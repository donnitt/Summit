from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QPushButton, QTabWidget, QWidget

from summit.database import Database
from summit.ui import (
    AccountDialog,
    DateField,
    DebtDialog,
    FixedExpenseDialog,
    FixedIncomeDialog,
    MainWindow,
    MoneyField,
    OnboardingWindow,
    TransactionDialog,
)


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
            self.assertEqual(dashboard.pages.count(), 10)
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
            dashboard._show_page(8)
            self.assertGreaterEqual(len(dashboard.pages.currentWidget().findChildren(DateField)), 2)
            dashboard._show_page(0)
            dashboard._change_dashboard_period("annual")
            self.assertEqual(dashboard.dashboard_period, "annual")
            dashboard.privacy_button.click()
            self.assertTrue(dashboard.privacy_button.isChecked())
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
