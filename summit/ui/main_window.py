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

from summit.ui.dashboard import DashboardPage
from summit.ui.movements import MovementsPage, DrillDownDialog
from summit.ui.import_review import run_import_flow
from summit.ui.accounts_debts import (
    FixedEntriesPage,
    AccountsPage,
    DebtsPage,
    PlanningPage,
    InvestmentsPage,
)
from summit.ui.dialogs import (
    AccountDialog,
    DebtDialog,
    TransactionDialog,
    FixedExpenseDialog,
    FixedIncomeDialog,
    GoalDialog,
    BudgetDialog,
    InvestmentDialog,
    CategoryManagerDialog,
)
from summit.ui.reports import ReportsPage
from summit.ui.settings import SettingsPage

class MainWindow(QMainWindow):
    NAVIGATION = (
        "Visão geral", "Movimentações", "Fixos", "Contas", "Dívidas",
        "Planejamento", "Investimentos", "Relatórios", "Configurações",
    )

    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self.nav_buttons: list[QPushButton] = []
        self.dashboard_period = "monthly"
        self.account_visibility: dict[int, bool] = {}
        self.metric_visibility: dict[str, bool] = {}
        self._metric_snapshot: dict[str, bool] | None = None
        self.category_display_mode = "amount"
        self.movements_filter: dict[str, str] = {
            "preset": "all", "start": "", "end": "", "search": "",
        }
        set_values_hidden(False)
        self.setWindowTitle("Summit · Visão financeira")
        self.setWindowIcon(app_icon())
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
        # Cada página tem sua própria QScrollArea (fixas, criadas uma vez).
        # O conteúdo de dentro delas é que é (re)construído sob demanda —
        # ver _ensure_page_built/_build_page.
        self.page_scrolls = [self._make_page_scroll() for _ in self.NAVIGATION]
        for page_scroll in self.page_scrolls:
            self.pages.addWidget(page_scroll)
        content_layout.addWidget(self.pages)
        shell.addWidget(content, 1)
        apply_frameless_chrome(self, root)
        # Todas as páginas começam "sujas" (nunca construídas); só a
        # primeira é montada de cara, as outras só quando o usuário navegar
        # até elas — evita reconstruir as 9 páginas inteiras sempre que
        # qualquer coisa muda.
        self._pages_dirty: set[int] = set(range(len(self.NAVIGATION)))
        self._ensure_page_built(0, force=True)
        self.pages.setCurrentIndex(0)

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
        settings = self.database.settings()
        self.theme_toggle = ThemeToggle(settings.get("theme_mode", "dark"))
        self.theme_toggle.themeChanged.connect(lambda mode: self._change_theme(mode, DEFAULT_ACCENT))
        layout.addWidget(self.theme_toggle)
        layout.addSpacing(6)
        self.privacy_button = QPushButton("  Valores")
        self.privacy_button.setObjectName("Secondary")
        self.privacy_button.setCheckable(True)
        self.privacy_button.setIcon(eye_icon(True, PURPLE))
        self.privacy_button.setIconSize(QSize(18, 18))
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
        if hidden:
            # Guarda o estado atual de cada card independente antes de
            # forçar a ocultação geral, para poder devolvê-lo depois.
            self._metric_snapshot = dict(self.metric_visibility)
            for key in self._known_metric_keys():
                self.metric_visibility[key] = True
        else:
            if self._metric_snapshot is not None:
                self.metric_visibility = dict(self._metric_snapshot)
            else:
                self.metric_visibility = {}
            self._metric_snapshot = None
        self.privacy_button.setIcon(eye_icon(not hidden, "#ffffff" if hidden else PURPLE))
        self.privacy_button.setToolTip(
            "Mostrar os valores financeiros" if hidden else "Ocultar todos os valores financeiros exibidos"
        )
        self._refresh_pages()

    @staticmethod
    def _known_metric_keys() -> tuple[str, ...]:
        return ("balance", "income", "expense", "to_receive", "saved", "planned", "fixed", "result")

    def _toggle_metric_visibility(self, key: str) -> None:
        current = self.metric_visibility.get(key, values_hidden())
        self.metric_visibility[key] = not current
        # Uma alteração manual assume o controle desse card: o "geral"
        # não deve mais sobrescrever esse valor específico ao ser
        # pressionado novamente para mostrar tudo.
        self._metric_snapshot = None
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

    def _toggle_category_display(self) -> None:
        self.category_display_mode = "percent" if self.category_display_mode == "amount" else "amount"
        self._refresh_pages()

    def _change_movements_filter(self, preset: str, start: str, end: str, search: str) -> None:
        self.movements_filter = {"preset": preset, "start": start, "end": end, "search": search}
        self._refresh_pages()

    def _open_drilldown(
        self,
        category: str | None = None,
        start: str | None = None,
        end: str | None = None,
        title: str = "Lançamentos",
    ) -> None:
        snapshot = self.database.snapshot()
        start_date = date.fromisoformat(start) if start else None
        end_date = date.fromisoformat(end) if end else None

        def matches(item: dict[str, Any]) -> bool:
            if item["status"] != "paid":
                return False
            if category is not None and item["category"] != category:
                return False
            if start_date and end_date:
                item_date = date.fromisoformat(item["transaction_date"])
                if not (start_date <= item_date <= end_date):
                    return False
            return True

        items = sorted(
            (item for item in snapshot["transactions"] if matches(item)),
            key=lambda item: item["transaction_date"],
            reverse=True,
        )
        dialog = DrillDownDialog(
            title, items, self._edit_transaction, self, mode=self.database.settings()["theme_mode"],
        )
        dialog.exec()

    def _show_page(self, index: int) -> None:
        self._ensure_page_built(index)
        self.pages.setCurrentIndex(index)
        if 0 <= index < len(self.page_scrolls):
            page_scroll = self.page_scrolls[index]
            page_scroll.horizontalScrollBar().setValue(0)
            page_scroll.verticalScrollBar().setValue(0)
        self.section_label.setText(self.NAVIGATION[index].upper())
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)

    @staticmethod
    def _make_page_scroll() -> QScrollArea:
        # Each page gets its own scroll area so the scrollbar range
        # reflects only that page's content, not the tallest page in
        # the app.
        page_scroll = QScrollArea()
        page_scroll.setObjectName("PageScroll")
        page_scroll.setWidgetResizable(True)
        page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page_scroll.viewport().setStyleSheet("background: transparent;")
        page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        return page_scroll

    def _refresh_pages(self) -> None:
        """Sinaliza que os dados mudaram.

        Em vez de reconstruir as 9 páginas na hora (caro: recarrega o
        banco e recria cada widget/tabela/gráfico), marcamos todas como
        "sujas" e reconstruímos de imediato só a que está visível agora —
        as demais são reconstruídas sob demanda, na próxima vez que o
        usuário navegar até elas (ver _ensure_page_built).
        """
        self._pages_dirty = set(range(len(self.NAVIGATION)))
        current = self.pages.currentIndex() if self.pages.count() else 0
        self._ensure_page_built(current, force=True)

    def _ensure_page_built(self, index: int, force: bool = False) -> None:
        already_built = self.page_scrolls[index].widget() is not None
        if already_built and not force and index not in self._pages_dirty:
            return
        snapshot = self.database.snapshot()
        page_widget = self._build_page(index, snapshot)
        wrapper = QWidget()
        wrapper.setObjectName("PageContainer")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(32, 24, 32, 34)
        layout.addWidget(page_widget)
        # QScrollArea.setWidget() já libera o widget anterior sozinho.
        self.page_scrolls[index].setWidget(wrapper)
        self._pages_dirty.discard(index)

    def _build_page(self, index: int, snapshot: dict[str, Any]) -> QWidget:
        # Lista de "construtores" preguiçosos: montar essa lista é barato
        # (só cria lambdas), o trabalho de verdade só acontece no builders[index]()
        # chamado logo abaixo — ou seja, construímos só a página pedida.
        builders: list[Callable[[], QWidget]] = [
            lambda: DashboardPage(
                snapshot,
                lambda: self._new_transaction(),
                self._confirm_receipt,
                self._edit_transaction,
                self.dashboard_period,
                self._change_dashboard_period,
                self.metric_visibility,
                self._toggle_metric_visibility,
                self.database.settings()["theme_mode"],
                self.category_display_mode,
                self._toggle_category_display,
                self._open_drilldown,
            ),
            lambda: MovementsPage(
                snapshot,
                lambda kind, status: self._new_transaction(kind=kind, status=status),
                self._edit_transaction,
                self._import_statement,
                self.movements_filter,
                self._change_movements_filter,
            ),
            lambda: FixedEntriesPage(
                snapshot,
                lambda scope: self._new_fixed_income(default_scope=scope),
                self._edit_fixed_income,
                lambda scope: self._new_fixed_expense(default_scope=scope),
                self._edit_fixed_expense,
            ),
            lambda: AccountsPage(
                snapshot, self._new_account, self._edit_account,
                self.account_visibility, self._toggle_account_visibility,
            ),
            lambda: DebtsPage(snapshot["debts"], self._new_debt, self._edit_debt),
            lambda: PlanningPage(
                snapshot,
                self._new_goal,
                self._edit_goal,
                self._delete_goal,
                self._new_budget,
                self._edit_budget,
                self._delete_budget,
                self.metric_visibility,
                self._toggle_metric_visibility,
            ),
            lambda: InvestmentsPage(
                snapshot["investments"],
                self._new_investment,
                self._edit_investment,
                self._delete_investment,
            ),
            lambda: ReportsPage(snapshot),
            lambda: SettingsPage(
                snapshot,
                self.database.settings(),
                self._save_profile,
                self._change_theme,
                self._backup_database,
                self._manage_categories,
                self.database,
                self._refresh_pages,
            ),
        ]
        return builders[index]()

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

    def _import_statement(self) -> None:
        if run_import_flow(self.database, self):
            self._refresh_pages()

    def _confirm_receipt(self, transaction: dict[str, Any]) -> None:
        account = next(
            (item["name"] for item in self.database.accounts() if item["id"] == transaction["account_id"]),
            "a conta selecionada",
        )
        answer = QMessageBox.question(
            self,
            "Confirmar recebimento",
            f'Confirmar que {brl(float(transaction["amount"]))} de “{transaction["description"]}” entrou em {account}?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
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
        for toggle in self.findChildren(ThemeToggle):
            if toggle.mode() != theme_mode:
                toggle.set_mode(theme_mode)

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

    def _manage_categories(self) -> None:
        dialog = CategoryManagerDialog(self.database, self)
        dialog.changed.connect(self._refresh_pages)
        dialog.exec()


