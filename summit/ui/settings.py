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

from summit.ui.common import Panel

class SettingsPage(QWidget):
    def __init__(
        self,
        snapshot: dict[str, Any],
        settings: dict[str, Any],
        save_profile: Callable[[str, str], None],
        change_theme: Callable[[str, str], None],
        backup: Callable[[], None],
        manage_categories: Callable[[], None],
        database: Database,
        reload_settings_page: Callable[[], None],
    ) -> None:
        super().__init__()
        self.settings = settings
        self.change_theme = change_theme
        self.database = database
        self.reload_settings_page = reload_settings_page
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

        theme_panel = Panel("Aparência", "Alternar entre tema escuro e claro")
        mode_row = QHBoxLayout()
        mode_row.setSpacing(12)
        self.theme_toggle = ThemeToggle(settings.get("theme_mode", "dark"))

        def _on_theme_changed(mode: str) -> None:
            self.change_theme(mode, DEFAULT_ACCENT)
            self.settings["theme_mode"] = mode

        self.theme_toggle.themeChanged.connect(_on_theme_changed)
        mode_row.addWidget(self.theme_toggle)
        mode_row.addStretch()
        theme_panel.body.addLayout(mode_row)
        theme_panel.body.addSpacing(10)
        theme_panel.body.addWidget(label(
            "O Summit usa um único tom de roxo como destaque, no claro e no escuro, "
            "para manter contraste e legibilidade consistentes em todas as páginas.",
            "Tiny", True,
        ))
        page.addWidget(theme_panel)

        security_panel = Panel("Segurança", "Proteja o acesso ao Summit com um PIN")
        pin_enabled = self.database.is_pin_enabled()
        security_panel.body.addWidget(label(
            "Proteção por PIN ativada." if pin_enabled else "Proteção por PIN desativada.",
            "Tiny", True,
        ))
        security_panel.body.addSpacing(10)
        security_row = QHBoxLayout()
        security_row.setSpacing(10)

        def _open_pin_dialog() -> None:
            dialog = PinDialog(self.database, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.reload_settings_page()

        def _disable_pin() -> None:
            reply = QMessageBox.question(
                self, "Desativar PIN",
                "Tem certeza de que deseja desativar a proteção por PIN?",
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.database.disable_pin()
                self.reload_settings_page()

        primary_button = QPushButton("Alterar PIN" if pin_enabled else "Ativar PIN")
        primary_button.setObjectName("Secondary")
        primary_button.clicked.connect(_open_pin_dialog)
        security_row.addWidget(primary_button)
        if pin_enabled:
            disable_button = QPushButton("Desativar PIN")
            disable_button.setObjectName("Secondary")
            disable_button.clicked.connect(_disable_pin)
            security_row.addWidget(disable_button)
        security_row.addStretch()
        security_panel.body.addLayout(security_row)
        page.addWidget(security_panel)

        categories_panel = Panel(
            "Categorias",
            "Catálogo usado para sugerir categorias em lançamentos, contas fixas e dívidas",
        )
        categories_count = len(snapshot.get("categories", []))
        categories_panel.body.addWidget(label(
            f"{categories_count} categoria" + ("" if categories_count == 1 else "s") + " no catálogo.",
            "Tiny", True,
        ))
        categories_panel.body.addSpacing(10)
        categories_row = QHBoxLayout()
        edit_categories_button = QPushButton("Editar lista")
        edit_categories_button.setObjectName("Secondary")
        edit_categories_button.clicked.connect(manage_categories)
        categories_row.addWidget(edit_categories_button)
        categories_row.addStretch()
        categories_panel.body.addLayout(categories_row)
        page.addWidget(categories_panel)

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


