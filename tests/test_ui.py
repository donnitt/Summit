from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QPushButton, QTabWidget, QWidget

from summit.database import Database
from summit.security import LockWindow, PinDialog
from summit.ui import (
    AccountDialog,
    DateField,
    DebtDialog,
    FixedExpenseDialog,
    FixedIncomeDialog,
    MainWindow,
    OnboardingWindow,
    ThemeToggle,
    TransactionDialog,
)
from summit.widgets import MoneyField


class UiSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_onboarding_and_dashboard_can_be_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Database(Path(temp_dir) / "summit.db")
            onboarding = OnboardingWindow(database)
            onboarding._start_demo()
            self.assertTrue(database.is_configured())

            dashboard = MainWindow(database)
            self.assertEqual(dashboard.pages.count(), 9)
            self.assertEqual(dashboard.windowTitle(), "Summit · Visão financeira")
            dashboard._show_page(1)
            movement_page = dashboard.pages.currentWidget()
            self.assertIsNotNone(movement_page.findChild(QWidget, "MovementBoard"))
            columns = [
                child for child in movement_page.findChildren(QFrame)
                if child.objectName() == "MovementColumn"
            ]
            self.assertEqual(len(columns), 3)
            self.assertIsNone(movement_page.findChild(QTabWidget))
            dashboard._show_page(2)
            fixed_page = dashboard.pages.currentWidget()
            self.assertIsNotNone(fixed_page.findChild(QWidget, "FixedBoard"))
            self.assertEqual(len([
                child for child in fixed_page.findChildren(QFrame)
                if child.objectName() == "MovementColumn"
            ]), 2)

            transaction = database.transactions()[0]
            transaction_dialog = TransactionDialog(database, transaction=transaction)
            self.assertIn(
                "Excluir lançamento",
                [button.text() for button in transaction_dialog.findChildren(QPushButton)],
            )
            fixed_dialog = FixedExpenseDialog(database, expense=database.fixed_expenses()[0])
            self.assertIn(
                "Excluir conta fixa",
                [button.text() for button in fixed_dialog.findChildren(QPushButton)],
            )
            personal_fixed_dialog = FixedExpenseDialog(database, default_scope="personal")
            self.assertEqual(personal_fixed_dialog.scope.currentData(), "personal")
            fixed_income_dialog = FixedIncomeDialog(database, income=database.fixed_incomes()[0])
            self.assertIn(
                "Excluir entrada fixa",
                [button.text() for button in fixed_income_dialog.findChildren(QPushButton)],
            )
            account_dialog = AccountDialog(database, account=database.accounts()[0])
            self.assertEqual(account_dialog.initial_balance.value(), 12480)
            debt_dialog = DebtDialog(database, debt=database.debts()[0])
            self.assertIn(
                "Marcar como quitada",
                [button.text() for button in debt_dialog.findChildren(QPushButton)],
            )
            dashboard._show_page(4)
            self.assertIsNotNone(dashboard.pages.currentWidget().findChild(QWidget, "DebtsTable"))
            dashboard._show_page(7)
            self.assertGreaterEqual(len(dashboard.pages.currentWidget().findChildren(DateField)), 2)
            dashboard._show_page(0)
            dashboard._change_dashboard_period("annual")
            self.assertEqual(dashboard.dashboard_period, "annual")
            dashboard.privacy_button.click()
            self.assertTrue(dashboard.privacy_button.isChecked())

            # Verificar botão de tema no cabeçalho
            self.assertIsNotNone(dashboard.theme_toggle)
            dashboard.theme_toggle.switch.click()
            self.assertEqual(dashboard.theme_toggle.mode(), "light")
            self.assertEqual(database.settings()["theme_mode"], "light")

            # Verificar se os cards de métricas estão em primeiro lugar no layout do Dashboard
            dash_scroll = dashboard.pages.widget(0)
            dash_page = dash_scroll.findChild(QWidget, "PeriodSwitch").parentWidget()
            self.assertIsInstance(dash_page.layout().itemAt(0), QGridLayout)

            # Verificar se a tela de Configurações possui o ThemeToggle sincronizado
            dashboard._show_page(8)
            settings_toggle = dashboard.pages.currentWidget().findChild(ThemeToggle)
            self.assertIsNotNone(settings_toggle)
            self.assertEqual(settings_toggle.mode(), "light")

            dashboard.close()

    def test_theme_toggle_widget(self) -> None:
        toggle = ThemeToggle("dark")
        self.assertEqual(toggle.mode(), "dark")
        self.assertFalse(toggle.switch.isChecked())

        received: list[str] = []
        toggle.themeChanged.connect(received.append)

        # Clicar no interruptor para modo claro
        toggle.switch.click()
        self.assertEqual(toggle.mode(), "light")
        self.assertTrue(toggle.switch.isChecked())
        self.assertEqual(received, ["light"])

        # Clicar na lua para modo escuro
        QTest.mouseClick(toggle.moon_label, Qt.MouseButton.LeftButton)
        self.assertEqual(toggle.mode(), "dark")
        self.assertFalse(toggle.switch.isChecked())
        self.assertEqual(received, ["light", "dark"])

        # Clicar no sol para modo claro
        QTest.mouseClick(toggle.sun_label, Qt.MouseButton.LeftButton)
        self.assertEqual(toggle.mode(), "light")
        self.assertTrue(toggle.switch.isChecked())
        self.assertEqual(received, ["light", "dark", "light"])

    def test_lock_window_unlocks_only_with_correct_pin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Database(Path(temp_dir) / "summit.db")
            database.set_pin("1234")
            lock = LockWindow(database)

            unlocked: list[bool] = []
            lock.unlocked.connect(lambda: unlocked.append(True))

            # PIN errado: não deve desbloquear e deve mostrar mensagem de erro.
            for digit in "0000":
                lock._add_digit(digit)
            self.assertEqual(unlocked, [])
            self.assertNotEqual(lock.error_label.text(), "")
            self.assertEqual(lock.entered, "")

            # PIN correto: deve emitir o sinal de desbloqueio.
            for digit in "1234":
                lock._add_digit(digit)
            self.assertEqual(unlocked, [True])
            lock.close()

    def test_pin_dialog_creates_and_changes_pin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Database(Path(temp_dir) / "summit.db")

            create_dialog = PinDialog(database)
            self.assertIsNone(create_dialog.current_field)
            create_dialog.new_field.setText("1234")
            create_dialog.confirm_field.setText("1234")
            create_dialog._save()
            self.assertTrue(database.is_pin_enabled())
            self.assertTrue(database.verify_pin("1234"))

            change_dialog = PinDialog(database)
            self.assertIsNotNone(change_dialog.current_field)
            change_dialog.current_field.setText("1234")
            change_dialog.new_field.setText("5678")
            change_dialog.confirm_field.setText("5678")
            change_dialog._save()
            self.assertTrue(database.verify_pin("5678"))
            self.assertFalse(database.verify_pin("1234"))

    def test_settings_page_exposes_security_panel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Database(Path(temp_dir) / "summit.db")
            onboarding = OnboardingWindow(database)
            onboarding._start_demo()
            dashboard = MainWindow(database)
            dashboard._show_page(8)
            settings_page = dashboard.pages.currentWidget()
            button_labels = [button.text() for button in settings_page.findChildren(QPushButton)]
            self.assertIn("Ativar PIN", button_labels)
            dashboard.close()

    def test_money_field_replaces_selected_value(self) -> None:
        field = MoneyField()
        field.setRange(0, 999_999)
        field.setDecimals(2)
        field.setPrefix("R$ ")
        field.setValue(1000)
        field.show()
        field.setFocus()
        field.selectAll()
        QTest.keyClicks(field, "6")
        QTest.keyClick(field, Qt.Key.Key_Enter)
        self.assertEqual(field.value(), 6)
        field.close()


if __name__ == "__main__":
    unittest.main()
