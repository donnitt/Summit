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

class MetricCard(QFrame):
    def __init__(
        self,
        title: str,
        value: str,
        accent: str,
        object_name: str,
        detail: str,
        key: str = "",
        hidden: bool = False,
        on_toggle: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName(object_name)
        self.setMinimumHeight(137)
        self.setMaximumHeight(150)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 15, 18, 15)
        head = QHBoxLayout()
        head.addWidget(label(title, "Muted"))
        head.addStretch()
        if on_toggle is not None:
            eye = QPushButton()
            eye.setObjectName("MetricEyeToggle")
            eye.setFlat(True)
            eye.setCursor(Qt.CursorShape.PointingHandCursor)
            eye.setIcon(eye_icon(not hidden, accent, size=16))
            eye.setIconSize(QSize(16, 16))
            eye.setFixedSize(24, 24)
            eye.setToolTip("Mostrar este valor" if hidden else "Ocultar este valor")
            eye.clicked.connect(lambda _checked=False, current_key=key: on_toggle(current_key))
            head.addWidget(eye)
        else:
            icon = label("●")
            icon.setStyleSheet(f"color: {accent}; font-size: 18px;")
            head.addWidget(icon)
        layout.addLayout(head)
        value_label = label(value, "MetricValue")
        layout.addWidget(value_label)
        layout.addStretch()
        detail_label = label(detail, "Tiny")
        detail_label.setStyleSheet(f"color: {accent};")
        layout.addWidget(detail_label)


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


