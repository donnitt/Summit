from __future__ import annotations

import csv
import math
import re
import sqlite3
from datetime import date, datetime
from typing import Any, Callable

from PySide6.QtCore import QDate, QEvent, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
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
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from summit.database import Database
from summit.finance import brl, calculate, due_urgency, set_values_hidden, values_hidden
from summit.theme import DEFAULT_ACCENT, build_stylesheet


PURPLE = "#9b7cff"
GREEN = "#4bd7b2"
ORANGE = "#ff9d66"
BLUE = "#64a8ff"
CATEGORY_COLORS = (PURPLE, GREEN, ORANGE, BLUE, "#e96e95", "#756782")


def app_icon(size: int = 64) -> QIcon:
    """Official Summit brand icon: purple rounded square with a white peak (▲)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    radius = size * 0.22
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#8562ef"))
    painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.setBrush(QColor("#ffffff"))
    peak = QPainterPath()
    peak.moveTo(size * 0.5, size * 0.2)
    peak.lineTo(size * 0.82, size * 0.78)
    peak.lineTo(size * 0.18, size * 0.78)
    peak.closeSubpath()
    painter.drawPath(peak)
    painter.end()
    return QIcon(pixmap)


def label(text: str, object_name: str = "", word_wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if object_name:
        widget.setObjectName(object_name)
    widget.setWordWrap(word_wrap)
    return widget


def text_field(placeholder: str, value: str = "") -> QLineEdit:
    field = QLineEdit(value)
    field.setPlaceholderText(placeholder)
    field.setClearButtonEnabled(True)
    return field


def eye_icon(closed: bool = False, color: str = "#a79bb2", size: int = 16) -> QIcon:
    """A small hand-drawn, line-only eye icon (open or crossed-out/closed)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.1, size * 0.09))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    margin = size * 0.08
    # Wider, almond-shaped eye for a more organic look (not stretched).
    rect = QRectF(margin, size * 0.26, size - margin * 2, size * 0.48)
    lid = QPainterPath()
    lid.moveTo(rect.left(), rect.center().y())
    lid.cubicTo(
        rect.left() + rect.width() * 0.22, rect.top(),
        rect.right() - rect.width() * 0.22, rect.top(),
        rect.right(), rect.center().y(),
    )
    lid.cubicTo(
        rect.right() - rect.width() * 0.22, rect.bottom(),
        rect.left() + rect.width() * 0.22, rect.bottom(),
        rect.left(), rect.center().y(),
    )
    painter.drawPath(lid)
    if not closed:
        pupil_radius = size * 0.11
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(rect.center().x(), rect.center().y()), pupil_radius, pupil_radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(rect.center().x(), rect.center().y()), pupil_radius, pupil_radius)
    else:
        painter.drawLine(
            QPointF(margin * 1.2, size * 0.78),
            QPointF(size - margin * 1.2, size * 0.22),
        )
    painter.end()
    return QIcon(pixmap)


_AMOUNT_RUN = re.compile(r"[0-9][0-9.,]*")


def mask_amount(text: str) -> str:
    """Replace the numeric portion of an already-formatted value with dots."""
    if _AMOUNT_RUN.search(text):
        return _AMOUNT_RUN.sub("••••", text, count=1)
    return "••••"


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

    def keyPressEvent(self, event: Any) -> None:
        # With all text selected, Backspace/Delete must clear the value
        # instead of being swallowed by the spin-box validation.
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) and self.selectedText():
            self.setValue(0)
            self.lineEdit().clear()
            event.accept()
            return
        super().keyPressEvent(event)


def money_field(value: float = 0, allow_negative: bool = False) -> MoneyField:
    field = MoneyField()
    field.setRange(-999_999_999 if allow_negative else 0, 999_999_999)
    field.setDecimals(2)
    field.setGroupSeparatorShown(True)
    field.setPrefix("R$ ")
    field.setKeyboardTracking(False)
    field.setValue(float(value))
    field.setButtonSymbols(QAbstractSpinBox.NoButtons)
    return field


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


def select_combo_data(combo: QComboBox, value: Any) -> None:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


DEFAULT_CATEGORIES = (
    "Transporte", "Autocuidado", "Alimentação", "Lazer", "Moradia",
    "Saúde", "Educação", "Serviços", "Contratos", "Vendas",
)


class CategoryCombo(QComboBox):
    """Editable combo that filters categories while typing and offers
    instant creation of a brand-new category ("Criar categoria …")."""

    def __init__(self, database: Database, kind: str = "expense", value: str = "") -> None:
        super().__init__()
        self.database = database
        self.kind = kind
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._reload()
        if value:
            self.setCurrentText(value)
        self.view().installEventFilter(self)
        self.view().pressed.connect(self._on_item_pressed)
        self.lineEdit().textEdited.connect(lambda _text: QTimer.singleShot(0, self._suggest))

    def _reload(self) -> None:
        current = self.currentText()
        self.clear()
        for item in self.database.categories(self.kind):
            self.addItem(item["name"])
        if current:
            self.setCurrentText(current)

    def refresh(self) -> None:
        self._reload()

    def _on_item_pressed(self, index: Any) -> None:
        text = self.view().model().data(index, Qt.ItemDataRole.DisplayRole) or ""
        self.hidePopup()
        if text.startswith("✚ Criar categoria “"):
            new_name = text.split("“", 1)[1].rstrip("”")
            try:
                self.database.add_category(new_name, self.kind)
            except (ValueError, sqlite3.Error):
                pass
            self._reload()
            self.setCurrentText(new_name)
        else:
            self.setCurrentText(text)

    def current_category(self) -> str:
        return self.currentText().strip()

    def eventFilter(self, source: Any, event: Any) -> bool:
        if event.type() == QtCore.QEvent.Type.KeyPress and source is self.view():
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.view().currentIndex().isValid():
                    self.view().pressed.emit(self.view().currentIndex())
                else:
                    self.hidePopup()
                return True
            if event.key() == Qt.Key.Key_Backspace:
                # Recompute suggestions on deletion before default handling.
                QTimer.singleShot(0, self._suggest)
        return super().eventFilter(source, event)

    def keyPressEvent(self, event: Any) -> None:
        super().keyPressEvent(event)
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            QTimer.singleShot(0, self._suggest)

    def _suggest(self) -> None:
        """Filter the dropdown to matching categories; when the typed name
        does not exist yet, offer instant creation as the first item."""
        if not self.view().isVisible():
            return
        text = self.currentText().strip()
        names = [item["name"] for item in self.database.categories(self.kind)]
        matches = [name for name in names if text.casefold() in name.casefold()] if text else names
        model = self.model()
        model.removeRows(0, model.rowCount())
        exists = text.casefold() in (name.casefold() for name in names)
        if text and not exists:
            self.addItem(f"✚ Criar categoria “{text}”")
        for name in matches:
            self.addItem(name)
        self.view().setCurrentIndex(self.model().index(0, 0))


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
    return ConfirmOverlay.ask(
        parent,
        "Confirmar exclusão",
        f"Excluir {subject}? Esta ação não pode ser desfeita.",
        confirm_text="Excluir",
        danger=True,
    )


class CashFlowChart(QWidget):
    def __init__(self, values: list[dict[str, Any]]) -> None:
        super().__init__()
        self.values = values
        self.setMinimumHeight(235)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = self.rect().adjusted(42, 15, -18, -31)
        if area.width() <= 0 or area.height() <= 0:
            return
        maximum = max([item[key] for item in self.values for key in ("income", "expense")] + [1000])
        maximum = math.ceil(maximum / 2000) * 2000

        painter.setFont(QFont("Segoe UI", 8))
        for index in range(5):
            y = area.top() + index * area.height() / 4
            painter.setPen(QPen(QColor("#2a2233"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(area.left(), int(y), area.right(), int(y))
            value = maximum * (1 - index / 4)
            painter.setPen(QColor("#756b80"))
            axis_label = "••" if values_hidden() else f"{value / 1000:.0f}k"
            painter.drawText(0, int(y - 8), 36, 16, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, axis_label)

        points_by_key: dict[str, list[QPointF]] = {"income": [], "expense": []}
        step = area.width() / max(len(self.values) - 1, 1)
        for index, item in enumerate(self.values):
            x = area.left() + index * step
            painter.setPen(QColor("#716778"))
            painter.drawText(int(x - 18), area.bottom() + 4, 36, 14, Qt.AlignmentFlag.AlignCenter, item["label"])
            range_text = item.get("range", "")
            if range_text and not values_hidden():
                painter.setPen(QColor("#5d5468"))
                painter.drawText(int(x - 24), area.bottom() + 17, 48, 12, Qt.AlignmentFlag.AlignCenter, range_text)
            for key in points_by_key:
                y = area.bottom() - (float(item[key]) / maximum) * area.height()
                points_by_key[key].append(QPointF(x, y))

        self._draw_series(painter, area, points_by_key["income"], QColor(PURPLE), QColor(155, 124, 255, 45))
        self._draw_series(painter, area, points_by_key["expense"], QColor(ORANGE), QColor(255, 157, 102, 18))

    @staticmethod
    def _draw_series(painter: QPainter, area: Any, points: list[QPointF], color: QColor, fill: QColor) -> None:
        if not points:
            return
        path = QPainterPath(points[0])
        for index in range(1, len(points)):
            previous = points[index - 1]
            current = points[index]
            middle = (previous.x() + current.x()) / 2
            path.cubicTo(middle, previous.y(), middle, current.y(), current.x(), current.y())
        fill_path = QPainterPath(path)
        fill_path.lineTo(points[-1].x(), area.bottom())
        fill_path.lineTo(points[0].x(), area.bottom())
        fill_path.closeSubpath()
        painter.fillPath(fill_path, fill)
        painter.setPen(QPen(color, 2.4))
        painter.drawPath(path)


class DonutChart(QWidget):
    def __init__(self, categories: list[tuple[str, float]], total: float) -> None:
        super().__init__()
        self.categories = categories
        self.total = total
        self.setMinimumSize(175, 175)

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width(), self.height()) - 32
        chart = QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)
        painter.setPen(Qt.PenStyle.NoPen)
        if not self.categories or self.total <= 0:
            painter.setBrush(QColor("#30273a"))
            painter.drawEllipse(chart)
        else:
            start = 90 * 16
            for index, (_name, amount) in enumerate(self.categories):
                span = -int((amount / self.total) * 360 * 16)
                painter.setBrush(QColor(CATEGORY_COLORS[index % len(CATEGORY_COLORS)]))
                painter.drawPie(chart, start, span)
                start += span
        hole_size = size * 0.61
        hole = QRectF((self.width() - hole_size) / 2, (self.height() - hole_size) / 2, hole_size, hole_size)
        painter.setBrush(QColor("#171120"))
        painter.drawEllipse(hole)
        painter.setPen(QColor("#776d82"))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(hole.adjusted(0, 22, 0, 0), Qt.AlignmentFlag.AlignHCenter, "Total")
        painter.setPen(QColor("#f4f0f8"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(hole.adjusted(0, 42, 0, 0), Qt.AlignmentFlag.AlignHCenter, brl(self.total))


class MetricCard(QFrame):
    """A dashboard metric tile with its own eye toggle.

    ``value`` should be the value formatted as if values were visible
    (i.e. computed with ``hidden=False``) — this card tracks its own
    hidden state, seeded from the global privacy toggle but afterwards
    fully independent of it, so a single card can be shown or hidden
    on its own without affecting the rest of the app.
    """

    def __init__(self, title: str, value: str, accent: str, object_name: str, detail: str) -> None:
        super().__init__()
        self.setObjectName(object_name)
        self.setMinimumHeight(137)
        self.setMaximumHeight(150)
        self._value = value
        self._hidden = values_hidden()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 15, 18, 15)
        head = QHBoxLayout()
        head.addWidget(label(title, "Muted"))
        head.addStretch()
        self._eye_button = QPushButton()
        self._eye_button.setObjectName("VisibilityToggle")
        self._eye_button.setIconSize(QSize(15, 15))
        self._eye_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._eye_button.setFlat(True)
        self._eye_button.clicked.connect(self._toggle)
        head.addWidget(self._eye_button)
        layout.addLayout(head)
        self._value_label = label("", "MetricValue")
        layout.addWidget(self._value_label)
        layout.addStretch()
        detail_label = label(detail, "Tiny")
        detail_label.setStyleSheet(f"color: {accent};")
        layout.addWidget(detail_label)
        self._render()

    def _render(self) -> None:
        self._value_label.setText(mask_amount(self._value) if self._hidden else self._value)
        # Closed/focused state uses the brand purple; open uses neutral gray.
        self._eye_button.setIcon(eye_icon(closed=self._hidden, color="#8562ef" if self._hidden else "#a79bb2"))
        self._eye_button.setToolTip("Mostrar este valor" if self._hidden else "Ocultar este valor")

    def _toggle(self) -> None:
        self._hidden = not self._hidden
        self._render()


class Panel(QFrame):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("Panel")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 16)
        header = QHBoxLayout()
        copy = QVBoxLayout()
        copy.setSpacing(3)
        copy.addWidget(label(title, "PanelTitle"))
        if subtitle:
            copy.addWidget(label(subtitle, "Tiny"))
        header.addLayout(copy)
        header.addStretch()
        self.body.addLayout(header)


class DashboardPage(QWidget):
    def __init__(
        self,
        snapshot: dict[str, Any],
        add_transaction: Callable[[], None],
        confirm_receipt: Callable[[dict[str, Any]], None],
        edit_receipt: Callable[[dict[str, Any]], None],
        period: str,
        change_period: Callable[[str], None],
    ) -> None:
        super().__init__()
        stats = calculate(snapshot, period=period)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(14)

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
            # Force legible fixed colors on the selected state regardless of
            # the active theme (mirrors the Escuro/Claro fix above).
            option_button.setStyleSheet(
                f"QPushButton:checked{{background:{DEFAULT_ACCENT};color:#ffffff;}}"
            )
            option_button.clicked.connect(
                lambda _checked=False, selected=option_value: change_period(selected)
            )
            period_buttons.append(option_button)
            switch_layout.addWidget(option_button)
        period_bar.addWidget(period_switch)
        page.addLayout(period_bar)

        metrics = QGridLayout()
        metrics.setSpacing(13)
        cards = [
            MetricCard("Saldo disponível", brl(stats["balance"], hidden=False), PURPLE, "MetricPurple", "Visão consolidada"),
            MetricCard(f'Entradas {stats["period_label"]}', brl(stats["income"], hidden=False), GREEN, "MetricGreen", stats["period_title"]),
            MetricCard(f'Saídas {stats["period_label"]}', brl(stats["expense"], hidden=False), ORANGE, "MetricOrange", stats["period_title"]),
            MetricCard("A receber", brl(stats["to_receive"], hidden=False), BLUE, "MetricBlue", f'{stats["pending_income_count"]} lançamento(s) previsto(s)'),
        ]
        for index, card in enumerate(cards):
            metrics.addWidget(card, 0, index)
        page.addLayout(metrics)

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
        cash = Panel("Fluxo de caixa", stats["chart_subtitle"])
        legend = QHBoxLayout()
        accumulated = sum(item["income"] - item["expense"] for item in stats["cash_flow"])
        legend.addWidget(label(f"Resultado acumulado  {brl(accumulated)}", "Tiny"))
        legend.addStretch()
        income_legend = label("● Entradas")
        income_legend.setStyleSheet(f"color: {PURPLE}; font-size: 10px;")
        expense_legend = label("● Saídas")
        expense_legend.setStyleSheet(f"color: {ORANGE}; font-size: 10px;")
        legend.addWidget(income_legend)
        legend.addWidget(expense_legend)
        cash.body.addLayout(legend)
        cash.body.addWidget(CashFlowChart(stats["cash_flow"]))
        charts.addWidget(cash, 7)

        categories_panel = Panel("Gastos por categoria", f'Distribuição {stats["distribution_label"]}')
        category_content = QHBoxLayout()
        category_content.addWidget(DonutChart(stats["categories"], stats["expense"]), 1)
        list_layout = QVBoxLayout()
        list_layout.addStretch()
        for index, (name, amount) in enumerate(stats["categories"][:5]):
            item = QHBoxLayout()
            dot = label("●")
            dot.setStyleSheet(f"color: {CATEGORY_COLORS[index % len(CATEGORY_COLORS)]};")
            item.addWidget(dot)
            item.addWidget(label(name, "Tiny"))
            item.addStretch()
            percentage = round(amount / stats["expense"] * 100) if stats["expense"] else 0
            item.addWidget(label(f"{brl(amount)} · {percentage}%", "Tiny"))
            list_layout.addLayout(item)
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
        projection.body.addWidget(label(f'+ A receber  {brl(stats["to_receive"])}', "Positive"))
        projection.body.addWidget(label(f'+ Entradas fixas {brl(stats["fixed_income_total"])}', "Positive"))
        projection.body.addWidget(label(f'− A pagar     {brl(stats["to_pay"])}', "Orange"))
        projection.body.addWidget(label(f'− Custos fixos {brl(stats["fixed_total"])}', "Orange"))
        projection.body.addSpacing(8)
        projection.body.addWidget(label(f'Livre após fixos  {brl(stats["available_after_fixed"])}', "Purple"))
        projection.body.addStretch()
        projection.body.addWidget(label("●  Lançamentos futuros e valores fixos estão nesta projeção.", "Tiny", True))
        lower.addWidget(projection, 3)
        page.addLayout(lower)


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
        for item in items:
            card = MovementCard(item)
            card.clicked.connect(lambda current=item: edit_action(current))
            cards.addWidget(card)
        if not items:
            cards.addWidget(label("Nenhum lançamento aqui por enquanto.", "EmptyState", True))
        cards.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)


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
    ) -> None:
        super().__init__()
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(label("Movimentações organizadas", "PageTitle"))
        page.addWidget(label(
            "Tudo visível em um único quadro. Clique em qualquer cartão para editar ou excluir.",
            "Muted",
            True,
        ))
        page.addSpacing(12)

        transactions = snapshot["transactions"]
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
            visibility = QPushButton()
            visibility.setObjectName("VisibilityToggle")
            visibility.setIcon(eye_icon(closed=is_hidden, color="#8562ef" if is_hidden else "#a79bb2"))
            visibility.setIconSize(QSize(15, 15))
            visibility.setFlat(True)
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
            "Saldo devedor", brl(sum(float(item["outstanding_amount"]) for item in open_debts), hidden=False),
            ORANGE, "MetricOrange", f"{len(open_debts)} dívida(s) aberta(s)",
        ), 0, 0)
        totals.addWidget(MetricCard(
            "Vencidas", brl(sum(float(item["outstanding_amount"]) for item in overdue), hidden=False),
            "#ef7185", "MetricOrange", f"{len(overdue)} precisa(m) de atenção",
        ), 0, 1)
        totals.addWidget(MetricCard(
            "Próximos 30 dias", brl(due_soon_amount, hidden=False),
            BLUE, "MetricBlue", f"{len(due_soon)} parcela(s) estimada(s)",
        ), 0, 2)
        totals.addWidget(MetricCard(
            "Valor já pago", brl(sum(float(item["total_amount"]) - float(item["outstanding_amount"]) for item in debts), hidden=False),
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
    ) -> None:
        super().__init__()
        stats = calculate(snapshot)
        goals = snapshot["goals"]
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
        metrics.addWidget(MetricCard("Reservado nas metas", brl(saved, hidden=False), PURPLE, "MetricPurple", f"Objetivo total: {brl(total_target, hidden=False)}"), 0, 0)
        metrics.addWidget(MetricCard("Aportes planejados", brl(planned_monthly, hidden=False), GREEN, "MetricGreen", "Valor mensal definido por você"), 0, 1)
        metrics.addWidget(MetricCard("Custos fixos", brl(stats["fixed_total"], hidden=False), ORANGE, "MetricOrange", "Compromisso mensal recorrente"), 0, 2)
        metrics.addWidget(MetricCard("Resultado do mês", brl(stats["result"], hidden=False), BLUE, "MetricBlue", f'Taxa de economia: {stats["savings_rate"]:.0f}%'), 0, 3)
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
        metrics.addWidget(MetricCard("Valor atual", brl(total, hidden=False), PURPLE, "MetricPurple", "Patrimônio investido"), 0, 0)
        metrics.addWidget(MetricCard("Total aplicado", brl(invested, hidden=False), BLUE, "MetricBlue", "Custo acumulado"), 0, 1)
        metrics.addWidget(MetricCard("Resultado", brl(result, hidden=False), GREEN if result >= 0 else ORANGE, "MetricGreen" if result >= 0 else "MetricOrange", "Ganho ou perda da carteira"), 0, 2)
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


class AccountDialog(QDialog):
    saved = Signal()

    def __init__(
        self,
        database: Database,
        parent: QWidget | None = None,
        account: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.account_data = account
        self.setWindowTitle(("Editar" if account else "Nova") + " conta · Summit")
        self.setModal(True)
        self.setMinimumWidth(540)
        source = account or {}
        form = QVBoxLayout(self)
        form.setContentsMargins(26, 24, 26, 24)
        form.setSpacing(10)
        form.addWidget(label("Editar conta" if account else "Nova conta", "PageTitle"))
        form.addWidget(label(
            "O saldo-base é o ponto de partida. As movimentações confirmadas formam o saldo atual.",
            "Muted", True,
        ))
        self.name = text_field("Ex.: Conta principal", source.get("name", ""))
        self.account_type = QComboBox()
        self.account_type.setEditable(True)
        self.account_type.addItems(("Conta corrente", "Conta digital", "Poupança", "Dinheiro", "Carteira"))
        self.account_type.setCurrentText(source.get("account_type", "Conta corrente"))
        self.initial_balance = money_field(float(source.get("initial_balance", 0)), allow_negative=True)
        grid = QGridLayout()
        fields = [
            ("Nome da conta", self.name), ("Tipo", self.account_type),
            ("Saldo-base", self.initial_balance),
        ]
        for index, (title, widget) in enumerate(fields):
            add_form_field(grid, index, title, widget)
        form.addLayout(grid)
        form.addWidget(label(
            "Atenção: alterar o saldo-base recalcula o saldo disponível sem apagar o histórico.",
            "AccountHint", True,
        ))
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("Secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Salvar alterações" if account else "Criar conta")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        form.addLayout(buttons)
        add_frameless_dialog_bar(self)

    def _save(self) -> None:
        try:
            values = dict(
                name=self.name.text(), account_type=self.account_type.currentText(),
                initial_balance=self.initial_balance.value(),
            )
            if self.account_data:
                self.database.update_account(self.account_data["id"], **values)
            else:
                self.database.add_account(**values)
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Confira os dados", str(error))
            return
        self.saved.emit()
        self.accept()


class DebtDialog(QDialog):
    saved = Signal()

    def __init__(
        self,
        database: Database,
        parent: QWidget | None = None,
        debt: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.debt = debt
        self.setWindowTitle(("Editar" if debt else "Nova") + " dívida · Summit")
        self.setModal(True)
        self.setMinimumWidth(590)
        source = debt or {}
        form = QVBoxLayout(self)
        form.setContentsMargins(26, 24, 26, 24)
        form.setSpacing(10)
        form.addWidget(label("Editar dívida" if debt else "Nova dívida", "PageTitle"))
        form.addWidget(label("Registre o saldo atual, as parcelas e a próxima data importante.", "Muted"))

        self.description = text_field("Ex.: Financiamento do notebook", source.get("description", ""))
        self.creditor = text_field("Ex.: Banco ou loja", source.get("creditor", ""))
        self.category = CategoryCombo(database, "expense", source.get("category", ""))
        self.total = money_field(float(source.get("total_amount", 0)))
        self.outstanding = money_field(float(source.get("outstanding_amount", 0)))
        if not debt:
            self.total.valueChanged.connect(self.outstanding.setValue)
        self.due_date = DateField(source.get("due_date"))
        self.installments_total = QSpinBox()
        self.installments_total.setRange(1, 999)
        self.installments_total.setValue(int(source.get("installments_total", 1)))
        self.installments_paid = QSpinBox()
        self.installments_paid.setRange(0, self.installments_total.value())
        self.installments_paid.setValue(int(source.get("installments_paid", 0)))
        self.installments_total.valueChanged.connect(self.installments_paid.setMaximum)
        self.scope = QComboBox()
        self.scope.addItem("Pessoal", "personal")
        self.scope.addItem("Trabalho", "work")
        select_combo_data(self.scope, source.get("scope", "personal"))
        self.notes = notes_field("Taxas, número do contrato ou observações", source.get("notes", ""))

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        fields = [
            ("Dívida", self.description), ("Credor", self.creditor),
            ("Categoria", self.category), ("Uso", self.scope),
            ("Valor total", self.total), ("Saldo devedor", self.outstanding),
            ("Próximo vencimento", self.due_date), ("Total de parcelas", self.installments_total),
            ("Parcelas pagas", self.installments_paid),
        ]
        for index, (title, widget) in enumerate(fields):
            add_form_field(grid, index, title, widget)
        form.addLayout(grid)
        form.addWidget(label("Observações", "FieldLabel"))
        form.addWidget(self.notes)
        buttons = QHBoxLayout()
        if debt:
            delete = QPushButton("Excluir dívida")
            delete.setObjectName("DangerAction")
            delete.clicked.connect(self._delete)
            buttons.addWidget(delete)
            if debt["status"] == "open":
                settle = QPushButton("Marcar como quitada")
                settle.setObjectName("Secondary")
                settle.clicked.connect(self._settle)
                buttons.addWidget(settle)
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("Secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Salvar dívida")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        form.addLayout(buttons)
        add_frameless_dialog_bar(self)

    def _values(self) -> dict[str, Any]:
        return dict(
            description=self.description.text(), creditor=self.creditor.text(),
            category=self.category.current_category(), total_amount=self.total.value(),
            outstanding_amount=self.outstanding.value(), due_date=self.due_date.iso_date(),
            installments_total=self.installments_total.value(),
            installments_paid=self.installments_paid.value(), scope=self.scope.currentData(),
            notes=self.notes.toPlainText(),
        )

    def _save(self) -> None:
        try:
            if self.debt:
                self.database.update_debt(self.debt["id"], **self._values())
            else:
                self.database.add_debt(**self._values())
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Confira os dados", str(error))
            return
        self.saved.emit()
        self.accept()

    def _settle(self) -> None:
        if not ConfirmOverlay.ask(
            self, "Confirmar quitação", "Confirmar que esta dívida foi totalmente quitada?",
            confirm_text="Quitar dívida",
        ):
            return
        self.outstanding.setValue(0)
        self.installments_paid.setValue(self.installments_total.value())
        self._save()

    def _delete(self) -> None:
        if not self.debt or not confirm_delete(self, f'a dívida “{self.debt["description"]}”'):
            return
        try:
            self.database.delete_debt(self.debt["id"])
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Não foi possível excluir", str(error))
            return
        self.saved.emit()
        self.accept()


class TransactionDialog(QDialog):
    saved = Signal()

    def __init__(
        self,
        database: Database,
        parent: QWidget | None = None,
        transaction: dict[str, Any] | None = None,
        default_kind: str = "expense",
        default_status: str = "paid",
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.transaction = transaction
        self.setWindowTitle(("Editar" if transaction else "Nova") + " movimentação · Summit")
        self.setModal(True)
        self.setMinimumWidth(570)
        form = QVBoxLayout(self)
        form.setContentsMargins(26, 24, 26, 24)
        form.setSpacing(10)
        form.addWidget(label("Editar lançamento" if transaction else "Novo lançamento", "PageTitle"))
        form.addWidget(label("Registre com clareza; os textos de exemplo somem assim que você digita.", "Muted"))

        self.kind = QComboBox()
        self.kind.addItem("Gasto", "expense")
        self.kind.addItem("Entrada", "income")
        self.description = text_field("Ex.: Sessão de tatuagem")
        self.amount = money_field()
        self.category = CategoryCombo(database, "expense")
        self.transaction_date = DateField()
        self.status = QComboBox()
        self.status.addItem("Concluído", "paid")
        self.status.addItem("Previsto", "pending")
        self.scope = QComboBox()
        self.scope.addItem("Trabalho", "work")
        self.scope.addItem("Pessoal", "personal")
        self.account = QComboBox()
        for account in database.accounts():
            self.account.addItem(account["name"], account["id"])
        self.notes = notes_field("Observações opcionais, cliente, referência ou detalhes do pagamento")

        source = transaction or {}
        self.description.setText(source.get("description", ""))
        self.category.setCurrentText(source.get("category", ""))
        self.amount.setValue(float(source.get("amount", 0)))
        self.transaction_date.setDate(
            QDate.fromString(source["transaction_date"], "yyyy-MM-dd")
            if source.get("transaction_date") else QDate.currentDate()
        )
        self.notes.setPlainText(source.get("notes", ""))
        select_combo_data(self.kind, source.get("kind", default_kind))
        select_combo_data(self.status, source.get("status", default_status))
        select_combo_data(self.scope, source.get("scope", "work"))
        if source.get("account_id") is not None:
            select_combo_data(self.account, source["account_id"])

        fields = [
            ("Tipo", self.kind), ("Descrição", self.description), ("Valor", self.amount),
            ("Categoria", self.category), ("Data", self.transaction_date),
            ("Situação", self.status), ("Uso", self.scope), ("Conta Corrente", self.account),
        ]
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for index, (field_name, widget) in enumerate(fields):
            add_form_field(grid, index, field_name, widget)
        form.addLayout(grid)
        form.addWidget(label("Observações", "FieldLabel"))
        form.addWidget(self.notes)

        buttons = QHBoxLayout()
        if transaction:
            delete = QPushButton("Excluir lançamento")
            delete.setObjectName("DangerAction")
            delete.clicked.connect(self._delete)
            buttons.addWidget(delete)
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("Secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Salvar alterações" if transaction else "Salvar lançamento")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        form.addSpacing(8)
        form.addLayout(buttons)
        add_frameless_dialog_bar(self)

    def _save(self) -> None:
        try:
            values = dict(
                description=self.description.text(),
                category=self.category.current_category(),
                amount=self.amount.value(),
                kind=self.kind.currentData(),
                status=self.status.currentData(),
                transaction_date=self.transaction_date.iso_date(),
                account_id=self.account.currentData(),
                notes=self.notes.toPlainText(),
                scope=self.scope.currentData(),
            )
            if self.transaction:
                self.database.update_transaction(self.transaction["id"], **values)
            else:
                self.database.add_transaction(**values)
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Confira os dados", str(error))
            return
        self.saved.emit()
        self.accept()

    def _delete(self) -> None:
        if not self.transaction or not confirm_delete(self, f'o lançamento “{self.transaction["description"]}”'):
            return
        try:
            self.database.delete_transaction(self.transaction["id"])
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Não foi possível excluir", str(error))
            return
        self.saved.emit()
        self.accept()


class FixedExpenseDialog(QDialog):
    saved = Signal()

    def __init__(
        self,
        database: Database,
        parent: QWidget | None = None,
        expense: dict[str, Any] | None = None,
        default_scope: str = "work",
        fixed_kind: str = "expense",
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.expense = expense
        self.fixed_kind = fixed_kind
        entry_name = "entrada fixa" if fixed_kind == "income" else "conta fixa"
        self.entry_name = entry_name
        self.setWindowTitle(("Editar" if expense else "Nova") + f" {entry_name} · Summit")
        self.setModal(True)
        self.setMinimumWidth(560)
        form = QVBoxLayout(self)
        form.setContentsMargins(26, 24, 26, 24)
        form.setSpacing(10)
        form.addWidget(label(("Editar " if expense else "Nova ") + entry_name, "PageTitle"))
        description = (
            "Cadastre receitas que você espera receber todos os meses."
            if fixed_kind == "income"
            else "Cadastre compromissos que se repetem todos os meses."
        )
        form.addWidget(label(description, "Muted"))

        source = expense or {}
        self.description = text_field(
            "Ex.: Salário, contrato mensal ou aluguel" if fixed_kind == "income" else "Ex.: Aluguel, internet ou escola",
            source.get("description", ""),
        )
        self.category = CategoryCombo(
            database,
            "income" if fixed_kind == "income" else "expense",
            source.get("category", ""),
        )
        self.amount = money_field(float(source.get("amount", 0)))
        self.due_day = QSpinBox()
        self.due_day.setRange(1, 31)
        self.due_day.setValue(int(source.get("due_day", 10)))
        self.due_day.setPrefix("Dia ")
        self.account = QComboBox()
        for account in database.accounts():
            self.account.addItem(account["name"], account["id"])
        if source.get("account_id") is not None:
            select_combo_data(self.account, source["account_id"])
        self.scope = QComboBox()
        self.scope.addItem("Trabalho", "work")
        self.scope.addItem("Pessoal", "personal")
        select_combo_data(self.scope, source.get("scope", default_scope))
        self.active = QCheckBox(
            "Incluir esta entrada no planejamento mensal"
            if fixed_kind == "income"
            else "Incluir esta conta no planejamento mensal"
        )
        self.active.setChecked(bool(source.get("active", True)))
        self.notes = notes_field("Contrato, forma de pagamento ou observações", source.get("notes", ""))

        grid = QGridLayout()
        fields = [
            ("Descrição", self.description), ("Categoria", self.category),
            ("Valor mensal", self.amount), ("Dia do vencimento", self.due_day),
            ("Uso", self.scope), ("Conta Corrente", self.account),
        ]
        for index, (title, widget) in enumerate(fields):
            add_form_field(grid, index, title, widget)
        form.addLayout(grid)
        form.addWidget(self.active)
        form.addWidget(label("Observações", "FieldLabel"))
        form.addWidget(self.notes)
        buttons = QHBoxLayout()
        if expense:
            delete = QPushButton(f"Excluir {entry_name}")
            delete.setObjectName("DangerAction")
            delete.clicked.connect(self._delete)
            buttons.addWidget(delete)
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("Secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton(f"Salvar {entry_name}")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        form.addLayout(buttons)
        add_frameless_dialog_bar(self)

    def _save(self) -> None:
        try:
            values = dict(
                description=self.description.text(), category=self.category.current_category(), amount=self.amount.value(),
                due_day=self.due_day.value(), account_id=self.account.currentData(),
                active=self.active.isChecked(), notes=self.notes.toPlainText(), scope=self.scope.currentData(),
            )
            if self.expense:
                if self.fixed_kind == "income":
                    self.database.update_fixed_income(self.expense["id"], **values)
                else:
                    self.database.update_fixed_expense(self.expense["id"], **values)
            else:
                if self.fixed_kind == "income":
                    self.database.add_fixed_income(**values)
                else:
                    self.database.add_fixed_expense(**values)
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Confira os dados", str(error))
            return
        self.saved.emit()
        self.accept()

    def _delete(self) -> None:
        if not self.expense or not confirm_delete(self, f'a {self.entry_name} “{self.expense["description"]}”'):
            return
        try:
            if self.fixed_kind == "income":
                self.database.delete_fixed_income(self.expense["id"])
            else:
                self.database.delete_fixed_expense(self.expense["id"])
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Não foi possível excluir", str(error))
            return
        self.saved.emit()
        self.accept()


class FixedIncomeDialog(FixedExpenseDialog):
    def __init__(
        self,
        database: Database,
        parent: QWidget | None = None,
        income: dict[str, Any] | None = None,
        default_scope: str = "work",
    ) -> None:
        super().__init__(database, parent, income, default_scope, fixed_kind="income")


class GoalDialog(QDialog):
    saved = Signal()

    def __init__(self, database: Database, parent: QWidget | None = None, goal: dict[str, Any] | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.goal = goal
        self.setWindowTitle(("Editar" if goal else "Nova") + " meta · Summit")
        self.setModal(True)
        self.setMinimumWidth(570)
        source = goal or {}
        form = QVBoxLayout(self)
        form.setContentsMargins(26, 24, 26, 24)
        form.setSpacing(10)
        form.addWidget(label("Editar meta" if goal else "Nova meta financeira", "PageTitle"))
        form.addWidget(label("Defina destino, prazo e quanto pretende reservar por mês.", "Muted"))
        self.name = text_field("Ex.: Reserva de emergência", source.get("name", ""))
        self.current = money_field(float(source.get("current_amount", 0)))
        self.target = money_field(float(source.get("target_amount", 0)))
        self.contribution = money_field(float(source.get("monthly_contribution", 0)))
        deadline = source.get("deadline") or QDate.currentDate().addMonths(6).toString("yyyy-MM-dd")
        self.deadline = DateField(deadline)
        self.notes = notes_field("Por que esta meta é importante?", source.get("notes", ""))
        grid = QGridLayout()
        fields = [
            ("Nome da meta", self.name), ("Prazo", self.deadline),
            ("Valor já reservado", self.current), ("Valor desejado", self.target),
            ("Aporte mensal planejado", self.contribution),
        ]
        for index, (title, widget) in enumerate(fields):
            add_form_field(grid, index, title, widget)
        form.addLayout(grid)
        form.addWidget(label("Observações", "FieldLabel"))
        form.addWidget(self.notes)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("Secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Salvar meta")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        form.addLayout(buttons)
        add_frameless_dialog_bar(self)

    def _save(self) -> None:
        try:
            values = dict(
                name=self.name.text(), current_amount=self.current.value(), target_amount=self.target.value(),
                deadline=self.deadline.iso_date(), monthly_contribution=self.contribution.value(),
                notes=self.notes.toPlainText(),
            )
            if self.goal:
                self.database.update_goal(self.goal["id"], **values)
            else:
                self.database.add_goal(**values)
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Confira os dados", str(error))
            return
        self.saved.emit()
        self.accept()


class BudgetDialog(QDialog):
    saved = Signal()

    def __init__(self, database: Database, parent: QWidget | None = None, budget: dict[str, Any] | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.budget = budget
        self.setWindowTitle(("Editar" if budget else "Novo") + " limite mensal · Summit")
        self.setModal(True)
        self.setMinimumWidth(500)
        source = budget or {}
        form = QVBoxLayout(self)
        form.setContentsMargins(26, 24, 26, 24)
        form.setSpacing(10)
        form.addWidget(label("Limite por categoria", "PageTitle"))
        form.addWidget(label("O Summit compara este teto com seus gastos concluídos do mês.", "Muted"))
        self.category = CategoryCombo(database, "expense", source.get("category", ""))
        self.limit = money_field(float(source.get("monthly_limit", 0)))
        self.notes = notes_field("Objetivo ou regra para esta categoria", source.get("notes", ""))
        form.addWidget(label("Categoria", "FieldLabel"))
        form.addWidget(self.category)
        form.addWidget(label("Limite mensal", "FieldLabel"))
        form.addWidget(self.limit)
        form.addWidget(label("Observações", "FieldLabel"))
        form.addWidget(self.notes)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("Secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Salvar limite")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        form.addLayout(buttons)
        add_frameless_dialog_bar(self)

    def _save(self) -> None:
        try:
            values = dict(category=self.category.current_category(), monthly_limit=self.limit.value(), notes=self.notes.toPlainText())
            if self.budget:
                self.database.update_budget(self.budget["id"], **values)
            else:
                self.database.add_budget(**values)
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Confira os dados", str(error))
            return
        self.saved.emit()
        self.accept()


class InvestmentDialog(QDialog):
    saved = Signal()

    TYPES = ("Renda fixa", "Renda variável", "Fundo", "Criptomoeda", "Previdência", "Imóvel", "Outro")

    def __init__(self, database: Database, parent: QWidget | None = None, investment: dict[str, Any] | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.investment = investment
        self.setWindowTitle(("Editar" if investment else "Novo") + " investimento · Summit")
        self.setModal(True)
        self.setMinimumWidth(610)
        source = investment or {}
        form = QVBoxLayout(self)
        form.setContentsMargins(26, 24, 26, 24)
        form.setSpacing(10)
        form.addWidget(label("Editar investimento" if investment else "Novo investimento", "PageTitle"))
        form.addWidget(label("Registre posição, custo e valor atual para acompanhar a rentabilidade.", "Muted"))
        self.name = text_field("Ex.: Tesouro Selic 2029", source.get("name", ""))
        self.investment_type = QComboBox()
        self.investment_type.addItems(self.TYPES)
        if source.get("investment_type"):
            index = self.investment_type.findText(source["investment_type"])
            self.investment_type.setCurrentIndex(max(0, index))
        self.institution = text_field("Ex.: Banco ou corretora", source.get("institution", ""))
        self.invested = money_field(float(source.get("invested", 0)))
        self.current_value = money_field(float(source.get("current_value", 0)))
        self.quantity = QDoubleSpinBox()
        self.quantity.setRange(0, 999_999_999)
        self.quantity.setDecimals(6)
        self.quantity.setValue(float(source.get("quantity", 0)))
        self.average_price = money_field(float(source.get("average_price", 0)))
        self.updated_at = DateField(source.get("updated_at") or None)
        self.notes = notes_field("Estratégia, vencimento, objetivo ou observações", source.get("notes", ""))
        grid = QGridLayout()
        fields = [
            ("Nome do ativo", self.name), ("Tipo", self.investment_type),
            ("Instituição", self.institution), ("Data da posição", self.updated_at),
            ("Total aplicado", self.invested), ("Valor atual", self.current_value),
            ("Quantidade", self.quantity), ("Preço médio", self.average_price),
        ]
        for index, (title, widget) in enumerate(fields):
            add_form_field(grid, index, title, widget)
        form.addLayout(grid)
        form.addWidget(label("Observações", "FieldLabel"))
        form.addWidget(self.notes)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("Secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Salvar investimento")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        form.addLayout(buttons)
        add_frameless_dialog_bar(self)

    def _save(self) -> None:
        try:
            values = dict(
                name=self.name.text(), investment_type=self.investment_type.currentText(),
                invested=self.invested.value(), current_value=self.current_value.value(),
                institution=self.institution.text(), quantity=self.quantity.value(),
                average_price=self.average_price.value(), notes=self.notes.toPlainText(),
                updated_at=self.updated_at.iso_date(),
            )
            if self.investment:
                self.database.update_investment(self.investment["id"], **values)
            else:
                self.database.add_investment(**values)
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Confira os dados", str(error))
            return
        self.saved.emit()
        self.accept()


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
        metrics.addWidget(MetricCard("Entradas", brl(income, hidden=False), GREEN, "MetricGreen", "Recebidas no período"), 0, 0)
        metrics.addWidget(MetricCard("Gastos", brl(expense, hidden=False), ORANGE, "MetricOrange", "Pagos no período"), 0, 1)
        metrics.addWidget(MetricCard("Resultado", brl(result, hidden=False), PURPLE, "MetricPurple", f"Margem: {margin:.1f}%"), 0, 2)
        metrics.addWidget(MetricCard("Fixos mensais", brl(fixed, hidden=False), BLUE, "MetricBlue", "Compromissos recorrentes ativos"), 0, 3)
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


class SplitEventDialog(QDialog):
    saved = Signal()

    def __init__(self, database: Database, parent: QWidget | None = None, event: dict[str, Any] | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.event = event
        self.setWindowTitle(("Editar" if event else "Novo") + " grupo · Summit")
        self.setModal(True)
        self.setMinimumWidth(520)
        source = event or {}
        form = QVBoxLayout(self)
        form.setContentsMargins(26, 24, 26, 24)
        form.setSpacing(10)
        form.addWidget(label("Editar grupo" if event else "Novo grupo de despesas", "PageTitle"))
        form.addWidget(label("Viagem em grupo, reforma, construção ou qualquer evento compartilhado.", "Muted", True))
        self.name = text_field("Ex.: Viagem para a praia", source.get("name", ""))
        self.description = text_field("Detalhe do evento (opcional)", source.get("description", ""))
        self.target = money_field(float(source.get("target_amount", 0)))
        self.target.setToolTip("Quanto vocês planejam gastar no total (opcional)")
        form.addWidget(label("Nome do grupo", "FieldLabel"))
        form.addWidget(self.name)
        form.addWidget(label("Descrição", "FieldLabel"))
        form.addWidget(self.description)
        form.addWidget(label("Meta de gastos (opcional)", "FieldLabel"))
        form.addWidget(self.target)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("Secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Salvar grupo")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        form.addLayout(buttons)
        add_frameless_dialog_bar(self)

    def _save(self) -> None:
        try:
            if self.event:
                self.database.update_split_event(
                    self.event["id"], self.name.text(), self.description.text(), self.target.value()
                )
            else:
                self.database.add_split_event(self.name.text(), self.description.text(), self.target.value())
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Confira os dados", str(error))
            return
        self.saved.emit()
        self.accept()


class SplitExpenseDialog(QDialog):
    saved = Signal()

    def __init__(
        self, database: Database, event_id: int,
        parent: QWidget | None = None, existing_people: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.event_id = event_id
        self.setWindowTitle("Nova despesa compartilhada · Summit")
        self.setModal(True)
        self.setMinimumWidth(540)
        form = QVBoxLayout(self)
        form.setContentsMargins(26, 24, 26, 24)
        form.setSpacing(10)
        form.addWidget(label("Nova despesa compartilhada", "PageTitle"))
        form.addWidget(label("Registre quem pagou e quem divide este gasto.", "Muted"))
        self.description = text_field("Ex.: Pousada, jantar, material")
        self.amount = money_field()
        self.paid_by = QComboBox()
        self.paid_by.setEditable(True)
        for person in existing_people or []:
            self.paid_by.addItem(person)
        self.participants = QLineEdit(", ".join(existing_people or []))
        self.participants.setPlaceholderText("Nomes separados por vírgula")
        self.expense_date = DateField()
        grid = QGridLayout()
        fields = [
            ("Descrição", self.description), ("Valor", self.amount),
            ("Quem pagou", self.paid_by), ("Participantes", self.participants),
            ("Data", self.expense_date),
        ]
        for index, (title, widget) in enumerate(fields):
            add_form_field(grid, index, title, widget)
        form.addLayout(grid)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("Secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Salvar despesa")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        form.addLayout(buttons)
        add_frameless_dialog_bar(self)

    def _save(self) -> None:
        participants = [part.strip() for part in self.participants.text().split(",")]
        try:
            self.database.add_split_expense(
                self.event_id, self.description.text(), self.amount.value(),
                self.paid_by.currentText(), participants, self.expense_date.iso_date(),
            )
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Confira os dados", str(error))
            return
        self.saved.emit()
        self.accept()


class SplitPage(QWidget):
    """Shared-expense groups (Splitwise style): who paid what and balances."""

    def __init__(
        self,
        events: list[dict[str, Any]],
        expenses_for: Callable[[int], list[dict[str, Any]]],
        add_event: Callable[[], None],
        edit_event: Callable[[dict[str, Any]], None],
        delete_event: Callable[[dict[str, Any]], None],
        add_expense: Callable[[dict[str, Any]], None],
        delete_expense: Callable[[dict[str, Any]], None],
    ) -> None:
        super().__init__()
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        copy = QVBoxLayout()
        copy.addWidget(label("Divisão de despesas", "PageTitle"))
        copy.addWidget(label("Divida custos de viagens, reformas e projetos entre participantes.", "Muted"))
        header.addLayout(copy)
        header.addStretch()
        add = QPushButton("+  Novo grupo")
        add.setObjectName("PagePrimary")
        add.clicked.connect(add_event)
        header.addWidget(add)
        page.addLayout(header)
        page.addSpacing(14)

        if not events:
            empty = Panel("Nenhum grupo ainda", "Crie um grupo para começar a dividir despesas")
            empty.body.addWidget(label(
                "Ideal para viagens em grupo, obras, reformas ou qualquer projeto compartilhado.", "Muted", True
            ))
            page.addWidget(empty)
            page.addStretch()
            return

        for event in events:
            expenses = expenses_for(event["id"])
            total = sum(float(item["amount"]) for item in expenses)
            panel = Panel(event["name"], event["description"] or "Grupo compartilhado")
            actions = QHBoxLayout()
            actions.addStretch()
            actions.addWidget(action_widget(
                lambda _checked=False, current=event: edit_event(current),
                lambda _checked=False, current=event: delete_event(current),
            ))
            panel.body.itemAt(0).layout().addLayout(actions)

            meta = QHBoxLayout()
            meta.addWidget(label(f"Total do grupo  {brl(total)}", "ColumnTotal"))
            meta.addStretch()
            target = float(event.get("target_amount") or 0)
            if target:
                meta.addWidget(label(f"Meta  {brl(target)} · {round(total / target * 100)}% usado", "Tiny"))
            panel.body.addLayout(meta)

            people: list[str] = []
            paid: dict[str, float] = {}
            owes: dict[str, float] = {}
            for item in expenses:
                amount = float(item["amount"])
                payer = item["paid_by"]
                participants = [part.strip() for part in item["participants"].split(",") if part.strip()]
                for person in [payer] + participants:
                    if person not in people:
                        people.append(person)
                paid[payer] = paid.get(payer, 0) + amount
                share = amount / max(len(participants), 1)
                for person in participants:
                    owes[person] = owes.get(person, 0) + share

            if people:
                balance_text = "  ·  ".join(
                    f"{person}: {brl(paid.get(person, 0) - owes.get(person, 0))}"
                    for person in people
                )
                panel.body.addWidget(label(f"Saldo por pessoa (positivo = a receber)  {balance_text}", "Tiny", True))

            for item in expenses:
                row = QHBoxLayout()
                row.addWidget(label(item["description"]))
                row.addStretch()
                row.addWidget(label(
                    f'{item["paid_by"]} pagou {brl(float(item["amount"]))} · {item["participants"]}', "Tiny"
                ))
                remove = QPushButton("Excluir")
                remove.setObjectName("DangerButton")
                remove.clicked.connect(lambda _checked=False, current=item: delete_expense(current))
                row.addWidget(remove)
                panel.body.addLayout(row)
            if not expenses:
                panel.body.addWidget(label("Nenhuma despesa registrada neste grupo.", "Muted"))
            add_expense_button = QPushButton("+  Adicionar despesa")
            add_expense_button.setObjectName("SmallButton")
            add_expense_button.clicked.connect(lambda _checked=False, current=event: add_expense(current))
            panel.body.addSpacing(8)
            panel.body.addWidget(add_expense_button)
            page.addWidget(panel)
        page.addStretch()


class SettingsPage(QWidget):
    def __init__(
        self,
        snapshot: dict[str, Any],
        settings: dict[str, Any],
        save_profile: Callable[[str, str], None],
        change_theme: Callable[[str, str], None],
        backup: Callable[[], None],
        database: Database | None = None,
        categories_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.database = database
        self.categories_changed = categories_changed
        self.change_theme = change_theme
        workspace = snapshot.get("workspace") or {}

        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(18)
        page.addWidget(label("Configurações", "PageTitle"))
        page.addWidget(label("Edite seu perfil e personalize a aparência do Summit.", "Muted"))

        profile_panel = Panel("Perfil", "Nome e atividade exibidos no espaço financeiro")
        name_field = QLineEdit(workspace.get("manager", ""))
        name_field.setPlaceholderText("Seu nome")
        business_field = QLineEdit(workspace.get("business", ""))
        business_field.setPlaceholderText("Sua atividade ou empresa")
        profile_grid = QGridLayout()
        profile_grid.setSpacing(13)
        add_form_field(profile_grid, 0, "NOME", name_field)
        add_form_field(profile_grid, 1, "ATIVIDADE", business_field)
        profile_panel.body.addLayout(profile_grid)
        profile_panel.body.addSpacing(10)
        save_profile_button = QPushButton("Salvar perfil")
        save_profile_button.setObjectName("Primary")

        def _save_profile() -> None:
            try:
                save_profile(name_field.text(), business_field.text())
            except ValueError as error:
                QMessageBox.warning(self, "Não foi possível salvar", str(error))

        save_profile_button.clicked.connect(_save_profile)
        profile_row = QHBoxLayout()
        profile_row.addStretch()
        profile_row.addWidget(save_profile_button)
        profile_panel.body.addLayout(profile_row)
        page.addWidget(profile_panel)

        theme_panel = Panel("Aparência", "Escolha entre tema claro e escuro")
        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        dark_button = QPushButton("Escuro")
        light_button = QPushButton("Claro")
        for button in (dark_button, light_button):
            button.setCheckable(True)
            button.setMinimumWidth(110)
        # Fixed, theme-independent colors so each swatch stays legible no
        # matter which theme is currently active: "Escuro" always uses the
        # same tint as a selected nav item in dark mode, "Claro" always uses
        # the dark theme's page background — neither ever blends into the
        # surrounding (possibly opposite) theme.
        # Fixed, high-contrast swatches that stay legible in BOTH themes:
        # the dark swatch is near-black with white text, the light swatch is
        # near-white with dark text, and the selected one gets the brand
        # purple border as the active indicator.
        dark_button.setStyleSheet(
            "QPushButton{background:#0c0912;color:#ffffff;border:2px solid #444;"
            "border-radius:9px;padding:9px 14px;font-weight:600;}"
            f"QPushButton:checked{{border:2px solid {DEFAULT_ACCENT};}}"
            "QPushButton:hover{border-color:#8c8298;}"
        )
        light_button.setStyleSheet(
            "QPushButton{background:#f5f3fa;color:#221f29;border:2px solid #9a93a8;"
            "border-radius:9px;padding:9px 14px;font-weight:600;}"
            f"QPushButton:checked{{border:2px solid {DEFAULT_ACCENT};}}"
            "QPushButton:hover{border-color:#56506e;}"
        )
        dark_button.setChecked(settings["theme_mode"] == "dark")
        light_button.setChecked(settings["theme_mode"] == "light")

        def _pick_mode(mode: str) -> None:
            dark_button.setChecked(mode == "dark")
            light_button.setChecked(mode == "light")
            self.change_theme(mode, DEFAULT_ACCENT)
            self.settings["theme_mode"] = mode

        dark_button.clicked.connect(lambda: _pick_mode("dark"))
        light_button.clicked.connect(lambda: _pick_mode("light"))
        mode_row.addWidget(dark_button)
        mode_row.addWidget(light_button)
        mode_row.addStretch()
        theme_panel.body.addLayout(mode_row)
        theme_panel.body.addSpacing(10)
        theme_panel.body.addWidget(label(
            "O Summit usa um único tom de roxo como destaque, no claro e no escuro, "
            "para manter contraste e legibilidade consistentes em todas as páginas.",
            "Tiny", True,
        ))
        page.addWidget(theme_panel)

        category_panel = Panel("Categorias", "Catálogo usado nos lançamentos e limites mensais")
        category_panel.body.addWidget(label(
            "As categorias predefinidas não podem ser alteradas; personalize criando as suas "
            "abaixo ou diretamente ao digitar no campo de categoria de um lançamento.", "Tiny", True
        ))
        category_panel.body.addSpacing(8)
        new_category_row = QHBoxLayout()
        self.new_category_field = text_field("Nova categoria personalizada")
        add_category_button = QPushButton("+  Criar categoria")
        add_category_button.setObjectName("Secondary")
        add_category_button.clicked.connect(self._create_category)
        new_category_row.addWidget(self.new_category_field, 1)
        new_category_row.addWidget(add_category_button)
        category_panel.body.addLayout(new_category_row)
        category_panel.body.addSpacing(8)
        custom_categories = [item for item in database.categories() if not item["predefined"]]
        if custom_categories:
            for category in custom_categories:
                row = QHBoxLayout()
                row.addWidget(label(category["name"]))
                row.addStretch()
                remove = QPushButton("Excluir")
                remove.setObjectName("DangerButton")
                remove.clicked.connect(
                    lambda _checked=False, current=category: self._delete_category(current)
                )
                row.addWidget(remove)
                category_panel.body.addLayout(row)
        else:
            category_panel.body.addWidget(label("Nenhuma categoria personalizada ainda.", "Muted"))
        page.addWidget(category_panel)

        data_panel = Panel("Dados", "Guarde uma cópia do seu banco de dados local")
        data_panel.body.addWidget(label(
            "O Summit guarda tudo em um arquivo local no seu computador. "
            "Faça backups periódicos para não perder seus lançamentos.", "Tiny", True
        ))
        data_panel.body.addSpacing(10)
        backup_row = QHBoxLayout()
        backup_button = QPushButton("Fazer backup agora")
        backup_button.setObjectName("Secondary")
        backup_button.clicked.connect(backup)
        backup_row.addWidget(backup_button)
        backup_row.addStretch()
        data_panel.body.addLayout(backup_row)
        page.addWidget(data_panel)
        page.addStretch()

    def _create_category(self) -> None:
        if self.database is None:
            return
        name = self.new_category_field.text()
        try:
            self.database.add_category(name, "expense")
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Não foi possível criar", str(error))
            return
        if self.categories_changed:
            self.categories_changed()

    def _delete_category(self, category: dict[str, Any]) -> None:
        if self.database is None or not confirm_delete(self, f'a categoria “{category["name"]}”'):
            return
        try:
            self.database.delete_category(category["id"])
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Não foi possível excluir", str(error))
            return
        if self.categories_changed:
            self.categories_changed()


class WindowTitleBar(QWidget):
    """A minimal frameless-window title bar: no icon or text, just window controls."""

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self._window = window
        self.setObjectName("WindowTitleBar")
        # A little extra headroom so the custom bar is never clipped at the
        # top of the frameless window on Windows.
        self.setFixedHeight(38)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 0, 2)
        layout.setSpacing(0)
        layout.addStretch()
        self._max_button = self._control_button("▢", self._toggle_maximize)
        layout.addWidget(self._control_button("–", window.showMinimized))
        layout.addWidget(self._max_button)
        layout.addWidget(self._control_button("×", window.close, danger=True))

    def _control_button(self, text: str, handler: Callable[[], Any], danger: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("WindowControlDanger" if danger else "WindowControl")
        button.setFixedSize(44, 36)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(handler)
        return button

    def _toggle_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
        super().mouseDoubleClickEvent(event)


class _FramelessBody(QWidget):
    """Wraps a window's central widget with a title bar and a corner size grip."""

    def __init__(self, title_bar: WindowTitleBar, central: QWidget) -> None:
        super().__init__()
        self.setObjectName("Root")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(title_bar)
        layout.addWidget(central, 1)
        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(16, 16)
        self._grip.raise_()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._grip.move(self.width() - self._grip.width(), self.height() - self._grip.height())


def make_frameless(window: QMainWindow) -> WindowTitleBar:
    """Strip the native title bar/border from ``window`` and add a minimal one.

    Removes the OS chrome (icon, exe name, native buttons) in favor of a
    single solid-color window with just minimize/maximize/close controls,
    draggable via the title bar and resizable via a corner size grip.
    """
    window.setWindowIcon(app_icon())
    window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    title_bar = WindowTitleBar(window)
    central = window.centralWidget()
    window.setCentralWidget(_FramelessBody(title_bar, central))
    return title_bar


class _DialogTitleBar(QWidget):
    """A minimal draggable, close-only strip for frameless dialogs."""

    def __init__(self, dialog: QDialog) -> None:
        super().__init__(dialog)
        self._dialog = dialog
        self.setObjectName("WindowTitleBar")
        self.setFixedHeight(28)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch()
        close_button = QPushButton("×")
        close_button.setObjectName("WindowControlDanger")
        close_button.setFixedSize(40, 28)
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(dialog.reject)
        layout.addWidget(close_button)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._dialog.windowHandle()
            if handle is not None:
                handle.startSystemMove()
        super().mousePressEvent(event)


def add_frameless_dialog_bar(dialog: QDialog) -> None:
    """Strip a dialog's native title bar/border and add a minimal close strip."""
    dialog.setWindowIcon(app_icon())
    dialog.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    existing_layout = dialog.layout()
    if isinstance(existing_layout, QVBoxLayout):
        existing_layout.insertWidget(0, _DialogTitleBar(dialog))


class ConfirmOverlay(QDialog):
    """A translucent full-window confirmation card, replacing native QMessageBox Yes/No."""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        message: str,
        confirm_text: str = "Confirmar",
        danger: bool = False,
    ) -> None:
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card = QFrame()
        card.setObjectName("Panel")
        card.setFixedWidth(380)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(26, 24, 26, 20)
        card_layout.setSpacing(10)
        card_layout.addWidget(label(title, "PanelTitle"))
        card_layout.addWidget(label(message, "Muted", True))
        card_layout.addSpacing(10)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("Secondary")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton(confirm_text)
        confirm.setObjectName("DangerAction" if danger else "Primary")
        confirm.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        card_layout.addLayout(buttons)
        outer.addWidget(card)
        window = parent.window() if parent is not None else None
        if window is not None:
            self.setGeometry(window.geometry())

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(4, 2, 8, 150))

    @staticmethod
    def ask(
        parent: QWidget,
        title: str,
        message: str,
        confirm_text: str = "Confirmar",
        danger: bool = False,
    ) -> bool:
        overlay = ConfirmOverlay(parent, title, message, confirm_text, danger)
        return overlay.exec() == QDialog.DialogCode.Accepted


class MainWindow(QMainWindow):
    NAVIGATION = (
        "Visão geral", "Movimentações", "Fixos", "Contas", "Dívidas",
        "Planejamento", "Divisão", "Investimentos", "Relatórios", "Configurações",
    )

    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self.nav_buttons: list[QPushButton] = []
        self.dashboard_period = "monthly"
        self.account_visibility: dict[int, bool] = {}
        set_values_hidden(False)
        self.setWindowTitle("Summit · Visão financeira")
        self.setMinimumSize(1080, 700)
        self.resize(1380, 850)

        root = QWidget()
        root.setObjectName("Root")
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        shell.addWidget(self._sidebar())

        content = QWidget()
        content.setObjectName("Content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._header())

        self.pages = QStackedWidget()
        self.pages.setObjectName("Content")
        self.page_scrolls: list[QScrollArea] = []
        content_layout.addWidget(self.pages)
        shell.addWidget(content, 1)
        self.setCentralWidget(root)
        make_frameless(self)
        self._refresh_pages()

    def _sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(235)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 28, 18, 20)
        brand = QHBoxLayout()
        mark = label("▲", "BrandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(34, 34)
        brand.addWidget(mark)
        brand.addWidget(label("summit.", "Brand"))
        brand.addStretch()
        layout.addLayout(brand)
        layout.addSpacing(45)
        layout.addWidget(label("ESPAÇO FINANCEIRO", "SectionLabel"))
        layout.addSpacing(6)
        for index, name in enumerate(self.NAVIGATION):
            button = QPushButton(f"  {name}")
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, page=index: self._show_page(page))
            self.nav_buttons.append(button)
            layout.addWidget(button)
        self.nav_buttons[0].setChecked(True)
        layout.addStretch()

        insight = QFrame()
        insight.setObjectName("Insight")
        insight_layout = QVBoxLayout(insight)
        insight_layout.setContentsMargins(15, 14, 15, 14)
        insight_layout.addWidget(label("✦  Insight do Summit", "PanelTitle"))
        insight_layout.addWidget(label("Organize seus próximos lançamentos para manter a projeção sempre confiável.", "Tiny", True))
        layout.addWidget(insight)
        layout.addSpacing(14)
        workspace = self.database.workspace() or {}
        layout.addWidget(label(workspace.get("manager", "Seu espaço"), "PanelTitle"))
        layout.addWidget(label(workspace.get("business", "Administrador"), "Tiny"))
        return sidebar

    def _header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("Header")
        header.setFixedHeight(105)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(34, 19, 34, 18)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        self.section_label = label("VISÃO GERAL", "SectionLabel")
        workspace = self.database.workspace() or {}
        first_name = workspace.get("manager", "visitante").split()[0]
        copy.addWidget(self.section_label)
        copy.addWidget(label(f"Olá, {first_name}  ✦", "PageTitle"))
        copy.addWidget(label("Aqui está o pulso das suas finanças hoje.", "Tiny"))
        layout.addLayout(copy)
        layout.addStretch()
        self.privacy_button = QPushButton("  Valores")
        self.privacy_button.setObjectName("Secondary")
        self.privacy_button.setIcon(eye_icon(closed=False, color="#f4f0f8"))
        self.privacy_button.setIconSize(QSize(16, 16))
        self.privacy_button.setCheckable(True)
        self.privacy_button.setToolTip("Ocultar todos os valores financeiros exibidos")
        self.privacy_button.clicked.connect(self._toggle_values)
        layout.addWidget(self.privacy_button)
        new_transaction = QPushButton("+  Nova movimentação")
        new_transaction.setObjectName("Primary")
        new_transaction.clicked.connect(self._new_transaction)
        layout.addWidget(new_transaction)
        return header

    def _toggle_values(self, hidden: bool) -> None:
        set_values_hidden(hidden)
        self.privacy_button.setText("  Valores")
        self.privacy_button.setIcon(eye_icon(closed=hidden, color="#8562ef" if hidden else "#f4f0f8"))
        self.privacy_button.setToolTip(
            "Mostrar os valores financeiros" if hidden else "Ocultar todos os valores financeiros exibidos"
        )
        self._refresh_pages()

    def _toggle_account_visibility(self, account_id: int) -> None:
        current = self.account_visibility.get(account_id, values_hidden())
        self.account_visibility[account_id] = not current
        self._refresh_pages()

    def _change_dashboard_period(self, period: str) -> None:
        if period == self.dashboard_period:
            return
        self.dashboard_period = period
        self._refresh_pages()

    def _show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        if 0 <= index < len(self.page_scrolls):
            page_scroll = self.page_scrolls[index]
            page_scroll.horizontalScrollBar().setValue(0)
            page_scroll.verticalScrollBar().setValue(0)
        self.section_label.setText(self.NAVIGATION[index].upper())
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)

    def _refresh_pages(self) -> None:
        current = self.pages.currentIndex() if self.pages.count() else 0
        while self.pages.count():
            widget = self.pages.widget(0)
            self.pages.removeWidget(widget)
            widget.deleteLater()
        snapshot = self.database.snapshot()
        page_widgets = [
            DashboardPage(
                snapshot,
                lambda: self._new_transaction(),
                self._confirm_receipt,
                self._edit_transaction,
                self.dashboard_period,
                self._change_dashboard_period,
            ),
            MovementsPage(
                snapshot,
                lambda kind, status: self._new_transaction(kind=kind, status=status),
                self._edit_transaction,
            ),
            FixedEntriesPage(
                snapshot,
                lambda scope: self._new_fixed_income(default_scope=scope),
                self._edit_fixed_income,
                lambda scope: self._new_fixed_expense(default_scope=scope),
                self._edit_fixed_expense,
            ),
            AccountsPage(
                snapshot, self._new_account, self._edit_account,
                self.account_visibility, self._toggle_account_visibility,
            ),
            DebtsPage(snapshot["debts"], self._new_debt, self._edit_debt),
            PlanningPage(
                snapshot,
                self._new_goal,
                self._edit_goal,
                self._delete_goal,
                self._new_budget,
                self._edit_budget,
                self._delete_budget,
            ),
            SplitPage(
                snapshot.get("split_events", []),
                self.database.split_expenses,
                self._new_split_event,
                self._edit_split_event,
                self._delete_split_event,
                self._new_split_expense,
                self._delete_split_expense,
            ),
            InvestmentsPage(
                snapshot["investments"],
                self._new_investment,
                self._edit_investment,
                self._delete_investment,
            ),
            ReportsPage(snapshot),
            SettingsPage(
                snapshot,
                self.database.settings(),
                self._save_profile,
                self._change_theme,
                self._backup_database,
                database=self.database,
                categories_changed=self._refresh_pages,
            ),
        ]
        self.page_scrolls = []
        for page_widget in page_widgets:
            wrapper = QWidget()
            wrapper.setObjectName("PageContainer")
            layout = QVBoxLayout(wrapper)
            layout.setContentsMargins(32, 24, 32, 34)
            layout.addWidget(page_widget)
            # Each page gets its own scroll area so the scrollbar range
            # reflects only that page's content, not the tallest page in
            # the app.
            page_scroll = QScrollArea()
            page_scroll.setObjectName("PageScroll")
            page_scroll.setWidgetResizable(True)
            page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            page_scroll.viewport().setStyleSheet("background: transparent;")
            page_scroll.setFrameShape(QFrame.Shape.NoFrame)
            page_scroll.setWidget(wrapper)
            self.page_scrolls.append(page_scroll)
            self.pages.addWidget(page_scroll)
        self.pages.setCurrentIndex(max(0, current))

    def _open_dialog(self, dialog: QDialog) -> None:
        dialog.saved.connect(self._refresh_pages)  # type: ignore[attr-defined]
        dialog.exec()

    def _new_transaction(
        self,
        _checked: bool = False,
        kind: str = "expense",
        status: str = "paid",
    ) -> None:
        self._open_dialog(
            TransactionDialog(
                self.database, self, default_kind=kind, default_status=status
            )
        )

    def _edit_transaction(self, transaction: dict[str, Any]) -> None:
        self._open_dialog(TransactionDialog(self.database, self, transaction=transaction))

    def _confirm_receipt(self, transaction: dict[str, Any]) -> None:
        account = next(
            (item["name"] for item in self.database.accounts() if item["id"] == transaction["account_id"]),
            "a conta selecionada",
        )
        confirmed = ConfirmOverlay.ask(
            self,
            "Confirmar recebimento",
            f'Confirmar que {brl(float(transaction["amount"]), hidden=False)} de “{transaction["description"]}” entrou em {account}?',
            confirm_text="Confirmar recebimento",
        )
        if confirmed:
            self._delete_and_refresh(
                lambda: self.database.confirm_income_received(transaction["id"]),
                "Não foi possível confirmar o recebimento",
            )

    def _new_account(self, _checked: bool = False) -> None:
        self._open_dialog(AccountDialog(self.database, self))

    def _edit_account(self, account: dict[str, Any]) -> None:
        self._open_dialog(AccountDialog(self.database, self, account=account))

    def _new_debt(self, _checked: bool = False) -> None:
        self._open_dialog(DebtDialog(self.database, self))

    def _edit_debt(self, debt: dict[str, Any]) -> None:
        self._open_dialog(DebtDialog(self.database, self, debt=debt))

    def _new_fixed_expense(self, _checked: bool = False, default_scope: str = "work") -> None:
        self._open_dialog(FixedExpenseDialog(self.database, self, default_scope=default_scope))

    def _edit_fixed_expense(self, expense: dict[str, Any]) -> None:
        self._open_dialog(FixedExpenseDialog(self.database, self, expense=expense))

    def _new_fixed_income(self, _checked: bool = False, default_scope: str = "work") -> None:
        self._open_dialog(FixedIncomeDialog(self.database, self, default_scope=default_scope))

    def _edit_fixed_income(self, income: dict[str, Any]) -> None:
        self._open_dialog(FixedIncomeDialog(self.database, self, income=income))

    def _new_goal(self, _checked: bool = False) -> None:
        self._open_dialog(GoalDialog(self.database, self))

    def _edit_goal(self, goal: dict[str, Any]) -> None:
        self._open_dialog(GoalDialog(self.database, self, goal=goal))

    def _delete_goal(self, goal: dict[str, Any]) -> None:
        if confirm_delete(self, f'a meta “{goal["name"]}”'):
            self._delete_and_refresh(
                lambda: self.database.delete_goal(goal["id"]),
                "Não foi possível excluir a meta",
            )

    def _new_budget(self, _checked: bool = False) -> None:
        self._open_dialog(BudgetDialog(self.database, self))

    def _edit_budget(self, budget: dict[str, Any]) -> None:
        self._open_dialog(BudgetDialog(self.database, self, budget=budget))

    def _delete_budget(self, budget: dict[str, Any]) -> None:
        if confirm_delete(self, f'o limite de “{budget["category"]}”'):
            self._delete_and_refresh(
                lambda: self.database.delete_budget(budget["id"]),
                "Não foi possível excluir o limite",
            )

    def _new_split_event(self, _checked: bool = False) -> None:
        self._open_dialog(SplitEventDialog(self.database, self))

    def _edit_split_event(self, event: dict[str, Any]) -> None:
        self._open_dialog(SplitEventDialog(self.database, self, event=event))

    def _delete_split_event(self, event: dict[str, Any]) -> None:
        if confirm_delete(self, f'o grupo “{event["name"]}” e todas as suas despesas'):
            self._delete_and_refresh(
                lambda: self.database.delete_split_event(event["id"]),
                "Não foi possível excluir o grupo",
            )

    def _new_split_expense(self, event: dict[str, Any]) -> None:
        expenses = self.database.split_expenses(event["id"])
        people: list[str] = []
        for item in expenses:
            for person in (item["paid_by"], *[part.strip() for part in item["participants"].split(",")]):
                if person and person not in people:
                    people.append(person)
        dialog = SplitExpenseDialog(self.database, event["id"], self, existing_people=people)
        self._open_dialog(dialog)

    def _delete_split_expense(self, expense: dict[str, Any]) -> None:
        if confirm_delete(self, f'a despesa “{expense["description"]}”'):
            self._delete_and_refresh(
                lambda: self.database.delete_split_expense(expense["id"]),
                "Não foi possível excluir a despesa",
            )

    def _new_investment(self, _checked: bool = False) -> None:
        self._open_dialog(InvestmentDialog(self.database, self))

    def _edit_investment(self, investment: dict[str, Any]) -> None:
        self._open_dialog(InvestmentDialog(self.database, self, investment=investment))

    def _delete_investment(self, investment: dict[str, Any]) -> None:
        if confirm_delete(self, f'o investimento “{investment["name"]}”'):
            self._delete_and_refresh(
                lambda: self.database.delete_investment(investment["id"]),
                "Não foi possível excluir o investimento",
            )

    def _delete_and_refresh(self, operation: Callable[[], None], title: str) -> None:
        try:
            operation()
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, title, str(error))
            return
        self._refresh_pages()

    def _save_profile(self, manager: str, business: str) -> None:
        self.database.update_workspace(manager, business)
        workspace = self.database.workspace() or {}
        first_name = workspace.get("manager", "visitante").split()[0]
        self.section_label.setText(self.NAVIGATION[self.pages.currentIndex()].upper())
        self._refresh_pages()
        QMessageBox.information(self, "Perfil atualizado", f"Perfil salvo. Olá, {first_name}!")

    def _change_theme(self, theme_mode: str, accent_color: str) -> None:
        self.database.update_settings(theme_mode, accent_color)
        application = QApplication.instance()
        if application is not None:
            application.setStyleSheet(build_stylesheet(theme_mode, accent_color))

    def _backup_database(self) -> None:
        suggested = f"summit-backup-{date.today().isoformat()}.db"
        path, _selected = QFileDialog.getSaveFileName(
            self, "Salvar backup", suggested, "Banco de dados (*.db)"
        )
        if not path:
            return
        try:
            destination = self.database.backup_to(path)
        except OSError as error:
            QMessageBox.warning(self, "Não foi possível salvar o backup", str(error))
            return
        QMessageBox.information(self, "Backup concluído", f"Cópia salva em:\n{destination}")


class OnboardingWindow(QMainWindow):
    completed = Signal()

    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self.step = 0
        self.setWindowTitle("Bem-vindo ao Summit")
        self.setMinimumSize(900, 590)
        self.resize(980, 650)
        root = QWidget()
        root.setObjectName("Root")
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        shell.addWidget(self._welcome_panel(), 9)
        shell.addWidget(self._form_panel(), 11)
        self.setCentralWidget(root)
        make_frameless(self)

    def _welcome_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("WelcomePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(42, 38, 42, 34)
        brand = QHBoxLayout()
        mark = label("▲", "BrandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(35, 35)
        brand.addWidget(mark)
        brand.addWidget(label("summit.", "Brand"))
        brand.addStretch()
        layout.addLayout(brand)
        layout.addStretch()
        kicker = label("✦  BEM-VINDO AO SUMMIT", "Purple")
        kicker.setStyleSheet("font-size: 10px; font-weight: 700; color: #b39bff;")
        layout.addWidget(kicker)
        title = label("Clareza para chegar\nmais longe.", "PageTitle")
        title.setStyleSheet("font-size: 38px; font-weight: 800; color: #ffffff;")
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(label("Uma visão simples e inteligente da sua vida financeira, seja em casa ou no seu negócio.", "Muted", True))
        layout.addStretch()
        quote = label("“Organização financeira é sobre criar novas possibilidades.”", "Tiny", True)
        quote.setStyleSheet("background: #2a1d3c; border: 1px solid #3c2a52; border-radius: 10px; padding: 15px; color: #a99db4;")
        layout.addWidget(quote)
        return panel

    def _form_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(54, 38, 54, 32)
        self.steps_label = label("1  ●────────○────────○  3", "Purple")
        self.steps_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.steps_label)
        layout.addStretch()

        self.form_stack = QStackedWidget()
        self.manager = text_field("Ex.: Alex Fernandes")
        self.business = text_field("Ex.: Estúdio de tatuagem")
        self.account_name = text_field("Ex.: Conta principal")
        self.initial_balance = QDoubleSpinBox()
        self.initial_balance.setRange(-999_999_999, 999_999_999)
        self.initial_balance.setDecimals(2)
        self.initial_balance.setPrefix("R$ ")
        self.initial_balance.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.form_stack.addWidget(self._step_widget("VAMOS COMEÇAR", "Como podemos chamar você?", "Esse nome será usado para deixar sua experiência mais pessoal.", "Seu nome", self.manager))
        self.form_stack.addWidget(self._step_widget("CONTE UM POUCO", "Qual é o seu momento?", "Pode ser sua casa, profissão, estúdio ou atividade principal.", "Atividade ou espaço", self.business))

        last = QWidget()
        last_layout = QVBoxLayout(last)
        last_layout.setContentsMargins(0, 0, 0, 0)
        last_layout.addWidget(label("ÚLTIMO PASSO", "Purple"))
        last_layout.addWidget(label("Configure sua primeira conta", "PageTitle"))
        last_layout.addWidget(label("Informe o ponto de partida. Você poderá organizar outros dados depois.", "Muted", True))
        last_layout.addSpacing(16)
        last_layout.addWidget(label("Nome da conta", "FieldLabel"))
        last_layout.addWidget(self.account_name)
        last_layout.addWidget(label("Saldo atual", "FieldLabel"))
        last_layout.addWidget(self.initial_balance)
        self.form_stack.addWidget(last)
        layout.addWidget(self.form_stack)
        layout.addStretch()

        actions = QHBoxLayout()
        self.back = QPushButton("Voltar")
        self.back.setObjectName("Secondary")
        self.back.clicked.connect(self._previous)
        self.back.setVisible(False)
        self.continue_button = QPushButton("Continuar  →")
        self.continue_button.setObjectName("Primary")
        self.continue_button.clicked.connect(self._next)
        actions.addWidget(self.back)
        actions.addStretch()
        actions.addWidget(self.continue_button)
        layout.addLayout(actions)
        demo = QPushButton("Explorar com dados de demonstração")
        demo.setObjectName("TextButton")
        demo.clicked.connect(self._start_demo)
        layout.addWidget(demo, alignment=Qt.AlignmentFlag.AlignCenter)
        return panel

    @staticmethod
    def _step_widget(kicker: str, title: str, description: str, field_name: str, field: QWidget) -> QWidget:
        step = QWidget()
        layout = QVBoxLayout(step)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label(kicker, "Purple"))
        layout.addWidget(label(title, "PageTitle"))
        layout.addWidget(label(description, "Muted", True))
        layout.addSpacing(16)
        layout.addWidget(label(field_name, "FieldLabel"))
        layout.addWidget(field)
        return step

    def _next(self) -> None:
        current_value = self.manager.text() if self.step == 0 else self.business.text() if self.step == 1 else self.account_name.text()
        if not current_value.strip():
            QMessageBox.warning(self, "Campo obrigatório", "Preencha este campo para continuar.")
            return
        if self.step < 2:
            self.step += 1
            self.form_stack.setCurrentIndex(self.step)
            self.back.setVisible(True)
            self.continue_button.setText("Entrar no Summit  →" if self.step == 2 else "Continuar  →")
            self.steps_label.setText("1  ●────────●────────○  3" if self.step == 1 else "1  ●────────●────────●  3")
            return
        self._finish(False)

    def _previous(self) -> None:
        if self.step == 0:
            return
        self.step -= 1
        self.form_stack.setCurrentIndex(self.step)
        self.back.setVisible(self.step > 0)
        self.continue_button.setText("Continuar  →")
        self.steps_label.setText("1  ●────────○────────○  3" if self.step == 0 else "1  ●────────●────────○  3")

    def _start_demo(self) -> None:
        self.manager.setText("Alex")
        self.business.setText("Estúdio de tatuagem")
        self.account_name.setText("Conta do estúdio")
        self.initial_balance.setValue(12480)
        self._finish(True)

    def _finish(self, demo: bool) -> None:
        try:
            self.database.setup_workspace(
                self.manager.text(), self.business.text(), self.account_name.text(),
                self.initial_balance.value(), demo=demo,
            )
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Não foi possível configurar", str(error))
            return
        self.completed.emit()
        self.close()
