from __future__ import annotations

from collections import defaultdict
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any


MONTHS = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
_VALUES_HIDDEN = False


def set_values_hidden(hidden: bool) -> None:
    global _VALUES_HIDDEN
    _VALUES_HIDDEN = bool(hidden)


def values_hidden() -> bool:
    return _VALUES_HIDDEN


def brl(value: float, hidden: bool | None = None) -> str:
    """Format a value as BRL currency.

    ``hidden`` lets a caller override the global privacy toggle for a
    single value (used by per-account visibility switches). When not
    given, the global ``_VALUES_HIDDEN`` flag is used.
    """
    is_hidden = _VALUES_HIDDEN if hidden is None else hidden
    if is_hidden:
        return "R$ ••••••"
    formatted = f"{abs(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{'− ' if value < 0 else ''}R$ {formatted}"


def due_urgency(due: date, today: date | None = None) -> tuple[str, str]:
    """Return (label, style_name) describing how urgent a due date is.

    style_name matches the QLabel object names defined in theme.py
    (AlertOverdue / AlertToday / AlertSoon / AlertScheduled) so callers
    across different pages (dashboard alerts, movements list) can share
    the same visual language for due dates.
    """
    today = today or date.today()
    days = (due - today).days
    if days < 0:
        return f"Atrasado há {abs(days)} dia" + ("" if days == -1 else "s"), "AlertOverdue"
    if days == 0:
        return "Vence hoje", "AlertToday"
    if days <= 7:
        return f"Vence em {days} dia" + ("" if days == 1 else "s"), "AlertSoon"
    return due.strftime("%d/%m/%Y"), "AlertScheduled"


def _parse(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


MOVEMENTS_PERIOD_OPTIONS = (
    ("all", "Todo o período"),
    ("this_month", "Este mês"),
    ("last_month", "Mês passado"),
    ("last_3_months", "Últimos 3 meses"),
    ("this_year", "Este ano"),
    ("custom", "Personalizado"),
)


def movements_period_bounds(
    preset: str,
    custom_start: str = "",
    custom_end: str = "",
    today: date | None = None,
) -> tuple[date | None, date | None]:
    """Resolve a period preset (used by the Movimentações filter) into an
    inclusive (start, end) date range. Returns (None, None) for "all",
    meaning no filtering should be applied.
    """
    today = today or date.today()
    if preset == "this_month":
        start = date(today.year, today.month, 1)
        end = date(today.year, today.month, monthrange(today.year, today.month)[1])
        return start, end
    if preset == "last_month":
        month_index = today.year * 12 + today.month - 1 - 1
        year, zero_month = divmod(month_index, 12)
        month = zero_month + 1
        return date(year, month, 1), date(year, month, monthrange(year, month)[1])
    if preset == "last_3_months":
        month_index = today.year * 12 + today.month - 1 - 2
        year, zero_month = divmod(month_index, 12)
        start = date(year, zero_month + 1, 1)
        end = date(today.year, today.month, monthrange(today.year, today.month)[1])
        return start, end
    if preset == "this_year":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    if preset == "custom":
        try:
            start = date.fromisoformat(custom_start) if custom_start else None
        except ValueError:
            start = None
        try:
            end = date.fromisoformat(custom_end) if custom_end else None
        except ValueError:
            end = None
        return start, end
    return None, None


def filter_transactions_by_period(
    transactions: list[dict[str, Any]],
    preset: str,
    custom_start: str = "",
    custom_end: str = "",
    today: date | None = None,
) -> list[dict[str, Any]]:
    start, end = movements_period_bounds(preset, custom_start, custom_end, today)
    if start is None and end is None:
        return transactions
    filtered = []
    for item in transactions:
        item_date = _parse(item["transaction_date"])
        if start is not None and item_date < start:
            continue
        if end is not None and item_date > end:
            continue
        filtered.append(item)
    return filtered


def calculate(
    snapshot: dict[str, Any],
    today: date | None = None,
    period: str = "monthly",
) -> dict[str, Any]:
    today = today or date.today()
    if period not in {"weekly", "monthly", "annual"}:
        raise ValueError("Período inválido.")
    transactions = snapshot["transactions"]
    paid = [item for item in transactions if item["status"] == "paid"]

    def in_month(item: dict[str, Any], year: int, month: int) -> bool:
        item_date = _parse(item["transaction_date"])
        return item_date.year == year and item_date.month == month

    def total(items: list[dict[str, Any]]) -> float:
        return sum(float(item["amount"]) for item in items)

    if period == "weekly":
        period_start = today - timedelta(days=today.weekday())
        period_end = period_start + timedelta(days=6)
        period_name = "semana"
        period_title = "Nesta semana"
        period_label = "na semana"
        distribution_label = "da semana"
    elif period == "annual":
        period_start = date(today.year, 1, 1)
        period_end = date(today.year, 12, 31)
        period_name = "ano"
        period_title = f"Em {today.year}"
        period_label = "no ano"
        distribution_label = "do ano"
    else:
        period_start = date(today.year, today.month, 1)
        period_end = date(today.year, today.month, monthrange(today.year, today.month)[1])
        period_name = "mês"
        period_title = "Neste mês"
        period_label = "no mês"
        distribution_label = "do mês"

    def in_period(item: dict[str, Any]) -> bool:
        return period_start <= _parse(item["transaction_date"]) <= period_end

    period_paid = [item for item in paid if in_period(item)]
    income = total([item for item in period_paid if item["kind"] == "income"])
    expense = total([item for item in period_paid if item["kind"] == "expense"])
    initial = sum(float(account["initial_balance"]) for account in snapshot["accounts"])
    balance = initial + total([item for item in paid if item["kind"] == "income"]) - total(
        [item for item in paid if item["kind"] == "expense"]
    )
    pending_income = [item for item in transactions if item["kind"] == "income" and item["status"] == "pending"]
    pending_expense = [item for item in transactions if item["kind"] == "expense" and item["status"] == "pending"]
    fixed_total = sum(
        float(item["amount"])
        for item in snapshot.get("fixed_expenses", [])
        if item["active"]
    )
    fixed_income_total = sum(
        float(item["amount"])
        for item in snapshot.get("fixed_incomes", [])
        if item["active"]
    )

    monthly = []
    for offset in range(-5, 1):
        month_index = today.year * 12 + today.month - 1 + offset
        year, zero_month = divmod(month_index, 12)
        month = zero_month + 1
        month_items = [item for item in paid if in_month(item, year, month)]
        monthly.append(
            {
                "label": MONTHS[zero_month],
                "income": total([item for item in month_items if item["kind"] == "income"]),
                "expense": total([item for item in month_items if item["kind"] == "expense"]),
            }
        )

    def short_date(value: date) -> str:
        return f"{value.day:02d}/{value.month:02d}"

    if period == "weekly":
        cash_flow = []
        for offset, day_label in enumerate(WEEKDAYS):
            current = period_start + timedelta(days=offset)
            day_items = [item for item in paid if _parse(item["transaction_date"]) == current]
            cash_flow.append({
                "label": day_label,
                "range_label": short_date(current),
                "start": current.isoformat(),
                "end": current.isoformat(),
                "income": total([item for item in day_items if item["kind"] == "income"]),
                "expense": total([item for item in day_items if item["kind"] == "expense"]),
            })
        chart_subtitle = "Entradas e saídas por dia desta semana"
    elif period == "annual":
        cash_flow = []
        for month_index, month_label in enumerate(MONTHS, start=1):
            month_items = [item for item in paid if in_month(item, today.year, month_index)]
            month_start = date(today.year, month_index, 1)
            month_end = date(today.year, month_index, monthrange(today.year, month_index)[1])
            cash_flow.append({
                "label": month_label,
                "range_label": f"{month_label}/{today.year}",
                "start": month_start.isoformat(),
                "end": month_end.isoformat(),
                "income": total([item for item in month_items if item["kind"] == "income"]),
                "expense": total([item for item in month_items if item["kind"] == "expense"]),
            })
        chart_subtitle = f"Entradas e saídas por mês em {today.year}"
    else:
        # A aba "Mensal" compara meses entre si (não semanas dentro do mês
        # atual) — isso é o que faz sentido para quem quer ver a evolução
        # mês a mês. Mostramos os últimos 6 meses, incluindo o atual.
        cash_flow = []
        for offset in range(-5, 1):
            month_index = today.year * 12 + today.month - 1 + offset
            year, zero_month = divmod(month_index, 12)
            month = zero_month + 1
            month_items = [item for item in paid if in_month(item, year, month)]
            month_start = date(year, month, 1)
            month_end = date(year, month, monthrange(year, month)[1])
            month_label = MONTHS[zero_month]
            cash_flow.append({
                "label": f"{month_label}/{year % 100:02d}",
                "range_label": f"{month_label}/{year}",
                "start": month_start.isoformat(),
                "end": month_end.isoformat(),
                "income": total([item for item in month_items if item["kind"] == "income"]),
                "expense": total([item for item in month_items if item["kind"] == "expense"]),
            })
        chart_subtitle = "Entradas e saídas nos últimos 6 meses (toque numa barra para ver os lançamentos)"

    categories: dict[str, float] = defaultdict(float)
    for item in period_paid:
        if item["kind"] == "expense":
            categories[item["category"]] += float(item["amount"])

    normalized_categories = {name.casefold(): amount for name, amount in categories.items()}
    budget_rows = []
    for budget in snapshot.get("budgets", []):
        spent = normalized_categories.get(budget["category"].casefold(), 0.0)
        limit = float(budget["monthly_limit"])
        budget_rows.append(
            {
                **budget,
                "spent": spent,
                "remaining": limit - spent,
                "percentage": (spent / limit * 100) if limit else 0,
            }
        )

    invested = sum(float(item["invested"]) for item in snapshot.get("investments", []))
    investment_value = sum(float(item["current_value"]) for item in snapshot.get("investments", []))
    result = income - expense

    return {
        "balance": balance,
        "income": income,
        "expense": expense,
        "to_receive": total(pending_income),
        "to_pay": total(pending_expense),
        "pending_income_count": len(pending_income),
        "monthly": monthly,
        "cash_flow": cash_flow,
        "chart_subtitle": chart_subtitle,
        "period": period,
        "period_name": period_name,
        "period_title": period_title,
        "period_label": period_label,
        "distribution_label": distribution_label,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "categories": sorted(categories.items(), key=lambda item: item[1], reverse=True),
        "projected": balance + total(pending_income) - total(pending_expense) + fixed_income_total - fixed_total,
        "fixed_total": fixed_total,
        "fixed_income_total": fixed_income_total,
        "available_after_fixed": result + fixed_income_total - fixed_total,
        "result": result,
        "savings_rate": (result / income * 100) if income else 0,
        "budget_rows": budget_rows,
        "invested": invested,
        "investment_value": investment_value,
        "investment_result": investment_value - invested,
    }
