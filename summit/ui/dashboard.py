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

from summit.ui.charts import CashFlowChart, DonutChart
from summit.ui.common import MetricCard, Panel
from summit.ui.movements import transaction_row

class DashboardPage(QWidget):
    def __init__(
        self,
        snapshot: dict[str, Any],
        add_transaction: Callable[[], None],
        confirm_receipt: Callable[[dict[str, Any]], None],
        edit_receipt: Callable[[dict[str, Any]], None],
        period: str,
        change_period: Callable[[str], None],
        metric_visibility: dict[str, bool] | None = None,
        toggle_metric_visibility: Callable[[str], None] | None = None,
        theme_mode: str = "dark",
        category_display_mode: str = "amount",
        toggle_category_display: Callable[[], None] | None = None,
        open_drilldown: Callable[..., None] | None = None,
    ) -> None:
        super().__init__()
        stats = calculate(snapshot, period=period)
        metric_visibility = metric_visibility or {}
        open_drilldown = open_drilldown or (lambda **_kwargs: None)

        def metric_hidden(key: str) -> bool:
            return metric_visibility.get(key, values_hidden())

        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(14)

        metrics = QGridLayout()
        metrics.setSpacing(13)
        cards = [
            MetricCard(
                "Saldo disponível", brl(stats["balance"], hidden=metric_hidden("balance")), PURPLE,
                "MetricPurple", "Visão consolidada",
                key="balance", hidden=metric_hidden("balance"), on_toggle=toggle_metric_visibility,
            ),
            MetricCard(
                f'Entradas {stats["period_label"]}', brl(stats["income"], hidden=metric_hidden("income")), GREEN,
                "MetricGreen", stats["period_title"],
                key="income", hidden=metric_hidden("income"), on_toggle=toggle_metric_visibility,
            ),
            MetricCard(
                f'Saídas {stats["period_label"]}', brl(stats["expense"], hidden=metric_hidden("expense")), ORANGE,
                "MetricOrange", stats["period_title"],
                key="expense", hidden=metric_hidden("expense"), on_toggle=toggle_metric_visibility,
            ),
            MetricCard(
                "A receber", brl(stats["to_receive"], hidden=metric_hidden("to_receive")), BLUE,
                "MetricBlue", f'{stats["pending_income_count"]} lançamento(s) previsto(s)',
                key="to_receive", hidden=metric_hidden("to_receive"), on_toggle=toggle_metric_visibility,
            ),
        ]
        for index, card in enumerate(cards):
            metrics.addWidget(card, 0, index)
        page.addLayout(metrics)

        period_bar = QHBoxLayout()
        period_bar.addWidget(label("PERÍODO DA VISÃO GERAL", "SectionLabel"))
        period_bar.addStretch()
        period_switch = QFrame()
        period_switch.setObjectName("PeriodSwitch")
        switch_layout = QHBoxLayout(period_switch)
        switch_layout.setContentsMargins(3, 3, 3, 3)
        switch_layout.setSpacing(3)
        period_buttons: list[QPushButton] = []
        for option_label, option_value in (("Semanal", "weekly"), ("Mensal", "monthly"), ("Anual", "annual")):
            option_button = QPushButton(option_label)
            option_button.setObjectName("PeriodOption")
            option_button.setCheckable(True)
            option_button.setChecked(option_value == period)
            option_button.setCursor(Qt.CursorShape.PointingHandCursor)
            option_button.clicked.connect(
                lambda _checked=False, selected=option_value: change_period(selected)
            )
            period_buttons.append(option_button)
            switch_layout.addWidget(option_button)
        period_bar.addWidget(period_switch)
        page.addLayout(period_bar)

        pending_income = sorted(
            (
                item for item in snapshot["transactions"]
                if item["kind"] == "income" and item["status"] == "pending"
            ),
            key=lambda item: item["transaction_date"],
        )
        if pending_income:
            alerts = QFrame()
            alerts.setObjectName("ReceivablesAlert")
            alert_layout = QVBoxLayout(alerts)
            alert_layout.setContentsMargins(18, 15, 18, 15)
            alert_layout.setSpacing(9)
            alert_header = QHBoxLayout()
            alert_title = QVBoxLayout()
            alert_title.addWidget(label("Recebimentos aguardando confirmação", "PanelTitle"))
            alert_title.addWidget(label(
                "Confira os vencimentos e confirme assim que o dinheiro cair na conta.", "Tiny"
            ))
            alert_header.addLayout(alert_title)
            alert_header.addStretch()
            alert_header.addWidget(label(f"{len(pending_income)} pendente(s)", "AlertCount"))
            alert_layout.addLayout(alert_header)
            rows = QGridLayout()
            rows.setHorizontalSpacing(9)
            rows.setVerticalSpacing(9)
            for index, item in enumerate(pending_income[:4]):
                due = date.fromisoformat(item["transaction_date"])
                urgency, urgency_name = due_urgency(due)
                row = QFrame()
                row.setObjectName("ReceivableRow")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(12, 10, 12, 10)
                copy = QVBoxLayout()
                copy.setSpacing(2)
                copy.addWidget(label(item["description"], "MovementTitle", True))
                urgency_label = label(urgency, urgency_name)
                copy.addWidget(urgency_label)
                row_layout.addLayout(copy, 1)
                value = label(brl(float(item["amount"])), "Positive")
                value.setStyleSheet(f"color: {GREEN}; font-weight: 700;")
                row_layout.addWidget(value)
                later = QPushButton("Ainda não")
                later.setObjectName("SmallButton")
                later.setToolTip("Editar ou reagendar o recebimento")
                later.clicked.connect(lambda _checked=False, current=item: edit_receipt(current))
                received = QPushButton("Confirmar entrada")
                received.setObjectName("ConfirmButton")
                received.clicked.connect(lambda _checked=False, current=item: confirm_receipt(current))
                row_layout.addWidget(later)
                row_layout.addWidget(received)
                rows.addWidget(row, index // 2, index % 2)
            alert_layout.addLayout(rows)
            if len(pending_income) > 4:
                alert_layout.addWidget(label(
                    f"Mais {len(pending_income) - 4} recebimento(s) na área Movimentações.", "Tiny"
                ))
            page.addWidget(alerts)

        charts = QHBoxLayout()
        charts.setSpacing(14)
        flow = flow_colors(theme_mode)
        cash = Panel("Fluxo de caixa", f'{stats["chart_subtitle"]} · toque num período para ver os lançamentos')
        legend = QHBoxLayout()
        accumulated = sum(item["income"] - item["expense"] for item in stats["cash_flow"])
        legend.addWidget(label(f"Resultado acumulado  {brl(accumulated)}", "Tiny"))
        legend.addStretch()
        income_legend = label("● Entradas")
        income_legend.setStyleSheet(f"color: {flow['income']}; font-size: 10px;")
        expense_legend = label("● Saídas")
        expense_legend.setStyleSheet(f"color: {flow['expense']}; font-size: 10px;")
        legend.addWidget(income_legend)
        legend.addWidget(expense_legend)
        cash.body.addLayout(legend)
        cash_chart = CashFlowChart(
            stats["cash_flow"],
            hide_income=metric_hidden("income"),
            hide_expense=metric_hidden("expense"),
            mode=theme_mode,
        )
        cash_chart.barClicked.connect(lambda bucket: open_drilldown(
            start=bucket["start"], end=bucket["end"],
            title=f'Lançamentos de {bucket.get("range_label", bucket["label"])}',
        ))
        cash.body.addWidget(cash_chart)
        charts.addWidget(cash, 7)

        categories_panel = Panel("Gastos por categoria", f'Distribuição {stats["distribution_label"]}')
        category_header = QHBoxLayout()
        category_header.addStretch()
        if toggle_category_display is not None:
            display_button = QPushButton("Mostrar em %" if category_display_mode == "amount" else "Mostrar em R$")
            display_button.setObjectName("Secondary")
            display_button.setCursor(Qt.CursorShape.PointingHandCursor)
            display_button.clicked.connect(lambda _checked=False: toggle_category_display())
            category_header.addWidget(display_button)
        categories_panel.body.addLayout(category_header)
        category_content = QHBoxLayout()
        expense_hidden = metric_hidden("expense")
        palette = category_colors(theme_mode)
        donut = DonutChart(
            stats["categories"], stats["expense"], hidden=expense_hidden,
            mode=theme_mode, show_percent=category_display_mode == "percent",
        )
        donut.slicePicked.connect(lambda name: open_drilldown(
            category=name, start=stats["period_start"], end=stats["period_end"],
            title=f"Lançamentos · {name}",
        ))
        category_content.addWidget(donut, 1)
        list_layout = QVBoxLayout()
        list_layout.addStretch()
        for index, (name, amount) in enumerate(stats["categories"][:5]):
            row = QPushButton()
            row.setObjectName("CategoryLegendRow")
            row.setFlat(True)
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setToolTip(f"Ver lançamentos de {name}")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            dot = label("●")
            dot.setStyleSheet(f"color: {palette[index % len(palette)]};")
            dot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row_layout.addWidget(dot)
            name_label = label(name, "Tiny")
            name_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row_layout.addWidget(name_label)
            row_layout.addStretch()
            percentage = round(amount / stats["expense"] * 100) if stats["expense"] else 0
            if category_display_mode == "percent":
                value_text = "••%" if expense_hidden else f"{percentage}%"
            else:
                value_text = brl(amount, hidden=expense_hidden)
            value_label = label(value_text, "Tiny")
            value_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row_layout.addWidget(value_label)
            row.clicked.connect(lambda _checked=False, current=name: open_drilldown(
                category=current, start=stats["period_start"], end=stats["period_end"],
                title=f"Lançamentos · {current}",
            ))
            list_layout.addWidget(row)
        if not stats["categories"]:
            list_layout.addWidget(label(f'Sem gastos {stats["period_label"]}', "Muted"))
        list_layout.addStretch()
        category_content.addLayout(list_layout, 1)
        categories_panel.body.addLayout(category_content)
        charts.addWidget(categories_panel, 4)
        page.addLayout(charts)

        lower = QHBoxLayout()
        lower.setSpacing(14)
        transactions = Panel("Últimas movimentações")
        add_button = QPushButton("+  Adicionar")
        add_button.setObjectName("TextButton")
        add_button.clicked.connect(add_transaction)
        transactions.body.itemAt(0).layout().addWidget(add_button)
        recent = snapshot["transactions"][:5]
        if recent:
            for item in recent:
                transactions.body.addLayout(transaction_row(item))
        else:
            transactions.body.addWidget(label("Nenhuma movimentação cadastrada.", "Muted"))
        transactions.body.addStretch()
        lower.addWidget(transactions, 5)

        goals = Panel("Metas financeiras")
        for goal in snapshot["goals"][:2]:
            goals.body.addSpacing(8)
            top = QHBoxLayout()
            top.addWidget(label(goal["name"]))
            top.addStretch()
            progress = min(100, round(float(goal["current_amount"]) / float(goal["target_amount"]) * 100))
            top.addWidget(label(f"{progress}%", "Purple"))
            goals.body.addLayout(top)
            goals.body.addWidget(label(f'{brl(goal["current_amount"])} de {brl(goal["target_amount"])}', "Tiny"))
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setValue(progress)
            goals.body.addWidget(bar)
        if not snapshot["goals"]:
            goals.body.addWidget(label("Crie sua primeira meta financeira.", "Muted"))
        goals.body.addStretch()
        lower.addWidget(goals, 3)

        projection = Panel("Projeção do mês", "Seu ritmo financeiro")
        projection.body.addSpacing(12)
        projection.body.addWidget(label("Saldo projetado", "Tiny"))
        projection.body.addWidget(label(brl(stats["projected"]), "MetricValue"))
        projection.body.addSpacing(8)
        projection.body.addWidget(label(f'+ A receber  {brl(stats["to_receive"], hidden=metric_hidden("to_receive"))}', "Positive"))
        projection.body.addWidget(label(f'+ Entradas fixas {brl(stats["fixed_income_total"])}', "Positive"))
        projection.body.addWidget(label(f'− A pagar     {brl(stats["to_pay"])}', "Orange"))
        projection.body.addWidget(label(f'− Custos fixos {brl(stats["fixed_total"])}', "Orange"))
        projection.body.addSpacing(8)
        projection.body.addWidget(label(f'Livre após fixos  {brl(stats["available_after_fixed"])}', "Purple"))
        projection.body.addStretch()
        projection.body.addWidget(label("●  Lançamentos futuros e valores fixos estão nesta projeção.", "Tiny", True))
        lower.addWidget(projection, 3)
        page.addLayout(lower)


