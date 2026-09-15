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

class CashFlowChart(QWidget):
    barClicked = Signal(dict)

    def __init__(
        self,
        values: list[dict[str, Any]],
        hide_income: bool = False,
        hide_expense: bool = False,
        mode: str = "dark",
    ) -> None:
        super().__init__()
        self.values = values
        self.hide_income = hide_income
        self.hide_expense = hide_expense
        self.mode = mode
        self._points: list[QPointF] = []
        self._hover_index: int | None = None
        self.setMinimumHeight(235)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def _colors(self) -> dict[str, str]:
        if self.mode == "light":
            return {"grid": "#e4dff0", "axis": "#5c5468", "tick": "#6f6579", "guide": "#c9bfe0", "hover_bg": "#f0ecfa"}
        return {"grid": "#2a2233", "axis": "#756b80", "tick": "#716778", "guide": "#40374d", "hover_bg": "#1c1526"}

    def paintEvent(self, _event: Any) -> None:
        colors = self._colors()
        flow = flow_colors(self.mode)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = self.rect().adjusted(42, 15, -18, -31)
        self._points = []
        if area.width() <= 0 or area.height() <= 0:
            return
        maximum = max([item[key] for item in self.values for key in ("income", "expense")] + [1000])
        maximum = math.ceil(maximum / 2000) * 2000

        painter.setFont(QFont("Segoe UI", 8))
        axis_hidden = values_hidden() or (self.hide_income and self.hide_expense)
        for index in range(5):
            y = area.top() + index * area.height() / 4
            painter.setPen(QPen(QColor(colors["grid"]), 1, Qt.PenStyle.DashLine))
            painter.drawLine(area.left(), int(y), area.right(), int(y))
            value = maximum * (1 - index / 4)
            painter.setPen(QColor(colors["axis"]))
            axis_label = "••" if axis_hidden else f"{value / 1000:.0f}k"
            painter.drawText(0, int(y - 8), 36, 16, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, axis_label)

        points_by_key: dict[str, list[QPointF]] = {"income": [], "expense": []}
        step = area.width() / max(len(self.values) - 1, 1)
        small_font = len(self.values) > 0 and max(len(item["label"]) for item in self.values) > 5
        label_font_size = 6.5 if small_font else 8
        for index, item in enumerate(self.values):
            x = area.left() + index * step
            self._points.append(QPointF(x, area.center().y()))
            for key in points_by_key:
                y = area.bottom() - (float(item.get(key, 0)) / maximum) * area.height()
                points_by_key[key].append(QPointF(x, y))

        # Hover affordance: a soft column + vertical guide behind the
        # nearest period, so it's clear before clicking that the chart is
        # interactive and exactly which period a click will open.
        if self._hover_index is not None:
            x = self._points[self._hover_index].x()
            half_step = step / 2 if step else 18
            painter.fillRect(QRectF(x - half_step, area.top(), half_step * 2, area.height()), QColor(colors["hover_bg"]))
            painter.setPen(QPen(QColor(colors["guide"]), 1, Qt.PenStyle.DashLine))
            painter.drawLine(int(x), area.top(), int(x), area.bottom())

        for index, item in enumerate(self.values):
            x = self._points[index].x()
            painter.setPen(QColor(colors["tick"] if index != self._hover_index else flow["income"]))
            painter.setFont(QFont("Segoe UI", label_font_size, QFont.Weight.Bold if index == self._hover_index else QFont.Weight.Normal))
            width = 46 if small_font else 36
            painter.drawText(int(x - width / 2), area.bottom() + 9, width, 18, Qt.AlignmentFlag.AlignCenter, item["label"])

        if not (values_hidden() or self.hide_income):
            self._draw_series(painter, area, points_by_key["income"], QColor(flow["income"]), QColor(155, 124, 255, 45))
        if not (values_hidden() or self.hide_expense):
            self._draw_series(painter, area, points_by_key["expense"], QColor(flow["expense"]), QColor(255, 157, 102, 18))

        if self._hover_index is not None:
            for key, color in (("income", flow["income"]), ("expense", flow["expense"])):
                hidden = values_hidden() or (self.hide_income if key == "income" else self.hide_expense)
                if hidden:
                    continue
                point = points_by_key[key][self._hover_index]
                painter.setBrush(QColor(color))
                painter.setPen(QPen(QColor(colors["hover_bg"]), 2))
                painter.drawEllipse(point, 4.5, 4.5)

    def _index_at(self, x: float) -> int | None:
        if not self._points:
            return None
        closest = min(range(len(self._points)), key=lambda i: abs(self._points[i].x() - x))
        return closest if abs(self._points[closest].x() - x) <= 28 else None

    def mouseMoveEvent(self, event: Any) -> None:
        index = self._index_at(event.position().x())
        if index != self._hover_index:
            self._hover_index = index
            self.update()
        if index is not None:
            item = self.values[index]
            hint = item.get("range_label", item["label"])
            self.setToolTip(f"{hint} · clique para ver os lançamentos")
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: Any) -> None:
        if self._hover_index is not None:
            self._hover_index = None
            self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            index = self._index_at(event.position().x())
            if index is not None:
                self.barClicked.emit(self.values[index])
        super().mouseReleaseEvent(event)

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
    slicePicked = Signal(str)

    def __init__(
        self,
        categories: list[tuple[str, float]],
        total: float,
        hidden: bool = False,
        mode: str = "dark",
        show_percent: bool = False,
    ) -> None:
        super().__init__()
        self.categories = categories
        self.total = total
        self.hidden = hidden
        self.mode = mode
        self.show_percent = show_percent
        self._hover_index: int | None = None
        self.setMinimumSize(175, 175)
        self.setMouseTracking(True)
        if categories:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _colors(self) -> dict[str, str]:
        if self.mode == "light":
            return {"empty": "#e3ddef", "hole": "#fbf9fe", "muted": "#6f6579", "strong": "#241c30"}
        return {"empty": "#30273a", "hole": "#171120", "muted": "#776d82", "strong": "#f4f0f8"}

    def _center_text(self) -> str:
        if self._hover_index is not None:
            name, amount = self.categories[self._hover_index]
            if self.hidden or values_hidden():
                return "••"
            if self.show_percent:
                percentage = round(amount / self.total * 100) if self.total else 0
                return f"{percentage}%"
            return brl(amount)
        if self.show_percent:
            return "100%" if self.total > 0 else "0%"
        return brl(self.total, hidden=self.hidden or values_hidden())

    def _center_subtext(self) -> str:
        if self._hover_index is not None:
            name, _amount = self.categories[self._hover_index]
            return name
        return "Total"

    def _slice_at(self, point: Any) -> int | None:
        if not self.categories or self.total <= 0:
            return None
        center = self.rect().center()
        dx, dy = point.x() - center.x(), point.y() - center.y()
        size = min(self.width(), self.height()) - 32
        radius = size / 2
        distance = math.hypot(dx, dy)
        if not (radius * 0.305 <= distance <= radius):
            return None
        angle = math.degrees(math.atan2(-dy, dx)) % 360
        # Slices are drawn clockwise starting at 90° (12 o'clock).
        sweep = (90 - angle) % 360
        cursor = 0.0
        for index, (_name, amount) in enumerate(self.categories):
            share = (amount / self.total) * 360
            if cursor <= sweep < cursor + share:
                return index
            cursor += share
        return None

    def paintEvent(self, _event: Any) -> None:
        colors = self._colors()
        palette = category_colors(self.mode)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width(), self.height()) - 32
        chart = QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)
        painter.setPen(Qt.PenStyle.NoPen)
        if not self.categories or self.total <= 0:
            painter.setBrush(QColor(colors["empty"]))
            painter.drawEllipse(chart)
        else:
            start = 90 * 16
            for index, (_name, amount) in enumerate(self.categories):
                span = -int((amount / self.total) * 360 * 16)
                color = QColor(palette[index % len(palette)])
                # A slight outward "pop" + brighten on hover — visible
                # confirmation of exactly what a click will open.
                if index == self._hover_index:
                    color = color.lighter(112)
                    offset_angle = math.radians(90 - (start / 16) - (-span / 16) / 2)
                    dx, dy = math.cos(offset_angle) * 4, -math.sin(offset_angle) * 4
                    painter.setBrush(color)
                    painter.drawPie(chart.translated(dx, dy), start, span)
                else:
                    painter.setBrush(color)
                    painter.drawPie(chart, start, span)
                start += span
        hole_size = size * 0.61
        hole = QRectF((self.width() - hole_size) / 2, (self.height() - hole_size) / 2, hole_size, hole_size)
        painter.setBrush(QColor(colors["hole"]))
        painter.drawEllipse(hole)
        painter.setPen(QColor(colors["muted"]))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(hole.adjusted(0, 22, 0, 0), Qt.AlignmentFlag.AlignHCenter, self._center_subtext())
        painter.setPen(QColor(colors["strong"]))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(hole.adjusted(0, 42, 0, 0), Qt.AlignmentFlag.AlignHCenter, self._center_text())

    def mouseMoveEvent(self, event: Any) -> None:
        index = self._slice_at(event.position().toPoint())
        if index != self._hover_index:
            self._hover_index = index
            self.update()
        if index is not None:
            name, amount = self.categories[index]
            percentage = round(amount / self.total * 100) if self.total else 0
            self.setToolTip(f"{name} · {percentage}% · clique para ver os lançamentos")
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: Any) -> None:
        if self._hover_index is not None:
            self._hover_index = None
            self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            index = self._slice_at(event.position().toPoint())
            if index is not None:
                name, _amount = self.categories[index]
                self.slicePicked.emit(name)
        super().mouseReleaseEvent(event)


