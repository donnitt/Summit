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
        self.category = CategoryField(database.categories, "Ex.: Equipamentos ou Empréstimo", source.get("category", ""))
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

    def _values(self) -> dict[str, Any]:
        return dict(
            description=self.description.text(), creditor=self.creditor.text(),
            category=self.category.text(), total_amount=self.total.value(),
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
        answer = QMessageBox.question(
            self, "Confirmar quitação", "Confirmar que esta dívida foi totalmente quitada?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
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
        self.category = CategoryField(database.categories, "Ex.: Serviços, Casa ou Materiais")
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
        self.category.setText(source.get("category", ""))
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
            ("Situação", self.status), ("Uso", self.scope), ("Conta", self.account),
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

    def _save(self) -> None:
        try:
            values = dict(
                description=self.description.text(),
                category=self.category.text(),
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
        self.category = CategoryField(
            database.categories,
            "Ex.: Salário ou Contratos" if fixed_kind == "income" else "Ex.: Moradia ou Contas",
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
            ("Uso", self.scope), ("Conta usada", self.account),
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

    def _save(self) -> None:
        try:
            values = dict(
                description=self.description.text(), category=self.category.text(), amount=self.amount.value(),
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
        self.category = CategoryField(database.categories, "Use a mesma categoria dos lançamentos", source.get("category", ""))
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

    def _save(self) -> None:
        try:
            values = dict(category=self.category.text(), monthly_limit=self.limit.value(), notes=self.notes.toPlainText())
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


class CategoryManagerDialog(QDialog):
    """Editable list of the category catalog: rename, remove or add one."""

    changed = Signal()

    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.setWindowTitle("Editar categorias · Summit")
        self.setModal(True)
        self.setMinimumSize(480, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(12)
        layout.addWidget(label("Editar categorias", "PageTitle"))
        layout.addWidget(label(
            "Renomeie ou remova categorias do catálogo sugerido. Excluir uma "
            "categoria daqui não apaga lançamentos que já usam esse texto.",
            "Muted", True,
        ))

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.new_category = text_field("Nova categoria")
        self.new_category.returnPressed.connect(self._add)
        add_button = QPushButton("Adicionar")
        add_button.setObjectName("Secondary")
        add_button.clicked.connect(self._add)
        add_row.addWidget(self.new_category, 1)
        add_row.addWidget(add_button)
        layout.addLayout(add_row)

        self.list = QListWidget()
        self.list.setObjectName("CategoryManagerList")
        self.list.setSpacing(4)
        self.list.setStyleSheet(
            "QListWidget#CategoryManagerList { border: 0; background: transparent; }"
        )
        layout.addWidget(self.list, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        close_button = QPushButton("Fechar")
        close_button.setObjectName("Primary")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._reload()

    def _reload(self) -> None:
        self.list.clear()
        for name in self.database.categories():
            row_widget = QFrame()
            row_widget.setObjectName("CategoryManagerRow")
            row_widget.setStyleSheet(
                "QFrame#CategoryManagerRow { background: #1c1526; border-radius: 10px; }"
            )
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(10, 6, 10, 6)
            row.setSpacing(8)
            field = QLineEdit(name)
            field.setObjectName("CategoryManagerField")
            rename_button = QPushButton("Salvar")
            rename_button.setObjectName("Secondary")
            delete_button = QPushButton("Excluir")
            delete_button.setObjectName("DangerAction")
            rename_button.clicked.connect(
                lambda _checked=False, old=name, source_field=field: self._rename(old, source_field.text())
            )
            delete_button.clicked.connect(lambda _checked=False, current=name: self._delete(current))
            row.addWidget(field, 1)
            row.addWidget(rename_button)
            row.addWidget(delete_button)
            item = QListWidgetItem()
            item.setSizeHint(row_widget.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, row_widget)

    def _add(self) -> None:
        try:
            self.database.add_category(self.new_category.text())
        except ValueError as error:
            QMessageBox.warning(self, "Não foi possível adicionar", str(error))
            return
        self.new_category.clear()
        self._reload()
        self.changed.emit()

    def _rename(self, old_name: str, new_text: str) -> None:
        if new_text.strip() == old_name:
            return
        try:
            self.database.rename_category(old_name, new_text)
        except ValueError as error:
            QMessageBox.warning(self, "Não foi possível renomear", str(error))
            return
        self._reload()
        self.changed.emit()

    def _delete(self, name: str) -> None:
        if not confirm_delete(self, f"a categoria “{name}”"):
            return
        try:
            self.database.delete_category(name)
        except ValueError as error:
            QMessageBox.warning(self, "Não foi possível excluir", str(error))
            return
        self._reload()
        self.changed.emit()


