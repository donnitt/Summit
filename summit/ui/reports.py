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

class ReportsPage(QWidget):
    def __init__(self, snapshot: dict[str, Any]) -> None:
        super().__init__()
        self.snapshot = snapshot
        self.filtered: list[dict[str, Any]] = []
        self.page = QVBoxLayout(self)
        self.page.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        copy = QVBoxLayout()
        copy.addWidget(label("Relatórios financeiros", "PageTitle"))
        copy.addWidget(label("Analise um período, descubra padrões e exporte os dados.", "Muted"))
        header.addLayout(copy)
        header.addStretch()
        export = QPushButton("Exportar CSV")
        export.setObjectName("Primary")
        export.clicked.connect(self._export)
        header.addWidget(export)
        self.page.addLayout(header)

        filters = QHBoxLayout()
        filters.addWidget(label("PERÍODO DO RELATÓRIO", "SectionLabel"))
        filters.addStretch()
        self.start = DateField(QDate.currentDate().addDays(1 - QDate.currentDate().day()))
        self.end = DateField(QDate.currentDate())
        apply_button = QPushButton("Aplicar período")
        apply_button.setObjectName("Secondary")
        apply_button.clicked.connect(self._render)
        filters.addWidget(label("De", "FieldLabel"))
        filters.addWidget(self.start)
        filters.addWidget(label("Até", "FieldLabel"))
        filters.addWidget(self.end)
        filters.addWidget(apply_button)
        self.page.addLayout(filters)
        self.page.addSpacing(14)
        self.results = QWidget()
        self.page.addWidget(self.results)
        self._render()

    def _render(self) -> None:
        start = self.start.date().toPython()
        end = self.end.date().toPython()
        if start > end:
            self.end.setDate(self.start.date())
            end = start
        self.filtered = [
            item for item in self.snapshot["transactions"]
            if start <= date.fromisoformat(item["transaction_date"]) <= end
        ]
        paid = [item for item in self.filtered if item["status"] == "paid"]
        income = sum(float(item["amount"]) for item in paid if item["kind"] == "income")
        expense = sum(float(item["amount"]) for item in paid if item["kind"] == "expense")
        result = income - expense
        margin = (result / income * 100) if income else 0
        fixed = sum(float(item["amount"]) for item in self.snapshot["fixed_expenses"] if item["active"])

        replacement = QWidget()
        layout = QVBoxLayout(replacement)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        metrics = QGridLayout()
        metrics.setSpacing(13)
        metrics.addWidget(MetricCard("Entradas", brl(income), GREEN, "MetricGreen", "Recebidas no período"), 0, 0)
        metrics.addWidget(MetricCard("Gastos", brl(expense), ORANGE, "MetricOrange", "Pagos no período"), 0, 1)
        metrics.addWidget(MetricCard("Resultado", brl(result), PURPLE, "MetricPurple", f"Margem: {margin:.1f}%"), 0, 2)
        metrics.addWidget(MetricCard("Fixos mensais", brl(fixed), BLUE, "MetricBlue", "Compromissos recorrentes ativos"), 0, 3)
        layout.addLayout(metrics)

        analysis = QHBoxLayout()
        categories: dict[str, float] = {}
        for item in paid:
            if item["kind"] == "expense":
                categories[item["category"]] = categories.get(item["category"], 0) + float(item["amount"])
        ranking = Panel("Para onde foi o dinheiro", "Categorias de gastos no período")
        if categories:
            for index, (name, amount) in enumerate(sorted(categories.items(), key=lambda entry: entry[1], reverse=True)):
                row = QHBoxLayout()
                dot = label("●")
                dot.setStyleSheet(f"color: {CATEGORY_COLORS[index % len(CATEGORY_COLORS)]};")
                row.addWidget(dot)
                row.addWidget(label(name))
                row.addStretch()
                percentage = amount / expense * 100 if expense else 0
                row.addWidget(label(f"{brl(amount)} · {percentage:.0f}%", "Tiny"))
                ranking.body.addLayout(row)
        else:
            ranking.body.addWidget(label("Sem gastos concluídos neste período.", "Muted"))
        ranking.body.addStretch()
        analysis.addWidget(ranking, 5)

        insight = Panel("Leitura do período", "Um resumo para apoiar decisões")
        if income == 0 and expense == 0:
            message = "Ainda não há lançamentos concluídos neste intervalo. Escolha outro período ou registre movimentações."
        elif result < 0:
            message = f"Os gastos superaram as entradas em {brl(abs(result))}. Revise as maiores categorias e os custos fixos."
        elif margin < 20:
            message = f"O período fechou positivo, mas a margem foi de {margin:.1f}%. Há pouco espaço para imprevistos e metas."
        else:
            message = f"Resultado saudável: {margin:.1f}% das entradas ficaram disponíveis para metas, reserva ou investimentos."
        insight.body.addWidget(label(message, "Muted", True))
        insight.body.addSpacing(10)
        pending = sum(float(item["amount"]) for item in self.filtered if item["status"] == "pending")
        insight.body.addWidget(label(f"Valores previstos no período: {brl(pending)}", "Purple"))
        insight.body.addWidget(label(f"Quantidade de lançamentos: {len(self.filtered)}", "Tiny"))
        insight.body.addStretch()
        analysis.addWidget(insight, 4)
        layout.addLayout(analysis)

        detail = Panel("Detalhamento", "Todos os lançamentos encontrados no período")
        table = standard_table(["DESCRIÇÃO", "TIPO", "CATEGORIA", "DATA", "SITUAÇÃO", "VALOR"])
        for row_index, item in enumerate(self.filtered):
            table.insertRow(row_index)
            values = [
                item["description"], "Entrada" if item["kind"] == "income" else "Gasto", item["category"],
                datetime.strptime(item["transaction_date"], "%Y-%m-%d").strftime("%d/%m/%Y"),
                "Previsto" if item["status"] == "pending" else "Concluído", brl(float(item["amount"])),
            ]
            for column, value in enumerate(values):
                table.setItem(row_index, column, QTableWidgetItem(value))
            table.setRowHeight(row_index, 42)
        table.setMinimumHeight(240)
        detail.body.addWidget(table)
        layout.addWidget(detail)

        old = self.results
        self.page.replaceWidget(old, replacement)
        self.results = replacement
        old.hide()
        old.setParent(None)
        old.deleteLater()

    def _export(self) -> None:
        if not self.filtered:
            QMessageBox.information(self, "Nada para exportar", "Não há lançamentos no período selecionado.")
            return
        path, _selected = QFileDialog.getSaveFileName(
            self, "Salvar relatório", "relatorio-summit.csv", "Arquivo CSV (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.writer(stream, delimiter=";")
                writer.writerow(["Descrição", "Tipo", "Categoria", "Data", "Situação", "Valor", "Observações"])
                for item in self.filtered:
                    writer.writerow([
                        item["description"], "Entrada" if item["kind"] == "income" else "Gasto",
                        item["category"], item["transaction_date"],
                        "Previsto" if item["status"] == "pending" else "Concluído",
                        f'{float(item["amount"]):.2f}'.replace(".", ","), item.get("notes", ""),
                    ])
        except OSError as error:
            QMessageBox.warning(self, "Não foi possível exportar", str(error))
            return
        QMessageBox.information(self, "Relatório exportado", f"Arquivo salvo em:\n{path}")


