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
from summit.finance import (
    MOVEMENTS_PERIOD_OPTIONS,
    brl,
    calculate,
    due_urgency,
    filter_transactions_by_period,
    set_values_hidden,
    values_hidden,
)
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

# Cada MovementCard é um QFrame "de verdade" (layout + vários labels + estilo),
# não uma linha virtualizada. Construir milhares deles de uma vez (uma coluna
# inteira de gastos importados de extrato, por exemplo) é o que trava a tela
# ao entrar em Movimentações. Por isso as colunas renderizam em lotes.
MOVEMENT_PAGE_SIZE = 40

def transaction_row(item: dict[str, Any]) -> QHBoxLayout:
    row = QHBoxLayout()
    is_income = item["kind"] == "income"
    icon = label("↓" if is_income else "↑")
    icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon.setFixedSize(30, 30)
    icon.setStyleSheet(
        f"background: {'#143029' if is_income else '#34201c'}; color: {GREEN if is_income else ORANGE}; border-radius: 8px; font-weight: 700;"
    )
    row.addWidget(icon)
    copy = QVBoxLayout()
    copy.setSpacing(1)
    copy.addWidget(label(item["description"]))
    formatted_date = datetime.strptime(item["transaction_date"], "%Y-%m-%d").strftime("%d/%m/%Y")
    copy.addWidget(label(f'{item["category"]} · {formatted_date}', "Tiny"))
    row.addLayout(copy)
    row.addStretch()
    amount = label(f'{"+" if is_income else "−"} {brl(float(item["amount"]))}')
    amount.setStyleSheet(f"color: {GREEN if is_income else '#f1ebf5'}; font-weight: 700;")
    row.addWidget(amount)
    return row


class MovementCard(QFrame):
    """Compact, keyboard-accessible card that opens the corresponding editor."""

    clicked = Signal()

    def __init__(self, item: dict[str, Any], fixed: bool = False) -> None:
        super().__init__()
        self.setObjectName("MovementCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f'Editar {item["description"]}')
        self.setToolTip("Clique para editar ou excluir")

        content = QVBoxLayout(self)
        content.setContentsMargins(12, 11, 12, 11)
        content.setSpacing(5)
        title = label(item["description"], "MovementTitle", True)
        amount = float(item["amount"])
        if fixed:
            amount_text = brl(amount)
            is_fixed_income = item.get("_fixed_kind") == "income"
            amount_color = GREEN if is_fixed_income else ORANGE
            detail = f'{item["category"]} · dia {item["due_day"]}'
            state = "Ativa" if item["active"] else "Pausada"
            state_object_name = "Tiny"
        else:
            is_income = item["kind"] == "income"
            amount_text = f'{"+" if is_income else "−"} {brl(amount)}'
            amount_color = GREEN if is_income else ORANGE
            formatted_date = datetime.strptime(item["transaction_date"], "%Y-%m-%d").strftime("%d/%m/%Y")
            detail = f'{item["category"]} · {formatted_date}'
            if item["status"] == "paid":
                state = "Recebido" if is_income else "Pago"
                state_object_name = "Tiny"
            else:
                due = date.fromisoformat(item["transaction_date"])
                state, state_object_name = due_urgency(due)

        value = label(amount_text, "MovementValue")
        value.setStyleSheet(f"color: {amount_color}; font-weight: 700; font-size: 14px;")
        meta = label(detail, "Tiny", True)
        footer = QHBoxLayout()
        footer.setSpacing(5)
        scope = label("Pessoal" if item.get("scope") == "personal" else "Trabalho")
        scope.setObjectName("ScopePersonal" if item.get("scope") == "personal" else "ScopeWork")
        footer.addWidget(scope)
        footer.addStretch()
        state_label = label(state, state_object_name)
        footer.addWidget(state_label)
        for widget in (title, value, meta, scope, state_label):
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        content.addWidget(title)
        content.addWidget(value)
        content.addWidget(meta)
        content.addLayout(footer)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class MovementColumn(QFrame):
    def __init__(
        self,
        title: str,
        subtitle: str,
        items: list[dict[str, Any]],
        add_action: Callable[[], None],
        edit_action: Callable[[dict[str, Any]], None],
    ) -> None:
        super().__init__()
        self.setObjectName("MovementColumn")
        self.setProperty("boardColumn", title)
        self.setMinimumWidth(168)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 14, 13, 13)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        heading.setSpacing(5)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        copy.addWidget(label(title, "ColumnTitle"))
        copy.addWidget(label(f"{len(items)} lançamento" + ("" if len(items) == 1 else "s"), "Tiny"))
        heading.addLayout(copy)
        heading.addStretch()
        add = QPushButton("+")
        add.setObjectName("ColumnAdd")
        add.setToolTip(f"Adicionar em {title.lower()}")
        add.setAccessibleName(f"Adicionar em {title}")
        add.clicked.connect(add_action)
        heading.addWidget(add)
        layout.addLayout(heading)
        layout.addWidget(label(subtitle, "ColumnHint", True))
        layout.addWidget(label(f'Total  {brl(sum(float(item["amount"]) for item in items))}', "ColumnTotal"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: 0; }")
        scroll.viewport().setStyleSheet("background: transparent;")
        scroll.setMinimumHeight(465)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        cards = QVBoxLayout(container)
        cards.setContentsMargins(0, 2, 0, 2)
        cards.setSpacing(8)
        if not items:
            cards.addWidget(label("Nenhum lançamento aqui por enquanto.", "EmptyState", True))

        self._items = items
        self._edit_action = edit_action
        self._cards_layout = cards
        self._rendered_count = 0
        self._load_more_button = QPushButton()
        self._load_more_button.setObjectName("Secondary")
        self._load_more_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._load_more_button.clicked.connect(self._render_next_batch)
        cards.addWidget(self._load_more_button)
        cards.addStretch()
        self._render_next_batch()

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

    def _render_next_batch(self) -> None:
        start = self._rendered_count
        end = min(start + MOVEMENT_PAGE_SIZE, len(self._items))
        insert_at = self._cards_layout.indexOf(self._load_more_button)
        for item in self._items[start:end]:
            card = MovementCard(item)
            card.clicked.connect(lambda current=item: self._edit_action(current))
            self._cards_layout.insertWidget(insert_at, card)
            insert_at += 1
        self._rendered_count = end
        remaining = len(self._items) - self._rendered_count
        if remaining > 0:
            self._load_more_button.setText(f"Carregar mais ({remaining} restante" + ("s)" if remaining != 1 else ")"))
            self._load_more_button.setVisible(True)
        else:
            self._load_more_button.setVisible(False)


class FixedFlowColumn(QFrame):
    def __init__(
        self,
        title: str,
        subtitle: str,
        items: list[dict[str, Any]],
        kind: str,
        add_action: Callable[[str], None],
        edit_action: Callable[[dict[str, Any]], None],
    ) -> None:
        super().__init__()
        self.setObjectName("MovementColumn")
        self.setProperty("boardColumn", title)
        self.setMinimumWidth(280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 14, 13, 13)
        layout.setSpacing(8)
        layout.addWidget(label(title, "ColumnTitle"))
        active = [item for item in items if item["active"]]
        active_label = "ativo" if len(active) == 1 else "ativos"
        layout.addWidget(label(f"{len(active)} {active_label} · {subtitle}", "Tiny"))
        layout.addWidget(label(f'Total  {brl(sum(float(item["amount"]) for item in active))}', "ColumnTotal"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: 0; }")
        scroll.viewport().setStyleSheet("background: transparent;")
        scroll.setMinimumHeight(496)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        sections = QVBoxLayout(container)
        sections.setContentsMargins(0, 2, 0, 2)
        sections.setSpacing(8)
        for scope, section_title in (("personal", "PESSOAL"), ("work", "TRABALHO")):
            scoped_items = [item for item in items if item.get("scope", "work") == scope]
            section_header = QHBoxLayout()
            section_header.addWidget(label(f"{section_title}  ·  {len(scoped_items)}", "FixedSection"))
            section_header.addStretch()
            add = QPushButton("+")
            add.setObjectName("InlineAdd")
            movement_name = "entrada fixa" if kind == "income" else "gasto fixo"
            add.setToolTip(f"Adicionar {movement_name} de {section_title.lower()}")
            add.setAccessibleName(f"Adicionar {movement_name} de {section_title.lower()}")
            add.clicked.connect(lambda _checked=False, selected_scope=scope: add_action(selected_scope))
            section_header.addWidget(add)
            sections.addLayout(section_header)
            subtotal = sum(float(item["amount"]) for item in scoped_items if item["active"])
            sections.addWidget(label(f"Subtotal ativo  {brl(subtotal)}", "FixedSubtotal"))
            for item in scoped_items:
                display_item = {**item, "_fixed_kind": kind}
                card = MovementCard(display_item, fixed=True)
                card.clicked.connect(lambda current=item: edit_action(current))
                sections.addWidget(card)
            if not scoped_items:
                sections.addWidget(label("Nenhuma conta cadastrada.", "EmptyState", True))
            sections.addSpacing(8)
        sections.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)


class MovementsPage(QWidget):
    def __init__(
        self,
        snapshot: dict[str, Any],
        add_transaction: Callable[[str, str], None],
        edit_transaction: Callable[[dict[str, Any]], None],
        import_statement: Callable[[], None] | None = None,
        filter_state: dict[str, str] | None = None,
        on_filter_change: Callable[[str, str, str, str], None] | None = None,
    ) -> None:
        super().__init__()
        filter_state = filter_state or {}
        preset = filter_state.get("preset", "all")
        custom_start = filter_state.get("start", "")
        custom_end = filter_state.get("end", "")
        search_text = filter_state.get("search", "")

        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(label("Movimentações organizadas", "PageTitle"))
        titles.addWidget(label(
            "Tudo visível em um único quadro. Clique em qualquer cartão para editar ou excluir.",
            "Muted",
            True,
        ))
        heading.addLayout(titles)
        heading.addStretch()
        if import_statement is not None:
            import_button = QPushButton("Importar extrato")
            import_button.setObjectName("Secondary")
            import_button.setToolTip("Importar um extrato (CSV ou PDF do Santander) para conciliação")
            import_button.clicked.connect(import_statement)
            heading.addWidget(import_button, 0, Qt.AlignmentFlag.AlignTop)
        page.addLayout(heading)
        page.addSpacing(12)

        def emit_filter_change(
            new_preset: str | None = None,
            new_start: str | None = None,
            new_end: str | None = None,
            new_search: str | None = None,
        ) -> None:
            if on_filter_change is None:
                return
            on_filter_change(
                preset if new_preset is None else new_preset,
                custom_start if new_start is None else new_start,
                custom_end if new_end is None else new_end,
                search_text if new_search is None else new_search,
            )

        if on_filter_change is not None:
            filter_bar = QHBoxLayout()
            filter_bar.setSpacing(8)

            period_combo = QComboBox()
            period_combo.setObjectName("PeriodFilter")
            period_combo.setToolTip("Filtrar lançamentos por período")
            for value, text in MOVEMENTS_PERIOD_OPTIONS:
                period_combo.addItem(text, value)
            select_combo_data(period_combo, preset)
            period_combo.currentIndexChanged.connect(
                lambda _index: emit_filter_change(new_preset=period_combo.currentData())
            )
            filter_bar.addWidget(period_combo)

            start_field = DateField(custom_start or QDate.currentDate())
            end_field = DateField(custom_end or QDate.currentDate())
            start_field.setVisible(preset == "custom")
            end_field.setVisible(preset == "custom")
            start_field.dateChanged.connect(
                lambda value: emit_filter_change(new_start=value.toString("yyyy-MM-dd"))
            )
            end_field.dateChanged.connect(
                lambda value: emit_filter_change(new_end=value.toString("yyyy-MM-dd"))
            )
            filter_bar.addWidget(label("de", "Tiny"))
            filter_bar.addWidget(start_field)
            filter_bar.addWidget(label("até", "Tiny"))
            filter_bar.addWidget(end_field)

            search_field = text_field("Buscar por descrição ou categoria…", search_text)
            search_field.setMinimumWidth(220)
            search_field.editingFinished.connect(
                lambda: emit_filter_change(new_search=search_field.text().strip())
            )
            filter_bar.addWidget(search_field, 1)

            if preset != "all" or search_text:
                clear_button = QPushButton("Limpar filtros")
                clear_button.setObjectName("Secondary")
                clear_button.clicked.connect(lambda: emit_filter_change("all", "", "", ""))
                filter_bar.addWidget(clear_button)

            page.addLayout(filter_bar)
            page.addSpacing(10)

        transactions = filter_transactions_by_period(snapshot["transactions"], preset, custom_start, custom_end)
        if search_text:
            needle = search_text.casefold()
            transactions = [
                item for item in transactions
                if needle in item["description"].casefold() or needle in item["category"].casefold()
            ]

        if (preset != "all" or search_text) and not transactions:
            page.addWidget(label(
                "Nenhum lançamento encontrado com esse filtro. Tente ampliar o período ou limpar a busca.",
                "EmptyState",
                True,
            ))

        sections = [
            (
                "Entradas", "Dinheiro que já entrou.",
                [item for item in transactions if item["kind"] == "income" and item["status"] == "paid"],
                "income", "paid",
            ),
            (
                "A receber", "Valores previstos.",
                [item for item in transactions if item["kind"] == "income" and item["status"] == "pending"],
                "income", "pending",
            ),
            (
                "Gastos", "Pagos e programados.",
                [item for item in transactions if item["kind"] == "expense"],
                "expense", "paid",
            ),
        ]
        board = QWidget()
        board.setObjectName("MovementBoard")
        columns = QHBoxLayout(board)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(10)
        for name, subtitle, items, kind, status in sections:
            columns.addWidget(
                MovementColumn(
                    name,
                    subtitle,
                    items,
                    lambda _checked=False, selected_kind=kind, selected_status=status: add_transaction(
                        selected_kind, selected_status
                    ),
                    edit_transaction,
                ),
                1,
            )
        page.addWidget(board, 1)


class DrillDownDialog(QDialog):
    """Filtered, read-only-ish list of transactions opened via chart drill-down.

    Reuses MovementCard so a click on any entry opens the normal editor,
    keeping this a thin filtering layer rather than a parallel UI.
    """

    def __init__(
        self,
        title: str,
        items: list[dict[str, Any]],
        edit_transaction: Callable[[dict[str, Any]], None],
        parent: QWidget | None = None,
        mode: str = "dark",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(420, 480)
        self.setObjectName("DrillDownDialog")
        # A raw QDialog only paints a background on the parts our own
        # widgets cover; the scroll area's viewport otherwise falls back to
        # the OS palette, which produced a mismatched light/dark seam. Force
        # a single solid, styled surface for the whole window instead.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card_bg, border, list_bg = ("#171120", "#30263a", "#130e1b") if mode == "dark" else ("#ffffff", "#e2d9f5", "#f7f4fc")
        self.setStyleSheet(
            f"QDialog#DrillDownDialog {{ background: {card_bg}; border: 1px solid {border}; border-radius: 16px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)
        layout.addWidget(label(title, "PageTitle"))

        income_total = sum(float(item["amount"]) for item in items if item["kind"] == "income")
        expense_total = sum(float(item["amount"]) for item in items if item["kind"] == "expense")
        summary = QHBoxLayout()
        summary.addWidget(label(f"{len(items)} lançamento(s)", "Muted"))
        summary.addStretch()
        if income_total:
            summary.addWidget(label(f"+ {brl(income_total)}", "Positive"))
        if expense_total:
            expense_label = label(f"− {brl(expense_total)}")
            expense_label.setStyleSheet(f"color: {ORANGE}; font-weight: 700;")
            summary.addWidget(expense_label)
        layout.addLayout(summary)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {list_bg}; border-radius: 11px; }}")
        scroll.viewport().setStyleSheet(f"background: {list_bg}; border-radius: 11px;")
        container = QWidget()
        container.setStyleSheet(f"background: {list_bg};")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(10, 10, 10, 10)
        container_layout.setSpacing(8)
        if items:
            self._items = items
            self._edit_transaction = edit_transaction
            self._cards_layout = container_layout
            self._rendered_count = 0
            self._load_more_button = QPushButton()
            self._load_more_button.setObjectName("Secondary")
            self._load_more_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._load_more_button.clicked.connect(self._render_next_batch)
            container_layout.addWidget(self._load_more_button)
            self._render_next_batch()
        else:
            container_layout.addWidget(label("Nenhum lançamento neste recorte.", "Muted"))
        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        close_button = QPushButton("Fechar")
        close_button.setObjectName("Secondary")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.reject)
        layout.addWidget(close_button)

    def _render_next_batch(self) -> None:
        start = self._rendered_count
        end = min(start + MOVEMENT_PAGE_SIZE, len(self._items))
        insert_at = self._cards_layout.indexOf(self._load_more_button)
        for item in self._items[start:end]:
            card = MovementCard(item)
            card.clicked.connect(lambda current=item: (self._edit_transaction(current), self.accept()))
            self._cards_layout.insertWidget(insert_at, card)
            insert_at += 1
        self._rendered_count = end
        remaining = len(self._items) - self._rendered_count
        if remaining > 0:
            self._load_more_button.setText(f"Carregar mais ({remaining} restante" + ("s)" if remaining != 1 else ")"))
            self._load_more_button.setVisible(True)
        else:
            self._load_more_button.setVisible(False)


