"""PIN lock screen and PIN management dialog.

Split out of summit/ui.py: this module has almost no coupling to the rest
of the UI beyond a handful of shared helpers (label, apply_frameless_chrome,
app_icon), so it is the safest first piece to extract into its own file.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from summit.chrome import apply_frameless_chrome
from summit.database import Database
from summit.resources import app_icon
from summit.widgets_common import label


class LockWindow(QMainWindow):
    """Full-screen PIN gate shown on launch when lock protection is active."""

    unlocked = Signal()
    PIN_LENGTH = 4

    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self.entered = ""
        self.setWindowTitle("Summit — Bloqueado")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(420, 600)
        self.resize(420, 600)

        root = QWidget()
        root.setObjectName("Root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(48, 48, 48, 40)
        layout.setSpacing(0)

        brand = QHBoxLayout()
        brand.setSpacing(8)
        mark = label("▲", "BrandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(30, 30)
        brand.addStretch()
        brand.addWidget(mark)
        brand.addWidget(label("summit.", "Brand"))
        brand.addStretch()
        layout.addLayout(brand)
        layout.addStretch()

        title = label("Digite seu PIN", "PageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(label("Desbloqueie o Summit para continuar.", "Muted", True), alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(20)

        dots_row = QHBoxLayout()
        dots_row.setSpacing(14)
        dots_row.addStretch()
        self.dots = [label("○", "PinDot") for _ in range(self.PIN_LENGTH)]
        for dot in self.dots:
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dots_row.addWidget(dot)
        dots_row.addStretch()
        layout.addLayout(dots_row)
        layout.addSpacing(10)

        self.error_label = label("", "PinError")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setFixedHeight(20)
        layout.addWidget(self.error_label)
        layout.addSpacing(10)

        keypad = QGridLayout()
        keypad.setSpacing(12)
        positions = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
            ("⌫", 3, 0), ("0", 3, 1),
        ]
        for text, row, col in positions:
            button = QPushButton(text)
            button.setObjectName("Keypad")
            button.setFixedSize(64, 64)
            if text == "⌫":
                button.clicked.connect(self._backspace)
            else:
                button.clicked.connect(lambda _checked=False, digit=text: self._add_digit(digit))
            keypad.addWidget(button, row, col)
        keypad_wrap = QHBoxLayout()
        keypad_wrap.addStretch()
        keypad_wrap.addLayout(keypad)
        keypad_wrap.addStretch()
        layout.addLayout(keypad_wrap)
        layout.addStretch()

        apply_frameless_chrome(self, root, show_maximize=False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _add_digit(self, digit: str) -> None:
        if len(self.entered) >= self.PIN_LENGTH:
            return
        self.entered += digit
        self._refresh_dots()
        if len(self.entered) == self.PIN_LENGTH:
            self._check_pin()

    def _backspace(self) -> None:
        self.entered = self.entered[:-1]
        self.error_label.setText("")
        self._refresh_dots()

    def _refresh_dots(self) -> None:
        for index, dot in enumerate(self.dots):
            dot.setText("●" if index < len(self.entered) else "○")

    def _check_pin(self) -> None:
        if self.database.verify_pin(self.entered):
            self.unlocked.emit()
            self.close()
            return
        self.error_label.setText("PIN incorreto. Tente novamente.")
        self.entered = ""
        self._refresh_dots()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        key = event.key()
        text = event.text()
        if text.isdigit():
            self._add_digit(text)
        elif key == Qt.Key.Key_Backspace:
            self._backspace()
        else:
            super().keyPressEvent(event)


class PinDialog(QDialog):
    """Create, change, or remove the lock PIN."""

    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.setObjectName("PinDialog")
        self.setWindowTitle("Alterar PIN" if database.is_pin_enabled() else "Ativar PIN")
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.addWidget(label(
            "Alterar seu PIN" if database.is_pin_enabled() else "Ativar proteção por PIN",
            "PageTitle",
        ))

        self.current_field: QLineEdit | None = None
        if database.is_pin_enabled():
            layout.addWidget(label("PIN ATUAL", "FieldLabel"))
            self.current_field = self._pin_field()
            layout.addWidget(self.current_field)

        layout.addWidget(label("NOVO PIN (4 dígitos)", "FieldLabel"))
        self.new_field = self._pin_field()
        layout.addWidget(self.new_field)

        layout.addWidget(label("CONFIRMAR NOVO PIN", "FieldLabel"))
        self.confirm_field = self._pin_field()
        layout.addWidget(self.confirm_field)

        layout.addWidget(label(
            "O Summit é 100% offline: não há recuperação automática de PIN. "
            "Se você esquecer, será necessário desativar a proteção manualmente pelo arquivo de dados.",
            "Tiny", True,
        ))

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("Secondary")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("Salvar PIN")
        confirm.setObjectName("Primary")
        confirm.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

    @staticmethod
    def _pin_field() -> QLineEdit:
        field = QLineEdit()
        field.setEchoMode(QLineEdit.EchoMode.Password)
        field.setMaxLength(4)
        field.setPlaceholderText("••••")
        return field

    def _save(self) -> None:
        if self.current_field is not None:
            if not self.database.verify_pin(self.current_field.text()):
                QMessageBox.warning(self, "PIN atual incorreto", "Digite o PIN atual corretamente para continuar.")
                return
        new_pin = self.new_field.text().strip()
        confirm_pin = self.confirm_field.text().strip()
        if new_pin != confirm_pin:
            QMessageBox.warning(self, "PINs não coincidem", "O novo PIN e a confirmação devem ser iguais.")
            return
        try:
            self.database.set_pin(new_pin)
        except ValueError as error:
            QMessageBox.warning(self, "PIN inválido", str(error))
            return
        self.accept()
