"""Tela de conciliação de extratos importados.

Fluxo: o usuário escolhe um arquivo CSV -> as linhas viram candidatos em
`imported_transactions` -> aqui ele revisa cada uma (categoria, conta, uso
pessoal/trabalho), confirma (vira lançamento definitivo) ou ignora
(descarta sem apagar o extrato original). Possíveis duplicatas contra
lançamentos já existentes vêm marcadas para chamar atenção.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from summit.database import Database
from summit.finance import brl
from summit.import_bank import (
    ImportError_,
    parse_bank_csv,
    parse_santander_statement_pdf,
    read_text_file,
)
from summit.widgets import CategoryField, select_combo_data
from summit.widgets_common import label


def run_import_flow(database: Database, parent: QWidget) -> bool:
    """Abre o seletor de arquivo, importa o extrato escolhido e, se algo foi
    trazido, abre a tela de revisão. Retorna True se algo mudou."""
    accounts = database.accounts()
    if not accounts:
        QMessageBox.information(
            parent, "Cadastre uma conta primeiro",
            "Crie ao menos uma conta antes de importar um extrato, para que o Summit saiba onde lançar as movimentações.",
        )
        return False

    path, _ = QFileDialog.getOpenFileName(
        parent, "Importar extrato", "",
        "Extrato (*.csv *.txt *.pdf);;CSV/TXT (*.csv *.txt);;PDF Santander (*.pdf);;Todos os arquivos (*)",
    )
    if not path:
        return False

    account = _choose_account(parent, accounts)
    if account is None:
        return False

    try:
        if path.lower().endswith(".pdf"):
            rows = parse_santander_statement_pdf(path, account["id"])
        else:
            raw_text = read_text_file(path)
            rows = parse_bank_csv(raw_text, account["id"])
    except ImportError_ as error:
        QMessageBox.warning(parent, "Não foi possível importar", str(error))
        return False

    if not rows:
        QMessageBox.information(
            parent, "Nada para importar",
            "Não encontrei movimentações reconhecíveis nesse arquivo.",
        )
        return False

    summary = database.import_bank_rows(rows, account["id"])
    if summary["inserted"] == 0:
        QMessageBox.information(
            parent, "Extrato já importado",
            "Todas as movimentações desse arquivo já haviam sido importadas antes.",
        )
        return False

    message = f"{summary['inserted']} movimentação(ões) pronta(s) para revisão."
    if summary["skipped"]:
        message += f" {summary['skipped']} já constavam de uma importação anterior e foram ignoradas."
    QMessageBox.information(parent, "Extrato importado", message)

    dialog = ImportReviewDialog(database, parent)
    dialog.exec()
    return True


def _choose_account(parent: QWidget, accounts: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(accounts) == 1:
        return accounts[0]
    dialog = QDialog(parent)
    dialog.setWindowTitle("Qual conta recebeu esse extrato?")
    dialog.setModal(True)
    layout = QVBoxLayout(dialog)
    layout.addWidget(label("Selecione a conta correspondente ao extrato importado.", "Muted", True))
    combo = QComboBox()
    for account in accounts:
        combo.addItem(account["name"], account)
    layout.addWidget(combo)
    buttons = QHBoxLayout()
    cancel = QPushButton("Cancelar")
    cancel.setObjectName("Secondary")
    cancel.clicked.connect(dialog.reject)
    confirm = QPushButton("Continuar")
    confirm.setObjectName("Primary")
    confirm.clicked.connect(dialog.accept)
    buttons.addStretch()
    buttons.addWidget(cancel)
    buttons.addWidget(confirm)
    layout.addLayout(buttons)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return combo.currentData()
    return None


class ImportReviewDialog(QDialog):
    saved = Signal()

    COLUMNS = ["", "Data", "Descrição", "Valor", "Categoria", "Uso", "Conta", "Situação"]

    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.setWindowTitle("Revisar importação · Summit")
        self.setModal(True)
        self.setMinimumSize(880, 520)

        layout = QVBoxLayout(self)
        layout.addWidget(label("Revisar movimentações importadas", "PageTitle"))
        layout.addWidget(label(
            "Confira categoria e uso antes de confirmar. Duplicatas prováveis vêm marcadas em amarelo.",
            "Muted", True,
        ))

        self.accounts = database.accounts()
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        select_all = QPushButton("Selecionar todas")
        select_all.setObjectName("Secondary")
        select_all.clicked.connect(lambda: self._toggle_all(True))
        select_none = QPushButton("Limpar seleção")
        select_none.setObjectName("Secondary")
        select_none.clicked.connect(lambda: self._toggle_all(False))
        ignore = QPushButton("Ignorar selecionadas")
        ignore.setObjectName("DangerAction")
        ignore.clicked.connect(self._ignore_selected)
        confirm = QPushButton("Confirmar selecionadas")
        confirm.setObjectName("Primary")
        confirm.clicked.connect(self._confirm_selected)
        close = QPushButton("Fechar")
        close.setObjectName("Secondary")
        close.clicked.connect(self.accept)
        buttons.addWidget(select_all)
        buttons.addWidget(select_none)
        buttons.addStretch()
        buttons.addWidget(ignore)
        buttons.addWidget(confirm)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._reload()

    def _reload(self) -> None:
        pending = self.database.pending_imports()
        self.table.setRowCount(0)
        for row_data in pending:
            self._add_row(row_data)
        if not pending:
            self.accept()

    def _add_row(self, item: dict[str, Any]) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        checkbox = QCheckBox()
        checkbox.setChecked(not item["possible_duplicate"])
        checkbox_holder = QWidget()
        holder_layout = QHBoxLayout(checkbox_holder)
        holder_layout.setContentsMargins(8, 0, 0, 0)
        holder_layout.addWidget(checkbox)
        self.table.setCellWidget(row, 0, checkbox_holder)

        self.table.setItem(row, 1, QTableWidgetItem(item["transaction_date"]))
        self.table.setItem(row, 2, QTableWidgetItem(item["description"]))
        sign = "+" if item["kind"] == "income" else "-"
        self.table.setItem(row, 3, QTableWidgetItem(f"{sign} {brl(item['amount'])}"))

        category_field = CategoryField(self.database.categories, "Categoria")
        category_field.setText(item["category"])
        self.table.setCellWidget(row, 4, category_field)

        scope_combo = QComboBox()
        scope_combo.addItem("Trabalho", "work")
        scope_combo.addItem("Pessoal", "personal")
        select_combo_data(scope_combo, item["scope"])
        self.table.setCellWidget(row, 5, scope_combo)

        account_combo = QComboBox()
        for account in self.accounts:
            account_combo.addItem(account["name"], account["id"])
        select_combo_data(account_combo, item["account_id"])
        self.table.setCellWidget(row, 6, account_combo)

        status_label = label("Possível duplicata" if item["possible_duplicate"] else "Novo", "Muted")
        self.table.setCellWidget(row, 7, status_label)

        self.table.setRowHeight(row, 40)
        self.table.item(row, 1).setData(Qt.ItemDataRole.UserRole, item)
        checkbox.item_id = item["id"]  # type: ignore[attr-defined]

    def _toggle_all(self, checked: bool) -> None:
        for row in range(self.table.rowCount()):
            holder = self.table.cellWidget(row, 0)
            checkbox = holder.findChild(QCheckBox)
            if checkbox:
                checkbox.setChecked(checked)

    def _checked_rows(self) -> list[int]:
        rows = []
        for row in range(self.table.rowCount()):
            holder = self.table.cellWidget(row, 0)
            checkbox = holder.findChild(QCheckBox)
            if checkbox and checkbox.isChecked():
                rows.append(row)
        return rows

    def _ignore_selected(self) -> None:
        rows = self._checked_rows()
        if not rows:
            return
        ids = [self.table.item(row, 1).data(Qt.ItemDataRole.UserRole)["id"] for row in rows]
        self.database.ignore_imports(ids)
        self.saved.emit()
        self._reload()

    def _confirm_selected(self) -> None:
        rows = self._checked_rows()
        if not rows:
            return
        errors: list[str] = []
        for row in rows:
            item = self.table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            category_field: CategoryField = self.table.cellWidget(row, 4)  # type: ignore[assignment]
            scope_combo: QComboBox = self.table.cellWidget(row, 5)  # type: ignore[assignment]
            account_combo: QComboBox = self.table.cellWidget(row, 6)  # type: ignore[assignment]
            try:
                self.database.confirm_import(
                    item["id"],
                    description=item["description"],
                    category=category_field.text() or "Outros",
                    amount=item["amount"],
                    kind=item["kind"],
                    transaction_date=item["transaction_date"],
                    account_id=account_combo.currentData(),
                    scope=scope_combo.currentData(),
                )
            except (ValueError, sqlite3.Error) as error:
                errors.append(f"{item['description']}: {error}")
        if errors:
            QMessageBox.warning(self, "Algumas linhas não foram confirmadas", "\n".join(errors))
        self.saved.emit()
        self._reload()
