"""Reusable, app-agnostic input widgets and small UI helpers.

Split out of summit/ui.py: none of this depends on Database or any page —
it's the layer of small building blocks (fields, popovers, tables, buttons)
that pages and dialogs are assembled from.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QDate, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from summit.widgets_common import label


PURPLE = "#9b7cff"
GREEN = "#4bd7b2"
ORANGE = "#ff9d66"
BLUE = "#64a8ff"
CATEGORY_COLORS = (PURPLE, GREEN, ORANGE, BLUE, "#e96e95", "#756782")

# Deeper variants of the same palette, used only where color also carries
# text/line meaning against a light background — the pastel dark-mode
# tones above don't hold enough contrast on white (e.g. #4bd7b2 or #ff9d66
# text on #ffffff falls well under WCAG AA for normal-size text).
PURPLE_ON_LIGHT = "#6a4bd6"
GREEN_ON_LIGHT = "#0f8f6c"
ORANGE_ON_LIGHT = "#c85a1f"
BLUE_ON_LIGHT = "#2f66d1"
CATEGORY_COLORS_LIGHT = (PURPLE_ON_LIGHT, GREEN_ON_LIGHT, ORANGE_ON_LIGHT, BLUE_ON_LIGHT, "#c14672", "#5c5468")


def flow_colors(mode: str) -> dict[str, str]:
    """Line/legend colors for income & expense, tuned per theme.

    Kept semantically identical to the dark palette (purple = entradas,
    orange = saídas) — only saturation/depth changes so the same colors
    stay legible as text and thin chart lines on a light background.
    """
    if mode == "light":
        return {"income": PURPLE_ON_LIGHT, "expense": ORANGE_ON_LIGHT}
    return {"income": PURPLE, "expense": ORANGE}


def category_colors(mode: str) -> tuple[str, ...]:
    return CATEGORY_COLORS_LIGHT if mode == "light" else CATEGORY_COLORS


def eye_icon(open_eye: bool, color: str, size: int = 18) -> QIcon:
    """Draw a small eye glyph: an almond outline with a pupil.

    When ``open_eye`` is False, a diagonal line is drawn across it to mean
    "hidden" — the same visual language used by most password/reveal toggles.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    margin = size * 0.14
    mid = size / 2
    path = QPainterPath()
    path.moveTo(margin, mid)
    path.quadTo(mid, margin, size - margin, mid)
    path.quadTo(mid, size - margin, margin, mid)
    path.closeSubpath()
    painter.drawPath(path)

    pupil_radius = size * 0.11
    painter.setBrush(QColor(color))
    painter.drawEllipse(QPointF(mid, mid), pupil_radius, pupil_radius)

    if not open_eye:
        slash_pen = QPen(QColor(color))
        slash_pen.setWidthF(1.0)
        slash_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(slash_pen)
        slash_margin = size * 0.22
        painter.drawLine(
            QPointF(slash_margin, size - slash_margin),
            QPointF(size - slash_margin, slash_margin),
        )

    painter.end()
    return QIcon(pixmap)


class MoneyField(QDoubleSpinBox):
    """Currency input whose current value is replaced on the first edit."""

    def focusInEvent(self, event: Any) -> None:
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)

    def mousePressEvent(self, event: Any) -> None:
        gaining_focus = not self.hasFocus()
        super().mousePressEvent(event)
        if gaining_focus:
            QTimer.singleShot(0, self.selectAll)


def money_field(value: float = 0, allow_negative: bool = False) -> MoneyField:
    field = MoneyField()
    field.setRange(-999_999_999 if allow_negative else 0, 999_999_999)
    field.setDecimals(2)
    field.setGroupSeparatorShown(True)
    field.setPrefix("R$ ")
    field.setKeyboardTracking(False)
    field.setValue(float(value))
    return field


class SwitchButton(QPushButton):
    """Toggle switch with a rounded track and sliding thumb."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(46, 24)
        self.setObjectName("SwitchButton")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Alternar tema escuro e claro")

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = float(self.width())
        height = float(self.height())
        radius = height / 2.0
        margin = 3.0
        thumb_diameter = height - (margin * 2.0)

        is_on = self.isChecked()
        track_color = QColor("#8562ef") if is_on else QColor("#282036")
        border_color = QColor("#a78bfa") if is_on else QColor("#493b5e")
        thumb_color = QColor("#ffffff") if is_on else QColor("#e2d8ec")

        # Draw pill track
        painter.setPen(QPen(border_color, 1.0))
        painter.setBrush(track_color)
        painter.drawRoundedRect(QRectF(0.5, 0.5, width - 1.0, height - 1.0), radius, radius)

        # Draw thumb
        thumb_x = (width - margin - thumb_diameter) if is_on else margin
        thumb_y = margin
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(thumb_color)
        painter.drawEllipse(QRectF(thumb_x, thumb_y, thumb_diameter, thumb_diameter))
        painter.end()


class ThemeToggle(QWidget):
    """Theme switcher with Moon (dark) on the left, pill switch, and Sun (light) on the right."""

    themeChanged = Signal(str)

    def __init__(self, mode: str = "dark", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ThemeToggle")
        self.setToolTip("Alternar tema (Escuro / Claro)")
        self._mode = mode if mode in ("dark", "light") else "dark"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self.moon_label = QLabel("🌙")
        self.moon_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.moon_label.setToolTip("Tema escuro")
        self.moon_label.setStyleSheet("font-size: 13px; background: transparent;")
        self.moon_label.mousePressEvent = lambda _event: self.set_mode("dark", notify=True)

        self.switch = SwitchButton(checked=(self._mode == "light"))
        self.switch.toggled.connect(self._on_switch_toggled)

        self.sun_label = QLabel("☀️")
        self.sun_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sun_label.setToolTip("Tema claro")
        self.sun_label.setStyleSheet("font-size: 13px; background: transparent;")
        self.sun_label.mousePressEvent = lambda _event: self.set_mode("light", notify=True)

        layout.addWidget(self.moon_label)
        layout.addWidget(self.switch)
        layout.addWidget(self.sun_label)

    def _on_switch_toggled(self, checked: bool) -> None:
        new_mode = "light" if checked else "dark"
        if new_mode != self._mode:
            self._mode = new_mode
            self.themeChanged.emit(self._mode)

    def set_mode(self, mode: str, notify: bool = False) -> None:
        if mode not in ("dark", "light"):
            return
        self._mode = mode
        self.switch.blockSignals(True)
        self.switch.setChecked(mode == "light")
        self.switch.blockSignals(False)
        self.switch.update()
        if notify:
            self.themeChanged.emit(self._mode)

    def mode(self) -> str:
        return self._mode


_CALENDAR_MONTHS = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)
_CALENDAR_WEEKDAYS = ("D", "S", "T", "Q", "Q", "S", "S")


class MiniCalendar(QWidget):
    """Compact popover calendar, anchored under a field instead of a separate window."""

    dateSelected = Signal(QDate)

    def __init__(self, initial: QDate, anchor: QWidget) -> None:
        super().__init__(anchor, Qt.WindowType.Popup)
        self.setObjectName("MiniCalendar")
        self._view_year = initial.year()
        self._view_month = initial.month()
        self._pending = QDate(initial)
        self.setStyleSheet(
            """
            QWidget#MiniCalendar { background: #171120; border: 1px solid #33283e; border-radius: 14px; }
            QLabel#CalMonth { color: #f4f0f8; font-size: 14px; font-weight: 700; }
            QPushButton#CalNav {
                background: transparent; color: #a99cc7; border: 0; font-size: 15px; font-weight: 700;
                min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px; border-radius: 13px;
            }
            QPushButton#CalNav:hover { background: #251a34; color: white; }
            QLabel#CalWeekday { color: #716778; font-size: 10px; font-weight: 700; }
            QPushButton#CalDay {
                background: transparent; color: #d9d2e2; border: 0; border-radius: 16px;
                min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; font-size: 12px;
            }
            QPushButton#CalDay:hover { background: #251a34; }
            QPushButton#CalDaySelected {
                background: #8562ef; color: white; border: 0; border-radius: 16px;
                min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; font-size: 12px; font-weight: 700;
            }
            QPushButton#CalToday { border: 1px solid #8562ef; }
            QPushButton#CalFooter {
                background: transparent; color: #ad94ff; border: 0; font-weight: 700; font-size: 11px; padding: 7px 10px;
            }
            QPushButton#CalFooter:hover { color: #d1c2ff; }
            """
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 10)
        outer.setSpacing(10)

        header = QHBoxLayout()
        self.month_label = QLabel()
        self.month_label.setObjectName("CalMonth")
        header.addWidget(self.month_label)
        header.addStretch()
        previous_button = QPushButton("‹")
        previous_button.setObjectName("CalNav")
        previous_button.setCursor(Qt.CursorShape.PointingHandCursor)
        previous_button.clicked.connect(lambda: self._change_month(-1))
        next_button = QPushButton("›")
        next_button.setObjectName("CalNav")
        next_button.setCursor(Qt.CursorShape.PointingHandCursor)
        next_button.clicked.connect(lambda: self._change_month(1))
        header.addWidget(previous_button)
        header.addWidget(next_button)
        outer.addLayout(header)

        weekday_row = QHBoxLayout()
        weekday_row.setSpacing(4)
        for letter in _CALENDAR_WEEKDAYS:
            weekday_label = QLabel(letter)
            weekday_label.setObjectName("CalWeekday")
            weekday_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            weekday_label.setFixedWidth(32)
            weekday_row.addWidget(weekday_label)
        outer.addLayout(weekday_row)

        self.grid = QGridLayout()
        self.grid.setSpacing(4)
        outer.addLayout(self.grid)

        footer = QHBoxLayout()
        today_button = QPushButton("HOJE")
        today_button.setObjectName("CalFooter")
        today_button.setCursor(Qt.CursorShape.PointingHandCursor)
        today_button.clicked.connect(self._pick_today)
        footer.addWidget(today_button)
        footer.addStretch()
        cancel_button = QPushButton("CANCELAR")
        cancel_button.setObjectName("CalFooter")
        cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_button.clicked.connect(self.close)
        ok_button = QPushButton("OK")
        ok_button.setObjectName("CalFooter")
        ok_button.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_button.clicked.connect(self._confirm)
        footer.addWidget(cancel_button)
        footer.addWidget(ok_button)
        outer.addLayout(footer)

        self._render_days()

    def _change_month(self, delta: int) -> None:
        month = self._view_month + delta
        year = self._view_year
        if month < 1:
            month, year = 12, year - 1
        elif month > 12:
            month, year = 1, year + 1
        self._view_year, self._view_month = year, month
        self._render_days()

    def _pick_today(self) -> None:
        today = QDate.currentDate()
        self._view_year, self._view_month = today.year(), today.month()
        self._pending = today
        self._render_days()

    def _render_days(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.month_label.setText(f"{_CALENDAR_MONTHS[self._view_month - 1]} de {self._view_year}")
        first_day = QDate(self._view_year, self._view_month, 1)
        start_column = first_day.dayOfWeek() % 7  # Qt: Monday=1..Sunday=7 -> Sunday=0 to match S M T W T F S
        today = QDate.currentDate()
        row, column = 0, start_column
        for day in range(1, first_day.daysInMonth() + 1):
            current = QDate(self._view_year, self._view_month, day)
            day_button = QPushButton(str(day))
            day_button.setCursor(Qt.CursorShape.PointingHandCursor)
            if current == self._pending:
                day_button.setObjectName("CalDaySelected")
            elif current == today:
                day_button.setObjectName("CalToday")
            else:
                day_button.setObjectName("CalDay")
            day_button.clicked.connect(lambda _checked=False, value=current: self._pick(value))
            self.grid.addWidget(day_button, row, column)
            column += 1
            if column > 6:
                column = 0
                row += 1

    def _pick(self, value: QDate) -> None:
        self._pending = value
        self._render_days()

    def _confirm(self) -> None:
        self.dateSelected.emit(self._pending)
        self.close()

    def show_below(self, anchor: QWidget) -> None:
        anchor_rect = anchor.rect()
        target = anchor.mapToGlobal(anchor_rect.bottomLeft())
        self.adjustSize()
        screen = anchor.screen().availableGeometry() if anchor.screen() else None
        if screen is not None and target.y() + self.height() > screen.bottom():
            target = anchor.mapToGlobal(anchor_rect.topLeft())
            target.setY(target.y() - self.height() - 4)
        self.move(target.x(), target.y() + 4)
        self.show()


class DateField(QPushButton):
    """Read-only date selector that opens a compact popover calendar."""

    dateChanged = Signal(QDate)

    def __init__(self, value: str | QDate | None = None) -> None:
        if isinstance(value, str):
            selected = QDate.fromString(value, "yyyy-MM-dd")
        elif isinstance(value, QDate):
            selected = value
        else:
            selected = QDate.currentDate()
        if not selected.isValid():
            selected = QDate.currentDate()
        super().__init__()
        self._date = selected
        self.setObjectName("DateField")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Clique para escolher dia, mês e ano no calendário.")
        self.clicked.connect(self._open_calendar)
        self._update_text()

    def _update_text(self) -> None:
        self.setText(f'{self._date.toString("dd/MM/yyyy")}   ▾')
        self.setAccessibleName(f'Data {self._date.toString("dd/MM/yyyy")}. Clique para abrir o calendário')

    def date(self) -> QDate:
        return QDate(self._date)

    def setDate(self, value: QDate) -> None:
        if value.isValid() and value != self._date:
            self._date = QDate(value)
            self._update_text()
            self.dateChanged.emit(self.date())

    def _open_calendar(self) -> None:
        popover = MiniCalendar(self._date, self)
        popover.dateSelected.connect(self.setDate)
        popover.show_below(self)

    def iso_date(self) -> str:
        return self.date().toString("yyyy-MM-dd")


class CategoryPopup(QWidget):
    """Scrollable, filterable list of categories anchored under a field."""

    categoryPicked = Signal(str)

    def __init__(self, categories: list[str], anchor: QWidget) -> None:
        super().__init__(anchor, Qt.WindowType.Popup)
        self.setObjectName("CategoryPopup")
        self._categories = categories
        self.setStyleSheet(
            """
            QWidget#CategoryPopup { background: #171120; border: 1px solid #33283e; border-radius: 12px; }
            QListWidget {
                background: transparent; border: 0; outline: 0; padding: 4px;
            }
            QListWidget::item {
                color: #d9d2e2; padding: 8px 10px; border-radius: 8px; font-size: 12px;
            }
            QListWidget::item:hover { background: #251a34; }
            QListWidget::item:selected { background: #2c2040; color: white; }
            """
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(0)
        self.list = QListWidget()
        self.list.setUniformItemSizes(True)
        self.list.itemClicked.connect(self._pick)
        outer.addWidget(self.list)

    def refresh(self, text: str, width: int) -> None:
        self.list.clear()
        query = text.strip()
        folded = query.casefold()
        matches = [name for name in self._categories if folded in name.casefold()] if folded else list(self._categories)
        exact = any(name.casefold() == folded for name in self._categories)
        if query and not exact:
            create_item = QListWidgetItem(f'+ Criar categoria “{query}”')
            create_item.setData(Qt.ItemDataRole.UserRole, query)
            create_font = create_item.font()
            create_font.setBold(True)
            create_item.setFont(create_font)
            create_item.setForeground(QColor("#ad94ff"))
            self.list.addItem(create_item)
        if not matches and not query:
            matches = list(self._categories)
        for name in matches:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.list.addItem(item)
        row_height = 34
        visible_rows = min(max(self.list.count(), 1), 7)
        self.setFixedWidth(width)
        self.list.setFixedHeight(row_height * visible_rows + 8)
        self.adjustSize()

    def _pick(self, item: QListWidgetItem) -> None:
        self.categoryPicked.emit(item.data(Qt.ItemDataRole.UserRole))
        self.close()

    def show_below(self, anchor: QWidget) -> None:
        anchor_rect = anchor.rect()
        target = anchor.mapToGlobal(anchor_rect.bottomLeft())
        screen = anchor.screen().availableGeometry() if anchor.screen() else None
        if screen is not None and target.y() + self.height() > screen.bottom():
            target = anchor.mapToGlobal(anchor_rect.topLeft())
            target.setY(target.y() - self.height() - 4)
        self.move(target.x(), target.y() + 4)
        self.show()


class CategoryField(QLineEdit):
    """Smart category input: click to browse, type to filter or create.

    Behaves like a plain text field (any value can be typed and saved),
    but offers the existing catalog as a scrollable, filterable list so the
    person rarely needs to type a whole category name from scratch.
    """

    def __init__(self, categories_provider: Callable[[], list[str]], placeholder: str, value: str = "") -> None:
        super().__init__(value)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self._categories_provider = categories_provider
        self._popup: CategoryPopup | None = None
        self.textEdited.connect(self._on_text_edited)

    def mousePressEvent(self, event: Any) -> None:
        super().mousePressEvent(event)
        self._open_popup()

    def _open_popup(self) -> None:
        if self._popup is not None and self._popup.isVisible():
            return
        self._popup = CategoryPopup(self._categories_provider(), self)
        self._popup.categoryPicked.connect(self._apply_pick)
        self._popup.refresh(self.text(), self.width())
        self._popup.show_below(self)

    def _on_text_edited(self, text: str) -> None:
        if self._popup is None or not self._popup.isVisible():
            self._popup = CategoryPopup(self._categories_provider(), self)
            self._popup.categoryPicked.connect(self._apply_pick)
            self._popup.refresh(text, self.width())
            self._popup.show_below(self)
        else:
            self._popup.refresh(text, self.width())

    def _apply_pick(self, value: str) -> None:
        self.setText(value)
        self.setFocus()


def select_combo_data(combo: QComboBox, value: Any) -> None:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


def notes_field(placeholder: str, value: str = "") -> QTextEdit:
    field = QTextEdit(value)
    field.setPlaceholderText(placeholder)
    field.setMaximumHeight(76)
    return field


def add_form_field(grid: QGridLayout, index: int, title: str, widget: QWidget) -> None:
    row, column = divmod(index, 2)
    field = QVBoxLayout()
    field.setSpacing(5)
    field.addWidget(label(title, "FieldLabel"))
    field.addWidget(widget)
    grid.addLayout(field, row, column)


def standard_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    for column in range(1, len(headers)):
        table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
    table.verticalHeader().setVisible(False)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    return table


def action_widget(edit_action: Callable[[], None], delete_action: Callable[[], None]) -> QWidget:
    widget = QWidget()
    widget.setMinimumWidth(118)
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(3, 2, 3, 2)
    layout.setSpacing(4)
    edit = QPushButton("Editar")
    edit.setObjectName("SmallButton")
    edit.setMinimumWidth(52)
    edit.clicked.connect(edit_action)
    delete = QPushButton("Excluir")
    delete.setObjectName("DangerButton")
    delete.setMinimumWidth(52)
    delete.clicked.connect(delete_action)
    layout.addWidget(edit)
    layout.addWidget(delete)
    return widget


def confirm_delete(parent: QWidget, subject: str) -> bool:
    answer = QMessageBox.question(
        parent,
        "Confirmar exclusão",
        f"Excluir {subject}? Esta ação não pode ser desfeita.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes

