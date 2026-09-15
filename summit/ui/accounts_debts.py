from __future__ import annotations

import csv
import math
import sqlite3
from datetime import date, datetime
from typing import Any, Callable

from PySide6.QtCore import QDate, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from summit.chrome import apply_frameless_chrome
from summit.database import Database
from summit.finance import brl, calculate, due_urgency, set_values_hidden, values_hidden
from summit.resources import app_icon
from summit.security import PinDialog
from summit.theme import DEFAULT_ACCENT, build_stylesheet
from summit.widgets import (
    BLUE,
    CATEGORY_COLORS,
    GREEN,
    ORANGE,
    PURPLE,
    CategoryField,
    DateField,
    ThemeToggle,
    action_widget,
    add_form_field,
    category_colors,
    confirm_delete,
    eye_icon,
    flow_colors,
    money_field,
    notes_field,
    select_combo_data,
    standard_table,
)
from summit.widgets_common import label, text_field

from summit.ui.common import MetricCard, Panel
from summit.ui.movements import FixedFlowColumn

class FixedEntriesPage(QWidget):
    def __init__(
        self,
        snapshot: dict[str, Any],
        add_income: Callable[[str], None],
        edit_income: Callable[[dict[str, Any]], None],
        add_expense: Callable[[str], None],
        edit_expense: Callable[[dict[str, Any]], None],
    ) -> None:
        super().__init__()
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(label("Entradas e gastos fixos", "PageTitle"))
        page.addWidget(label(
            "Organize o que se repete todos os meses. Clique em um cartão para editar, pausar ou excluir.",
            "Muted",
            True,
        ))
        page.addSpacing(12)
        board = QWidget()
        board.setObjectName("FixedBoard")
        columns = QHBoxLayout(board)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(12)
        columns.addWidget(FixedFlowColumn(
            "Entradas fixas", "receita mensal recorrente", snapshot.get("fixed_incomes", []),
            "income", add_income, edit_income,
        ), 1)
        columns.addWidget(FixedFlowColumn(
            "Gastos fixos", "compromisso mensal", snapshot["fixed_expenses"],
            "expense", add_expense, edit_expense,
        ), 1)
        page.addWidget(board, 1)


class AccountsPage(QWidget):
    def __init__(
        self,
        snapshot: dict[str, Any],
        add_account: Callable[[], None],
        edit_account: Callable[[dict[str, Any]], None],
        account_overrides: dict[int, bool],
        toggle_account_visibility: Callable[[int], None],
    ) -> None:
        super().__init__()
        stats = calculate(snapshot)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        title = QVBoxLayout()
        title.addWidget(label("Contas e saldos", "PageTitle"))
        title.addWidget(label("Ajuste o saldo-base e acompanhe o valor atualizado de cada conta.", "Muted"))
        header.addLayout(title)
        header.addStretch()
        add = QPushButton("+  Nova conta")
        add.setObjectName("PagePrimary")
        add.setStyleSheet("background: #8562ef; color: white; border-radius: 10px; padding: 10px 17px; font-weight: 700;")
        add.clicked.connect(add_account)
        header.addWidget(add)
        page.addLayout(header)
        page.addSpacing(12)
        hero = QFrame()
        hero.setObjectName("Panel")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 24, 28, 24)
        hero_layout.addWidget(label("PATRIMÔNIO NAS CONTAS", "SectionLabel"))
        hero_layout.addWidget(label(brl(stats["balance"]), "HeroValue"))
        hero_layout.addWidget(label("Visão consolidada do seu dinheiro disponível.", "Muted"))
        page.addWidget(hero)
        page.addSpacing(12)
        grid = QGridLayout()
        grid.setSpacing(13)
        for index, account in enumerate(snapshot["accounts"]):
            card = Panel(account["name"], account["account_type"])
            account_id = account["id"]
            is_hidden = account_overrides.get(account_id, values_hidden())
            visibility = QPushButton("\U0001F441" if not is_hidden else "\U0001F441\u20e0")
            visibility.setObjectName("VisibilityToggle")
            visibility.setToolTip(
                "Mostrar saldo desta conta" if is_hidden else "Ocultar saldo desta conta"
            )
            visibility.setCursor(Qt.CursorShape.PointingHandCursor)
            visibility.clicked.connect(
                lambda _checked=False, current_id=account_id: toggle_account_visibility(current_id)
            )
            card.body.itemAt(0).layout().addWidget(visibility)
            edit = QPushButton("Editar conta")
            edit.setObjectName("SmallButton")
            edit.clicked.connect(lambda _checked=False, current=account: edit_account(current))
            card.body.itemAt(0).layout().addWidget(edit)
            account_transactions = [
                item for item in snapshot["transactions"]
                if item["account_id"] == account_id and item["status"] == "paid"
            ]
            current_balance = float(account["initial_balance"]) + sum(
                float(item["amount"]) if item["kind"] == "income" else -float(item["amount"])
                for item in account_transactions
            )
            card.body.addSpacing(10)
            card.body.addWidget(label(brl(current_balance, hidden=is_hidden), "MetricValue"))
            card.body.addWidget(
                label(f'Saldo atual · base {brl(float(account["initial_balance"]), hidden=is_hidden)}', "Tiny")
            )
            grid.addWidget(card, index // 3, index % 3)
        page.addLayout(grid)
        page.addStretch()


class DebtsPage(QWidget):
    def __init__(
        self,
        debts: list[dict[str, Any]],
        add_debt: Callable[[], None],
        edit_debt: Callable[[dict[str, Any]], None],
    ) -> None:
        super().__init__()
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        title = QVBoxLayout()
        title.addWidget(label("Dívidas", "PageTitle"))
        title.addWidget(label("Acompanhe saldos, parcelas e vencimentos sem misturar com os gastos do mês.", "Muted"))
        header.addLayout(title)
        header.addStretch()
        add = QPushButton("+  Nova dívida")
        add.setObjectName("PagePrimary")
        add.setStyleSheet("background: #8562ef; color: white; border-radius: 10px; padding: 10px 17px; font-weight: 700;")
        add.clicked.connect(add_debt)
        header.addWidget(add)
        page.addLayout(header)
        page.addSpacing(12)

        today = date.today()
        open_debts = [item for item in debts if item["status"] == "open"]
        overdue = [item for item in open_debts if date.fromisoformat(item["due_date"]) < today]
        due_soon = [
            item for item in open_debts
            if 0 <= (date.fromisoformat(item["due_date"]) - today).days <= 30
        ]
        due_soon_amount = sum(
            float(item["outstanding_amount"])
            / max(1, int(item["installments_total"]) - int(item["installments_paid"]))
            for item in due_soon
        )
        totals = QGridLayout()
        totals.setSpacing(13)
        totals.addWidget(MetricCard(
            "Saldo devedor", brl(sum(float(item["outstanding_amount"]) for item in open_debts)),
            ORANGE, "MetricOrange", f"{len(open_debts)} dívida(s) aberta(s)",
        ), 0, 0)
        totals.addWidget(MetricCard(
            "Vencidas", brl(sum(float(item["outstanding_amount"]) for item in overdue)),
            "#ef7185", "MetricOrange", f"{len(overdue)} precisa(m) de atenção",
        ), 0, 1)
        totals.addWidget(MetricCard(
            "Próximos 30 dias", brl(due_soon_amount),
            BLUE, "MetricBlue", f"{len(due_soon)} parcela(s) estimada(s)",
        ), 0, 2)
        totals.addWidget(MetricCard(
            "Valor já pago", brl(sum(float(item["total_amount"]) - float(item["outstanding_amount"]) for item in debts)),
            GREEN, "MetricGreen", "Progresso acumulado",
        ), 0, 3)
        page.addLayout(totals)
        page.addSpacing(4)

        panel = Panel("Controle das dívidas", "Clique em uma linha para editar, quitar ou excluir")
        table = standard_table(["DÍVIDA", "CREDOR", "USO", "VENCIMENTO", "PARCELAS", "SALDO", "STATUS"])
        table.setObjectName("DebtsTable")
        table.setCursor(Qt.CursorShape.PointingHandCursor)
        for row_index, item in enumerate(debts):
            table.insertRow(row_index)
            due = date.fromisoformat(item["due_date"])
            if item["status"] == "paid":
                status = "Quitada"
            elif due < today:
                status = "Vencida"
            else:
                status = "Em aberto"
            values = [
                item["description"], item["creditor"],
                "Pessoal" if item["scope"] == "personal" else "Trabalho",
                due.strftime("%d/%m/%Y"),
                f'{item["installments_paid"]}/{item["installments_total"]}',
                brl(float(item["outstanding_amount"])), status,
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 6:
                    cell.setForeground(QColor(GREEN if status == "Quitada" else ORANGE))
                table.setItem(row_index, column, cell)
            table.setRowHeight(row_index, 48)
        table.cellClicked.connect(lambda row, _column: edit_debt(debts[row]))
        if not debts:
            table.setMinimumHeight(240)
        panel.body.addWidget(table)
        page.addWidget(panel)
        page.addStretch()


class PlanningPage(QWidget):
    def __init__(
        self,
        snapshot: dict[str, Any],
        add_goal: Callable[[], None],
        edit_goal: Callable[[dict[str, Any]], None],
        delete_goal: Callable[[dict[str, Any]], None],
        add_budget: Callable[[], None],
        edit_budget: Callable[[dict[str, Any]], None],
        delete_budget: Callable[[dict[str, Any]], None],
        metric_visibility: dict[str, bool] | None = None,
        toggle_metric_visibility: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        stats = calculate(snapshot)
        goals = snapshot["goals"]
        metric_visibility = metric_visibility or {}

        def metric_hidden(key: str) -> bool:
            return metric_visibility.get(key, values_hidden())
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        copy = QVBoxLayout()
        copy.addWidget(label("Planejamento financeiro", "PageTitle"))
        copy.addWidget(label("Metas com prazo e limites mensais baseados nos seus gastos reais.", "Muted"))
        header.addLayout(copy)
        header.addStretch()
        budget_button = QPushButton("+  Limite mensal")
        budget_button.setObjectName("Secondary")
        budget_button.clicked.connect(add_budget)
        goal_button = QPushButton("+  Nova meta")
        goal_button.setObjectName("Primary")
        goal_button.clicked.connect(add_goal)
        header.addWidget(budget_button)
        header.addWidget(goal_button)
        page.addLayout(header)
        page.addSpacing(14)

        total_target = sum(float(goal["target_amount"]) for goal in goals)
        saved = sum(float(goal["current_amount"]) for goal in goals)
        planned_monthly = sum(float(goal["monthly_contribution"]) for goal in goals)
        metrics = QGridLayout()
        metrics.setSpacing(13)
        metrics.addWidget(MetricCard(
            "Reservado nas metas", brl(saved, hidden=metric_hidden("saved")), PURPLE, "MetricPurple",
            f"Objetivo total: {brl(total_target)}",
            key="saved", hidden=metric_hidden("saved"), on_toggle=toggle_metric_visibility,
        ), 0, 0)
        metrics.addWidget(MetricCard(
            "Aportes planejados", brl(planned_monthly, hidden=metric_hidden("planned")), GREEN, "MetricGreen",
            "Valor mensal definido por você",
            key="planned", hidden=metric_hidden("planned"), on_toggle=toggle_metric_visibility,
        ), 0, 1)
        metrics.addWidget(MetricCard(
            "Custos fixos", brl(stats["fixed_total"], hidden=metric_hidden("fixed")), ORANGE, "MetricOrange",
            "Compromisso mensal recorrente",
            key="fixed", hidden=metric_hidden("fixed"), on_toggle=toggle_metric_visibility,
        ), 0, 2)
        metrics.addWidget(MetricCard(
            "Resultado do mês", brl(stats["result"], hidden=metric_hidden("result")), BLUE, "MetricBlue",
            f'Taxa de economia: {stats["savings_rate"]:.0f}%',
            key="result", hidden=metric_hidden("result"), on_toggle=toggle_metric_visibility,
        ), 0, 3)
        page.addLayout(metrics)

        goals_panel = Panel("Metas", "Quanto falta, prazo e aporte necessário")
        goals_grid = QGridLayout()
        goals_grid.setSpacing(12)
        today = date.today()
        for index, goal in enumerate(goals):
            deadline = date.fromisoformat(goal["deadline"]) if goal["deadline"] else None
            months = max(1, (deadline.year - today.year) * 12 + deadline.month - today.month) if deadline else 1
            remaining = max(float(goal["target_amount"]) - float(goal["current_amount"]), 0)
            required = remaining / months if deadline else 0
            progress = max(0, min(100, round(float(goal["current_amount"]) / float(goal["target_amount"]) * 100)))
            card = Panel(goal["name"], deadline.strftime("ATÉ %d/%m/%Y") if deadline else "SEM PRAZO DEFINIDO")
            card.body.itemAt(0).layout().addWidget(
                action_widget(
                    lambda _checked=False, current=goal: edit_goal(current),
                    lambda _checked=False, current=goal: delete_goal(current),
                )
            )
            card.body.addSpacing(10)
            card.body.addWidget(label(f'{brl(float(goal["current_amount"]))} de {brl(float(goal["target_amount"]))}', "MetricValue"))
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setValue(progress)
            card.body.addWidget(bar)
            card.body.addWidget(label(f"{progress}% concluído · faltam {brl(remaining)}", "Purple"))
            if deadline:
                card.body.addWidget(label(f"Aporte necessário: {brl(required)}/mês", "Tiny"))
            contribution = float(goal["monthly_contribution"])
            if contribution:
                status = "no ritmo" if not deadline or contribution >= required else "abaixo do necessário"
                card.body.addWidget(label(f"Seu plano: {brl(contribution)}/mês · {status}", "Positive" if status == "no ritmo" else "Orange"))
            if goal["notes"]:
                card.body.addWidget(label(goal["notes"], "Tiny", True))
            goals_grid.addWidget(card, index // 2, index % 2)
        if not goals:
            empty = Panel("Crie sua primeira meta", "Defina valor, prazo e aporte mensal")
            empty.body.addWidget(label("O Summit calcula o ritmo necessário e acompanha sua evolução.", "Muted", True))
            goals_grid.addWidget(empty, 0, 0)
        goals_panel.body.addLayout(goals_grid)
        page.addWidget(goals_panel)

        budgets_panel = Panel("Limites mensais", "Compare o planejado com os gastos concluídos deste mês")
        budget_table = standard_table(["CATEGORIA", "GASTO", "LIMITE", "DISPONÍVEL", "USO", "AÇÕES"])
        for row_index, budget in enumerate(stats["budget_rows"]):
            budget_table.insertRow(row_index)
            percentage = float(budget["percentage"])
            values = [
                budget["category"], brl(float(budget["spent"])), brl(float(budget["monthly_limit"])),
                brl(float(budget["remaining"])), f"{percentage:.0f}%",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column in {3, 4}:
                    cell.setForeground(QColor(ORANGE if percentage > 100 else GREEN))
                budget_table.setItem(row_index, column, cell)
            budget_table.setCellWidget(
                row_index,
                5,
                action_widget(
                    lambda _checked=False, current=budget: edit_budget(current),
                    lambda _checked=False, current=budget: delete_budget(current),
                ),
            )
            budget_table.setRowHeight(row_index, 48)
        budget_table.setMinimumHeight(190)
        budgets_panel.body.addWidget(budget_table)
        page.addWidget(budgets_panel)


class InvestmentsPage(QWidget):
    def __init__(
        self,
        investments: list[dict[str, Any]],
        add_investment: Callable[[], None],
        edit_investment: Callable[[dict[str, Any]], None],
        delete_investment: Callable[[dict[str, Any]], None],
    ) -> None:
        super().__init__()
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        copy = QVBoxLayout()
        copy.addWidget(label("Carteira de investimentos", "PageTitle"))
        copy.addWidget(label("Posição, custo, rentabilidade e detalhes de cada ativo.", "Muted"))
        header.addLayout(copy)
        header.addStretch()
        add = QPushButton("+  Novo investimento")
        add.setObjectName("Primary")
        add.clicked.connect(add_investment)
        header.addWidget(add)
        page.addLayout(header)
        page.addSpacing(14)

        invested = sum(float(item["invested"]) for item in investments)
        total = sum(float(item["current_value"]) for item in investments)
        result = total - invested
        profitability = (result / invested * 100) if invested else 0
        metrics = QGridLayout()
        metrics.setSpacing(13)
        metrics.addWidget(MetricCard("Valor atual", brl(total), PURPLE, "MetricPurple", "Patrimônio investido"), 0, 0)
        metrics.addWidget(MetricCard("Total aplicado", brl(invested), BLUE, "MetricBlue", "Custo acumulado"), 0, 1)
        metrics.addWidget(MetricCard("Resultado", brl(result), GREEN if result >= 0 else ORANGE, "MetricGreen" if result >= 0 else "MetricOrange", "Ganho ou perda da carteira"), 0, 2)
        metrics.addWidget(MetricCard("Rentabilidade", f"{profitability:+.2f}%", GREEN if result >= 0 else ORANGE, "MetricGreen" if result >= 0 else "MetricOrange", "Sobre o valor aplicado"), 0, 3)
        page.addLayout(metrics)

        grid = QGridLayout()
        grid.setSpacing(14)
        for index, investment in enumerate(investments):
            card = Panel(investment["name"], investment["investment_type"].upper())
            card.body.itemAt(0).layout().addWidget(
                action_widget(
                    lambda _checked=False, current=investment: edit_investment(current),
                    lambda _checked=False, current=investment: delete_investment(current),
                )
            )
            item_result = float(investment["current_value"]) - float(investment["invested"])
            item_rate = (item_result / float(investment["invested"]) * 100) if float(investment["invested"]) else 0
            card.body.addSpacing(10)
            card.body.addWidget(label(brl(float(investment["current_value"])), "MetricValue"))
            card.body.addWidget(label(f'Aplicado: {brl(float(investment["invested"]))}', "Tiny"))
            card.body.addWidget(label(f'{item_rate:+.2f}% · {brl(item_result)}', "Positive" if item_result >= 0 else "Orange"))
            details = []
            if investment["institution"]:
                details.append(investment["institution"])
            if float(investment["quantity"]):
                details.append(f'{float(investment["quantity"]):g} unidades')
            if float(investment["average_price"]):
                details.append(f'preço médio {brl(float(investment["average_price"]))}')
            if details:
                card.body.addWidget(label(" · ".join(details), "Tiny", True))
            if investment["notes"]:
                card.body.addWidget(label(investment["notes"], "Tiny", True))
            updated = investment["updated_at"]
            if updated:
                card.body.addWidget(label(f'Atualizado em {datetime.strptime(updated, "%Y-%m-%d").strftime("%d/%m/%Y")}', "Tiny"))
            grid.addWidget(card, index // 2, index % 2)
        if not investments:
            empty = Panel("Sua carteira começa aqui")
            empty.body.addWidget(label("Cadastre seus ativos para acompanhar valor atual e rentabilidade.", "Muted", True))
            grid.addWidget(empty, 0, 0)
        page.addLayout(grid)
        page.addStretch()


