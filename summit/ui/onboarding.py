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

class OnboardingWindow(QMainWindow):
    completed = Signal()

    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self.step = 0
        self.setWindowTitle("Bem-vindo ao Summit")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(900, 590)
        self.resize(980, 650)
        root = QWidget()
        root.setObjectName("Root")
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        shell.addWidget(self._welcome_panel(), 9)
        shell.addWidget(self._form_panel(), 11)
        apply_frameless_chrome(self, root, show_maximize=False)

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
