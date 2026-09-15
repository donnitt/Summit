"""Importação de extratos bancários (CSV) para conciliação manual.

Este módulo é o primeiro passo em direção à Prioridade 4 (sincronização
bancária via Open Finance). Ele lê um extrato exportado em CSV, normaliza
cada linha em um candidato a lançamento e calcula um hash de deduplicação.
Nada aqui grava direto na tabela `transactions`: os candidatos ficam em
`imported_transactions` até o usuário confirmar cada um na tela de
conciliação (evita duplicidade com lançamentos manuais).

Quando o sync automático (Pluggy/Belvo) for implementado, a ideia é que
o provedor gere a mesma lista de `ImportedRow` e reaproveite todo o
restante do fluxo (dedup, staging, tela de revisão) sem mudanças.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass

from pypdf import PdfReader

# Heurística simples de categorização por palavra-chave. É só um ponto de
# partida: o usuário sempre pode trocar a categoria na tela de revisão
# antes de confirmar o lançamento.
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Alimentação": (
        "mercad", "supermerc", "padaria", "restaurante", "lanchonete", "ifood",
        "99food", "food", "acougue", "açougue", "hortifruti", "frutas", "emporio",
        "empório", "dia brasil", "kfc", "habibs", "burger", "pizza", "sacolao",
    ),
    "Transporte": (
        "uber", "99app", "99 ", "combustive", "posto ", "pedagio", "pedágio",
        "estacionamento", "metro", "onibus", "ônibus",
    ),
    "Saúde": ("drogaria", "farmac", "hospital", "clinica", "clínica", "laborator"),
    "Contas": (
        "energia", "sabesp", "agua ", "água ", "luz ", "internet", "telefone",
        "boleto", "fatura", "vivo", "claro", "tim ", "condominio", "condomínio",
    ),
    "Assinaturas": (
        "netflix", "spotify", "amazon prime", "youtube premium", "assinatura",
        "hbo", "disney",
    ),
    "Lazer": ("cinema", "ingresso", "bar ", "balada"),
    "Salário": ("salario", "salário", "folha de pagamento", "provento"),
    "Serviços": ("pix enviado", "pix recebido", "ted ", "doc ", "transferencia", "transferência"),
}


@dataclass
class ImportedRow:
    transaction_date: str  # ISO yyyy-mm-dd
    description: str
    amount: float
    kind: str  # "income" ou "expense"
    category: str
    dedup_hash: str


class ImportError_(ValueError):
    """Erro amigável para exibir na UI quando o arquivo não pôde ser lido."""


def guess_category(description: str) -> str:
    normalized = description.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return category
    return "Outros"


def _parse_br_amount(raw: str) -> float | None:
    raw = raw.strip().strip('"').replace("R$", "").strip()
    if not raw:
        return None
    negative = raw.startswith("-")
    raw = raw.lstrip("-").strip()
    if not raw or raw in {".", ","}:
        return None
    raw = raw.replace(".", "").replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    return -value if negative else value


def _parse_date(raw: str) -> str | None:
    raw = raw.strip().strip('"')
    match = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", raw)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if match:
        return raw
    return None


def _dedup_hash(
    account_id: int | None, transaction_date: str, signed_amount: float, description: str,
    doc_ref: str = "",
) -> str:
    normalized = re.sub(r"\s+", " ", description.strip().lower())
    payload = f"{account_id}|{transaction_date}|{signed_amount:.2f}|{normalized}|{doc_ref}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_text_file(path: str) -> str:
    """Lê um arquivo de extrato tentando as codificações mais comuns no Brasil."""
    data = open(path, "rb").read()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ImportError_("Não foi possível ler o arquivo. Exporte o extrato como CSV e tente novamente.")


def parse_bank_csv(raw_text: str, account_id: int | None) -> list[ImportedRow]:
    """Interpreta um extrato em CSV com colunas Data/Descrição e
    Crédito+Débito separados ou uma única coluna de Valor (positivo/negativo).

    Aceita cabeçalhos com nomes variados (ex.: 'Histórico' no lugar de
    'Descrição', 'Entrada'/'Saída' no lugar de 'Crédito'/'Débito').
    """
    lines = [line for line in raw_text.splitlines() if line.strip()]
    header_index = None
    delimiter = ","
    for index, line in enumerate(lines):
        lowered = line.lower()
        if "data" in lowered and ("descri" in lowered or "hist" in lowered):
            for candidate_delim in (",", ";", "\t"):
                if line.count(candidate_delim) >= 2:
                    header_index = index
                    delimiter = candidate_delim
                    break
            if header_index is not None:
                break
    if header_index is None:
        raise ImportError_(
            "Não foi possível encontrar as colunas de Data e Descrição no arquivo. "
            "Confira se o extrato foi exportado em CSV a partir do internet banking."
        )

    reader = csv.reader(lines[header_index:], delimiter=delimiter)
    header = [cell.strip().lower() for cell in next(reader)]

    def find_column(*keywords: str) -> int | None:
        for idx, name in enumerate(header):
            if any(keyword in name for keyword in keywords):
                return idx
        return None

    date_col = find_column("data")
    desc_col = find_column("descri", "hist")
    credit_col = find_column("crédito", "credito", "entrada")
    debit_col = find_column("débito", "debito", "saida", "saída")
    value_col = find_column("valor") if credit_col is None and debit_col is None else None
    doc_col = find_column("docto", "documento", "n° doc", "nº doc")

    if date_col is None or desc_col is None:
        raise ImportError_("O arquivo não tem as colunas esperadas (Data e Descrição).")
    if credit_col is None and debit_col is None and value_col is None:
        raise ImportError_(
            "O arquivo não tem colunas de valor reconhecíveis (Crédito/Débito ou Valor)."
        )

    rows: list[ImportedRow] = []
    for cells in reader:
        if len(cells) <= date_col or len(cells) <= desc_col:
            continue
        transaction_date = _parse_date(cells[date_col])
        if transaction_date is None:
            continue  # provavelmente linha de resumo/rodapé do extrato
        description = cells[desc_col].strip().strip('"')
        if not description:
            continue

        amount: float | None = None
        kind: str | None = None
        if credit_col is not None and credit_col < len(cells):
            credit_value = _parse_br_amount(cells[credit_col])
            if credit_value:
                amount, kind = abs(credit_value), "income"
        if amount is None and debit_col is not None and debit_col < len(cells):
            debit_value = _parse_br_amount(cells[debit_col])
            if debit_value:
                amount, kind = abs(debit_value), "expense"
        if amount is None and value_col is not None and value_col < len(cells):
            raw_value = _parse_br_amount(cells[value_col])
            if raw_value:
                amount, kind = abs(raw_value), ("income" if raw_value > 0 else "expense")
        if not amount or kind is None:
            continue

        signed_amount = amount if kind == "income" else -amount
        doc_ref = cells[doc_col].strip() if doc_col is not None and doc_col < len(cells) else ""
        rows.append(
            ImportedRow(
                transaction_date=transaction_date,
                description=description,
                amount=round(amount, 2),
                kind=kind,
                category=guess_category(description),
                dedup_hash=_dedup_hash(account_id, transaction_date, signed_amount, description, doc_ref),
            )
        )
    return rows


# -- Extrato Santander em PDF ("Extrato Consolidado Inteligente") -----

_MONTH_NAMES_PT = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)
_PDF_MONEY_RE = re.compile(r"-?[\d.]+,\d{2}-?")
_PDF_DATE_RE = re.compile(r"^(\d{2})/(\d{2})\b")
_PDF_YEAR_RE = re.compile(r"/(\d{4})\b")
_PDF_NOISE_RE = re.compile(
    r"EXTRATO CONSOLIDADO|E ?xtrato_P ?F|B ?ALP|P ?agina\s*:|"
    r"(?:" + "|".join(_MONTH_NAMES_PT) + r")\s*/\s*\d{4}",
    re.IGNORECASE,
)


def _parse_pdf_number(raw: str) -> float:
    return float(raw.replace(".", "").replace(",", "."))


def parse_santander_statement_pdf(path: str, account_id: int | None) -> list[ImportedRow]:
    """Interpreta o 'Extrato Consolidado Inteligente' do Santander (PDF).

    O layout do PDF traz cada movimentação em uma ou duas linhas: uma linha
    "cabeçalho" com a data de processamento (só no primeiro lançamento do
    dia), descrição, número de documento e valor (com '-' no final para
    débitos); e, para a maioria dos lançamentos, uma segunda linha com a
    data real da compra e o estabelecimento, ou o nome de quem enviou/
    recebeu um PIX.
    """
    try:
        reader = PdfReader(path)
        full_text = "\n".join(
            page.extract_text(extraction_mode="layout") for page in reader.pages
        )
    except Exception as error:  # noqa: BLE001 - queremos uma mensagem amigável na UI
        raise ImportError_(f"Não foi possível ler o PDF: {error}") from None

    year_match = _PDF_YEAR_RE.search(full_text)
    if year_match is None:
        raise ImportError_("Não encontrei o mês/ano do extrato no PDF.")
    year = year_match.group(1)

    start = full_text.find("Movimentação")
    end = full_text.find("Saldos por Período")
    if start == -1 or end == -1 or end <= start:
        raise ImportError_(
            "Esse PDF não parece ser um extrato do Santander no formato esperado "
            "('Extrato Consolidado Inteligente')."
        )

    lines = full_text[start:end].split("\n")
    rows: list[ImportedRow] = []
    current_date: str | None = None
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line or _PDF_NOISE_RE.search(line):
            continue

        matches = list(_PDF_MONEY_RE.finditer(line))
        if not matches:
            continue  # linha solta sem valor: ruído de quebra de página

        amount_match = matches[0]
        date_match = _PDF_DATE_RE.match(line)
        if date_match:
            current_date = date_match.group(0)

        text_before_amount = line[:amount_match.start()]
        if date_match:
            text_before_amount = text_before_amount[date_match.end():]
        text_before_amount = text_before_amount.strip()
        doc_match = re.search(r"(\d{4,}|-)\s*$", text_before_amount)
        doc_ref = doc_match.group(1) if doc_match else ""
        if doc_ref == "-":
            doc_ref = ""
        description = re.sub(r"(\d{4,}|-)\s*$", "", text_before_amount).strip()

        raw_amount = amount_match.group(0)
        if raw_amount.endswith("-"):
            amount = _parse_pdf_number(raw_amount[:-1])
            kind = "expense"
        else:
            amount = _parse_pdf_number(raw_amount)
            kind = "income"
        if not amount:
            continue

        # a maioria dos lançamentos tem uma segunda linha (data real + local,
        # ou nome de quem mandou/recebeu o PIX) que completa a descrição
        if index < len(lines):
            next_line = lines[index].strip()
            if next_line and not _PDF_NOISE_RE.search(next_line) and not _PDF_MONEY_RE.search(next_line):
                description = f"{description} {next_line}".strip()
                index += 1

        if current_date is None:
            continue
        day, month = current_date.split("/")
        transaction_date = f"{year}-{month}-{day}"
        signed_amount = amount if kind == "income" else -amount

        rows.append(
            ImportedRow(
                transaction_date=transaction_date,
                description=description,
                amount=round(amount, 2),
                kind=kind,
                category=guess_category(description),
                dedup_hash=_dedup_hash(account_id, transaction_date, signed_amount, description, doc_ref),
            )
        )
    return rows
