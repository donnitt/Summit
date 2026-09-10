from __future__ import annotations

import tempfile
import unittest
import sqlite3
from datetime import date
from pathlib import Path

from summit.database import Database
from summit.finance import brl, calculate, set_values_hidden


class DatabaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "summit.db")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_workspace_and_transaction_are_persisted(self) -> None:
        self.database.setup_workspace("Doni", "Tatuador", "Conta principal", 1000)
        self.database.add_transaction(
            "Sessão", "Serviços", 500, "income", "paid", "2026-09-09", 1
        )
        self.assertTrue(self.database.is_configured())
        self.assertEqual(self.database.workspace()["manager"], "Doni")
        self.assertEqual(len(self.database.transactions()), 1)

        stats = calculate(self.database.snapshot(), today=date(2026, 9, 10))
        self.assertEqual(stats["balance"], 1500)
        self.assertEqual(stats["income"], 500)

    def test_demo_populates_dashboard_sections(self) -> None:
        self.database.setup_workspace("Alex", "Estúdio", "Conta", 0, demo=True)
        snapshot = self.database.snapshot()
        self.assertGreater(len(snapshot["transactions"]), 10)
        self.assertEqual(len(snapshot["fixed_expenses"]), 3)
        self.assertEqual(len(snapshot["fixed_incomes"]), 1)
        self.assertEqual(len(snapshot["debts"]), 2)
        self.assertEqual(len(snapshot["goals"]), 2)
        self.assertEqual(len(snapshot["budgets"]), 3)
        self.assertEqual(len(snapshot["investments"]), 2)

    def test_transaction_can_be_edited_and_deleted(self) -> None:
        self.database.setup_workspace("Doni", "Casa", "Conta", 0)
        self.database.add_transaction(
            "Mercado", "Casa", 100, "expense", "paid", "2026-09-09", 1, scope="personal"
        )
        transaction = self.database.transactions()[0]
        self.database.update_transaction(
            transaction["id"], "Mercado do mês", "Alimentação", 150,
            "expense", "pending", "2026-09-10", 1, notes="Compra planejada", scope="personal",
        )
        updated = self.database.transactions()[0]
        self.assertEqual(updated["description"], "Mercado do mês")
        self.assertEqual(updated["amount"], 150)
        self.assertEqual(updated["status"], "pending")
        self.assertEqual(updated["notes"], "Compra planejada")
        self.assertEqual(updated["scope"], "personal")
        self.database.delete_transaction(updated["id"])
        self.assertEqual(self.database.transactions(), [])

    def test_planning_and_investment_crud(self) -> None:
        self.database.setup_workspace("Doni", "Autônomo", "Conta", 0)
        self.database.add_fixed_expense(
            "Internet", "Contas", 120, 12, 1, notes="Plano mensal", scope="personal"
        )
        fixed = self.database.fixed_expenses()[0]
        self.database.update_fixed_expense(
            fixed["id"], "Internet fibra", "Contas", 130, 15, 1, False, scope="personal"
        )
        self.assertFalse(self.database.fixed_expenses()[0]["active"])
        self.assertEqual(self.database.fixed_expenses()[0]["scope"], "personal")

        self.database.add_fixed_income(
            "Contrato", "Serviços", 2200, 5, 1, notes="Mensal", scope="work"
        )
        fixed_income = self.database.fixed_incomes()[0]
        self.database.update_fixed_income(
            fixed_income["id"], "Contrato recorrente", "Serviços", 2400, 8, 1,
            False, notes="Pausado", scope="work",
        )
        self.assertEqual(self.database.fixed_incomes()[0]["amount"], 2400)
        self.assertFalse(self.database.fixed_incomes()[0]["active"])

        self.database.add_goal("Reserva", 500, 5000, "2027-09-09", 400, "Emergências")
        goal = self.database.goals()[0]
        self.database.update_goal(goal["id"], "Reserva maior", 700, 6000, "2027-10-09", 450)
        self.assertEqual(self.database.goals()[0]["target_amount"], 6000)

        self.database.add_budget("Alimentação", 900, "Teto mensal")
        budget = self.database.budgets()[0]
        self.database.update_budget(budget["id"], "Alimentação", 1000)
        self.assertEqual(self.database.budgets()[0]["monthly_limit"], 1000)

        self.database.add_investment(
            "Tesouro", "Renda fixa", 1000, 1050, "Corretora", 1, 1000,
            "Longo prazo", "2026-09-09",
        )
        investment = self.database.investments()[0]
        self.database.update_investment(
            investment["id"], "Tesouro Selic", "Renda fixa", 1100, 1175,
            "Corretora", 1.1, 1000, "Atualizado", "2026-10-09",
        )
        self.assertEqual(self.database.investments()[0]["current_value"], 1175)

        self.database.delete_fixed_expense(fixed["id"])
        self.database.delete_fixed_income(fixed_income["id"])
        self.database.delete_goal(goal["id"])
        self.database.delete_budget(budget["id"])
        self.database.delete_investment(investment["id"])
        self.assertEqual(self.database.fixed_expenses(), [])
        self.assertEqual(self.database.fixed_incomes(), [])
        self.assertEqual(self.database.goals(), [])
        self.assertEqual(self.database.budgets(), [])
        self.assertEqual(self.database.investments(), [])

    def test_accounts_debts_and_receipt_confirmation(self) -> None:
        self.database.setup_workspace("Doni", "Autônomo", "Conta", 500)
        self.database.update_account(1, "Conta profissional", "Conta digital", 750)
        self.database.add_account("Carteira", "Dinheiro", -20)
        accounts = self.database.accounts()
        self.assertEqual(accounts[0]["initial_balance"], 750)
        self.assertEqual(accounts[1]["initial_balance"], -20)

        self.database.add_debt(
            "Notebook", "Loja", "Equipamentos", 3000, 2000, "2026-10-10",
            10, 3, "work", "Uso no estúdio",
        )
        debt = self.database.debts()[0]
        self.database.update_debt(
            debt["id"], "Notebook novo", "Loja", "Equipamentos", 3000, 1500,
            "2026-11-10", 10, 5, "work", "Parcela atualizada",
        )
        updated_debt = self.database.debts()[0]
        self.assertEqual(updated_debt["outstanding_amount"], 1500)
        self.assertEqual(updated_debt["status"], "open")

        self.database.add_transaction(
            "Cliente", "Serviços", 800, "income", "pending", "2026-09-09", 1
        )
        receivable = self.database.transactions()[0]
        self.database.confirm_income_received(receivable["id"], "2026-09-12")
        received = self.database.transactions()[0]
        self.assertEqual(received["status"], "paid")
        self.assertEqual(received["transaction_date"], "2026-09-12")
        with self.assertRaisesRegex(ValueError, "aguardando recebimento"):
            self.database.confirm_income_received(receivable["id"], "2026-09-13")

        self.database.delete_debt(updated_debt["id"])
        self.assertEqual(self.database.debts(), [])

    def test_brl_format(self) -> None:
        set_values_hidden(False)
        self.assertEqual(brl(1234.5), "R$ 1.234,50")
        self.assertEqual(brl(-12.5), "− R$ 12,50")
        set_values_hidden(True)
        self.assertEqual(brl(1234.5), "R$ ••••••")
        set_values_hidden(False)

    def test_dashboard_periods_filter_and_group_transactions(self) -> None:
        self.database.setup_workspace("Doni", "Autônomo", "Conta", 0)
        for description, amount, kind, transaction_date in (
            ("Entrada semana", 500, "income", "2026-09-09"),
            ("Gasto semana", 100, "expense", "2026-09-08"),
            ("Entrada mês", 700, "income", "2026-09-01"),
            ("Entrada ano", 900, "income", "2026-02-01"),
        ):
            self.database.add_transaction(
                description, "Teste", amount, kind, "paid", transaction_date, 1
            )
        snapshot = self.database.snapshot()
        weekly = calculate(snapshot, today=date(2026, 9, 9), period="weekly")
        monthly = calculate(snapshot, today=date(2026, 9, 9), period="monthly")
        annual = calculate(snapshot, today=date(2026, 9, 9), period="annual")
        self.assertEqual(weekly["income"], 500)
        self.assertEqual(monthly["income"], 1200)
        self.assertEqual(annual["income"], 2100)
        self.assertEqual(len(weekly["cash_flow"]), 7)
        self.assertEqual(len(annual["cash_flow"]), 12)

    def test_existing_database_is_migrated_without_losing_data(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        connection = sqlite3.connect(legacy_path)
        connection.executescript(
            """
            CREATE TABLE workspace (id INTEGER PRIMARY KEY, manager TEXT NOT NULL, business TEXT NOT NULL, created_at TEXT);
            CREATE TABLE accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, account_type TEXT, initial_balance REAL, color TEXT);
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, description TEXT NOT NULL, category TEXT NOT NULL,
                amount REAL NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL, transaction_date TEXT NOT NULL,
                account_id INTEGER, recurring INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, current_amount REAL NOT NULL,
                target_amount REAL NOT NULL, deadline TEXT, color TEXT
            );
            CREATE TABLE investments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, investment_type TEXT NOT NULL,
                invested REAL NOT NULL, current_value REAL NOT NULL
            );
            INSERT INTO workspace VALUES (1, 'Doni', 'Tatuador', CURRENT_TIMESTAMP);
            INSERT INTO accounts VALUES (1, 'Conta', 'Conta corrente', 500, '#8f70ff');
            INSERT INTO transactions VALUES (1, 'Sessão antiga', 'Serviços', 300, 'income', 'paid', '2026-09-01', 1, 0);
            INSERT INTO investments VALUES (1, 'Tesouro antigo', 'Renda fixa', 100, 105);
            """
        )
        connection.commit()
        connection.close()

        migrated = Database(legacy_path)
        self.assertEqual(migrated.transactions()[0]["description"], "Sessão antiga")
        self.assertEqual(migrated.transactions()[0]["notes"], "")
        self.assertEqual(migrated.transactions()[0]["scope"], "work")
        self.assertEqual(migrated.investments()[0]["institution"], "")
        migrated.add_fixed_expense("Internet", "Contas", 100, 10, 1)
        self.assertEqual(len(migrated.fixed_expenses()), 1)
        self.assertEqual(migrated.debts(), [])


if __name__ == "__main__":
    unittest.main()
