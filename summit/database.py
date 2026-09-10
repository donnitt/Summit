from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator


def default_database_path() -> Path:
    """Return a writable, user-specific database location."""
    override = os.environ.get("SUMMIT_DATA_DIR")
    if override:
        data_dir = Path(override).expanduser()
    elif os.name == "nt":
        data_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Summit"
    else:
        data_dir = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "Summit"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "summit.db"


class Database:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else default_database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS workspace (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    manager TEXT NOT NULL,
                    business TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS app_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    theme_mode TEXT NOT NULL DEFAULT 'dark' CHECK (theme_mode IN ('dark', 'light')),
                    accent_color TEXT NOT NULL DEFAULT '#8562ef'
                );
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    account_type TEXT NOT NULL DEFAULT 'Conta corrente',
                    initial_balance REAL NOT NULL DEFAULT 0,
                    color TEXT NOT NULL DEFAULT '#8f70ff'
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount REAL NOT NULL CHECK (amount > 0),
                    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
                    status TEXT NOT NULL DEFAULT 'paid' CHECK (status IN ('paid', 'pending')),
                    transaction_date TEXT NOT NULL,
                    account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
                    recurring INTEGER NOT NULL DEFAULT 0 CHECK (recurring IN (0, 1)),
                    notes TEXT NOT NULL DEFAULT '',
                    scope TEXT NOT NULL DEFAULT 'work' CHECK (scope IN ('personal', 'work'))
                );
                CREATE TABLE IF NOT EXISTS fixed_expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount REAL NOT NULL CHECK (amount > 0),
                    due_day INTEGER NOT NULL CHECK (due_day BETWEEN 1 AND 31),
                    account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
                    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                    notes TEXT NOT NULL DEFAULT '',
                    scope TEXT NOT NULL DEFAULT 'work' CHECK (scope IN ('personal', 'work'))
                );
                CREATE TABLE IF NOT EXISTS fixed_incomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount REAL NOT NULL CHECK (amount > 0),
                    due_day INTEGER NOT NULL CHECK (due_day BETWEEN 1 AND 31),
                    account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
                    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                    notes TEXT NOT NULL DEFAULT '',
                    scope TEXT NOT NULL DEFAULT 'work' CHECK (scope IN ('personal', 'work'))
                );
                CREATE TABLE IF NOT EXISTS debts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL,
                    creditor TEXT NOT NULL,
                    category TEXT NOT NULL,
                    total_amount REAL NOT NULL CHECK (total_amount > 0),
                    outstanding_amount REAL NOT NULL CHECK (outstanding_amount >= 0),
                    due_date TEXT NOT NULL,
                    installments_total INTEGER NOT NULL DEFAULT 1 CHECK (installments_total > 0),
                    installments_paid INTEGER NOT NULL DEFAULT 0 CHECK (installments_paid >= 0),
                    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'paid')),
                    scope TEXT NOT NULL DEFAULT 'personal' CHECK (scope IN ('personal', 'work')),
                    notes TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    current_amount REAL NOT NULL DEFAULT 0 CHECK (current_amount >= 0),
                    target_amount REAL NOT NULL CHECK (target_amount > 0),
                    deadline TEXT,
                    color TEXT NOT NULL DEFAULT '#a78bfa',
                    monthly_contribution REAL NOT NULL DEFAULT 0 CHECK (monthly_contribution >= 0),
                    notes TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS budgets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    monthly_limit REAL NOT NULL CHECK (monthly_limit > 0),
                    notes TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS investments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    investment_type TEXT NOT NULL,
                    invested REAL NOT NULL CHECK (invested >= 0),
                    current_value REAL NOT NULL CHECK (current_value >= 0),
                    institution TEXT NOT NULL DEFAULT '',
                    quantity REAL NOT NULL DEFAULT 0 CHECK (quantity >= 0),
                    average_price REAL NOT NULL DEFAULT 0 CHECK (average_price >= 0),
                    notes TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date);
                CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status, kind);
                CREATE INDEX IF NOT EXISTS idx_fixed_expenses_active ON fixed_expenses(active, due_day);
                CREATE INDEX IF NOT EXISTS idx_fixed_incomes_active ON fixed_incomes(active, due_day);
                CREATE INDEX IF NOT EXISTS idx_debts_status_due ON debts(status, due_date);
                """
            )
            # Migra bancos criados por versões anteriores sem apagar dados.
            self._ensure_column(connection, "transactions", "notes", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "transactions", "scope", "TEXT NOT NULL DEFAULT 'work'")
            self._ensure_column(connection, "fixed_expenses", "scope", "TEXT NOT NULL DEFAULT 'work'")
            self._ensure_column(connection, "goals", "monthly_contribution", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(connection, "goals", "notes", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "investments", "institution", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "investments", "quantity", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(connection, "investments", "average_price", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(connection, "investments", "notes", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "investments", "updated_at", "TEXT NOT NULL DEFAULT ''")
            if connection.execute("SELECT 1 FROM app_settings WHERE id = 1").fetchone() is None:
                connection.execute(
                    "INSERT INTO app_settings (id, theme_mode, accent_color) VALUES (1, 'dark', '#8562ef')"
                )

    @staticmethod
    def _required_text(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError(f"Preencha o campo {field}.")
        return cleaned

    @staticmethod
    def _iso_date(value: str, field: str, optional: bool = False) -> str | None:
        cleaned = value.strip()
        if optional and not cleaned:
            return None
        try:
            return date.fromisoformat(cleaned).isoformat()
        except ValueError as error:
            raise ValueError(f"Informe uma data válida em {field}.") from error

    @staticmethod
    def _positive(value: float, field: str, allow_zero: bool = False) -> float:
        number = float(value)
        if number < 0 or (not allow_zero and number == 0):
            suffix = "zero ou maior" if allow_zero else "maior que zero"
            raise ValueError(f"O campo {field} deve ser {suffix}.")
        return number

    @staticmethod
    def _ensure_updated(cursor: sqlite3.Cursor, message: str) -> None:
        if cursor.rowcount == 0:
            raise ValueError(message)

    def is_configured(self) -> bool:
        with self.connect() as connection:
            return connection.execute("SELECT 1 FROM workspace WHERE id = 1").fetchone() is not None

    def setup_workspace(
        self,
        manager: str,
        business: str,
        account_name: str,
        initial_balance: float,
        demo: bool = False,
    ) -> None:
        values = (
            self._required_text(manager, "nome"),
            self._required_text(business, "atividade"),
            self._required_text(account_name, "conta"),
        )
        with self.connect() as connection:
            if connection.execute("SELECT 1 FROM workspace WHERE id = 1").fetchone():
                raise ValueError("Este espaço já foi configurado.")
            connection.execute("INSERT INTO workspace (id, manager, business) VALUES (1, ?, ?)", values[:2])
            cursor = connection.execute(
                "INSERT INTO accounts (name, initial_balance) VALUES (?, ?)",
                (values[2], float(initial_balance)),
            )
            if demo:
                self._seed_demo(connection, int(cursor.lastrowid))

    def _seed_demo(self, connection: sqlite3.Connection, account_id: int) -> None:
        today = date.today()

        def month_date(offset: int, day: int) -> str:
            total_month = today.year * 12 + today.month - 1 + offset
            year, month_index = divmod(total_month, 12)
            return date(year, month_index + 1, min(day, 28)).isoformat()

        rows = [
            ("Sessão — fechamento floral", "Serviços", 1850, "income", "paid", (today - timedelta(days=1)).isoformat(), 0),
            ("Sessão — fine line", "Serviços", 920, "income", "paid", (today - timedelta(days=4)).isoformat(), 0),
            ("Aluguel do estúdio", "Espaço", 1600, "expense", "paid", month_date(0, 5), 1),
            ("Materiais e descartáveis", "Materiais", 486.40, "expense", "paid", (today - timedelta(days=3)).isoformat(), 0),
            ("Anúncios Instagram", "Marketing", 320, "expense", "paid", (today - timedelta(days=6)).isoformat(), 1),
            ("Energia e internet", "Contas", 284.90, "expense", "paid", (today - timedelta(days=8)).isoformat(), 1),
            ("Sessão — braço fechado", "Serviços", 2400, "income", "pending", (today + timedelta(days=4)).isoformat(), 0),
            ("Sinal — projeto autoral", "Serviços", 780, "income", "pending", (today + timedelta(days=9)).isoformat(), 0),
            ("Fornecedor de tintas", "Materiais", 640, "expense", "pending", (today + timedelta(days=6)).isoformat(), 0),
            ("Workshop lettering", "Educação", 450, "expense", "pending", (today + timedelta(days=14)).isoformat(), 0),
        ]
        connection.executemany(
            """
            INSERT INTO transactions
                (description, category, amount, kind, status, transaction_date, account_id, recurring)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [row[:6] + (account_id, row[6]) for row in rows],
        )
        history = [(-5, 5800, 3820), (-4, 6450, 4010), (-3, 6180, 3740), (-2, 7200, 4320), (-1, 7640, 4410)]
        for offset, income, expense in history:
            connection.execute(
                "INSERT INTO transactions (description, category, amount, kind, status, transaction_date, account_id) VALUES (?, ?, ?, 'income', 'paid', ?, ?)",
                ("Receitas do mês", "Serviços", income, month_date(offset, 15), account_id),
            )
            connection.execute(
                "INSERT INTO transactions (description, category, amount, kind, status, transaction_date, account_id) VALUES (?, ?, ?, 'expense', 'paid', ?, ?)",
                ("Custos do mês", "Operação", expense, month_date(offset, 20), account_id),
            )
        connection.executemany(
            "INSERT INTO fixed_expenses (description, category, amount, due_day, account_id, notes, scope) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("Aluguel do estúdio", "Espaço", 1600, 5, account_id, "Contrato do estúdio", "work"),
                ("Internet de casa", "Contas", 129.90, 10, account_id, "Plano residencial", "personal"),
                ("Anúncios Instagram", "Marketing", 320, 15, account_id, "Verba recorrente", "work"),
            ],
        )
        connection.execute(
            "INSERT INTO fixed_incomes (description, category, amount, due_day, account_id, notes, scope) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("Contrato mensal de criação", "Contratos", 2800, 8, account_id, "Receita recorrente", "work"),
        )
        connection.executemany(
            """
            INSERT INTO debts
                (description, creditor, category, total_amount, outstanding_amount, due_date,
                 installments_total, installments_paid, scope, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("Notebook do estúdio", "Loja de equipamentos", "Equipamentos", 4800, 3200,
                 month_date(1, 12), 12, 4, "work", "Parcela mensal de R$ 400"),
                ("Curso de especialização", "Escola de arte", "Educação", 1800, 900,
                 month_date(0, 25), 6, 3, "personal", "Aprimoramento profissional"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO goals
                (name, current_amount, target_amount, deadline, color, monthly_contribution, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("Nova maca elétrica", 4800, 8000, month_date(3, 28), "#9b7cff", 800, "Equipamento prioritário"),
                ("Reserva de segurança", 12600, 20000, month_date(8, 28), "#47d7b2", 925, "Seis meses de custos"),
            ],
        )
        connection.executemany(
            "INSERT INTO budgets (category, monthly_limit, notes) VALUES (?, ?, ?)",
            [
                ("Materiais", 1200, "Tintas e descartáveis"),
                ("Marketing", 600, "Anúncios e conteúdo"),
                ("Educação", 500, "Cursos e eventos"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO investments
                (name, investment_type, invested, current_value, institution, quantity, average_price, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("Tesouro Selic 2029", "Renda fixa", 8500, 8974.20, "Tesouro Direto", 1, 8500, "Reserva de médio prazo", today.isoformat()),
                ("ETF BOVA11", "Renda variável", 3200, 3468.70, "Corretora", 28, 114.29, "Exposição à bolsa brasileira", today.isoformat()),
            ],
        )

    def workspace(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM workspace WHERE id = 1").fetchone()
            return dict(row) if row else None

    def update_workspace(self, manager: str, business: str) -> None:
        values = (
            self._required_text(manager, "nome"),
            self._required_text(business, "atividade"),
        )
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE workspace SET manager = ?, business = ? WHERE id = 1", values
            )
            self._ensure_updated(cursor, "Espaço ainda não configurado.")

    def settings(self) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM app_settings WHERE id = 1").fetchone()
            if row:
                return dict(row)
            return {"id": 1, "theme_mode": "dark", "accent_color": "#8562ef"}

    def update_settings(self, theme_mode: str, accent_color: str) -> None:
        if theme_mode not in {"dark", "light"}:
            raise ValueError("Tema inválido.")
        color = accent_color.strip()
        if not color.startswith("#") or len(color) not in (4, 7):
            raise ValueError("Cor de destaque inválida.")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO app_settings (id, theme_mode, accent_color) VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET theme_mode = excluded.theme_mode, accent_color = excluded.accent_color
                """,
                (theme_mode, color),
            )

    def backup_to(self, destination: str | Path) -> Path:
        """Copy the current database file to the given path and return it."""
        import shutil

        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.connect():
            pass  # ensure any pending WAL data is flushed before copying
        shutil.copy2(self.path, target)
        return target

    def accounts(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM accounts ORDER BY id")]

    def add_account(self, name: str, account_type: str, initial_balance: float) -> None:
        values = self._account_values(name, account_type, initial_balance)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO accounts (name, account_type, initial_balance) VALUES (?, ?, ?)",
                values,
            )

    def update_account(self, account_id: int, name: str, account_type: str, initial_balance: float) -> None:
        values = self._account_values(name, account_type, initial_balance)
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE accounts SET name = ?, account_type = ?, initial_balance = ? WHERE id = ?",
                values + (int(account_id),),
            )
            self._ensure_updated(cursor, "Conta não encontrada.")

    def _account_values(self, name: str, account_type: str, initial_balance: float) -> tuple[Any, ...]:
        return (
            self._required_text(name, "nome da conta"),
            self._required_text(account_type, "tipo da conta"),
            float(initial_balance),
        )

    def transactions(self, limit: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM transactions ORDER BY transaction_date DESC, id DESC"
        parameters: tuple[Any, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            parameters = (limit,)
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query, parameters)]

    def fixed_expenses(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM fixed_expenses ORDER BY active DESC, due_day, description"
            )]

    def fixed_incomes(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM fixed_incomes ORDER BY active DESC, due_day, description"
            )]

    def debts(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM debts ORDER BY status, due_date, id"
            )]

    def goals(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM goals ORDER BY deadline IS NULL, deadline, id"
            )]

    def budgets(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM budgets ORDER BY category COLLATE NOCASE"
            )]

    def investments(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM investments ORDER BY name COLLATE NOCASE"
            )]

    def add_transaction(
        self,
        description: str,
        category: str,
        amount: float,
        kind: str,
        status: str,
        transaction_date: str,
        account_id: int | None,
        recurring: bool = False,
        notes: str = "",
        scope: str = "work",
    ) -> None:
        values = self._transaction_values(
            description, category, amount, kind, status, transaction_date, account_id, recurring, notes, scope
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO transactions
                    (description, category, amount, kind, status, transaction_date, account_id, recurring, notes, scope)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )

    def update_transaction(
        self,
        transaction_id: int,
        description: str,
        category: str,
        amount: float,
        kind: str,
        status: str,
        transaction_date: str,
        account_id: int | None,
        recurring: bool = False,
        notes: str = "",
        scope: str = "work",
    ) -> None:
        values = self._transaction_values(
            description, category, amount, kind, status, transaction_date, account_id, recurring, notes, scope
        )
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE transactions
                SET description = ?, category = ?, amount = ?, kind = ?, status = ?,
                    transaction_date = ?, account_id = ?, recurring = ?, notes = ?, scope = ?
                WHERE id = ?
                """,
                values + (int(transaction_id),),
            )
            self._ensure_updated(cursor, "Lançamento não encontrado.")

    def _transaction_values(
        self,
        description: str,
        category: str,
        amount: float,
        kind: str,
        status: str,
        transaction_date: str,
        account_id: int | None,
        recurring: bool,
        notes: str,
        scope: str,
    ) -> tuple[Any, ...]:
        if kind not in {"income", "expense"} or status not in {"paid", "pending"}:
            raise ValueError("Tipo ou situação inválida.")
        if scope not in {"personal", "work"}:
            raise ValueError("Uso pessoal ou de trabalho inválido.")
        return (
            self._required_text(description, "descrição"),
            self._required_text(category, "categoria"),
            self._positive(amount, "valor"),
            kind,
            status,
            self._iso_date(transaction_date, "data"),
            account_id,
            int(recurring),
            notes.strip(),
            scope,
        )

    def delete_transaction(self, transaction_id: int) -> None:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM transactions WHERE id = ?", (int(transaction_id),))
            self._ensure_updated(cursor, "Lançamento não encontrado.")

    def add_fixed_expense(
        self,
        description: str,
        category: str,
        amount: float,
        due_day: int,
        account_id: int | None,
        active: bool = True,
        notes: str = "",
        scope: str = "work",
    ) -> None:
        values = self._fixed_expense_values(description, category, amount, due_day, account_id, active, notes, scope)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO fixed_expenses (description, category, amount, due_day, account_id, active, notes, scope) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )

    def update_fixed_expense(
        self,
        expense_id: int,
        description: str,
        category: str,
        amount: float,
        due_day: int,
        account_id: int | None,
        active: bool = True,
        notes: str = "",
        scope: str = "work",
    ) -> None:
        values = self._fixed_expense_values(description, category, amount, due_day, account_id, active, notes, scope)
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE fixed_expenses
                SET description = ?, category = ?, amount = ?, due_day = ?, account_id = ?, active = ?, notes = ?, scope = ?
                WHERE id = ?
                """,
                values + (int(expense_id),),
            )
            self._ensure_updated(cursor, "Conta fixa não encontrada.")

    def _fixed_expense_values(
        self,
        description: str,
        category: str,
        amount: float,
        due_day: int,
        account_id: int | None,
        active: bool,
        notes: str,
        scope: str,
    ) -> tuple[Any, ...]:
        day = int(due_day)
        if not 1 <= day <= 31:
            raise ValueError("O vencimento deve estar entre os dias 1 e 31.")
        if scope not in {"personal", "work"}:
            raise ValueError("Uso pessoal ou de trabalho inválido.")
        return (
            self._required_text(description, "descrição"),
            self._required_text(category, "categoria"),
            self._positive(amount, "valor"),
            day,
            account_id,
            int(active),
            notes.strip(),
            scope,
        )

    def delete_fixed_expense(self, expense_id: int) -> None:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM fixed_expenses WHERE id = ?", (int(expense_id),))
            self._ensure_updated(cursor, "Conta fixa não encontrada.")

    def add_fixed_income(
        self,
        description: str,
        category: str,
        amount: float,
        due_day: int,
        account_id: int | None,
        active: bool = True,
        notes: str = "",
        scope: str = "work",
    ) -> None:
        values = self._fixed_expense_values(description, category, amount, due_day, account_id, active, notes, scope)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO fixed_incomes (description, category, amount, due_day, account_id, active, notes, scope) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )

    def update_fixed_income(
        self,
        income_id: int,
        description: str,
        category: str,
        amount: float,
        due_day: int,
        account_id: int | None,
        active: bool = True,
        notes: str = "",
        scope: str = "work",
    ) -> None:
        values = self._fixed_expense_values(description, category, amount, due_day, account_id, active, notes, scope)
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE fixed_incomes
                SET description = ?, category = ?, amount = ?, due_day = ?, account_id = ?, active = ?, notes = ?, scope = ?
                WHERE id = ?
                """,
                values + (int(income_id),),
            )
            self._ensure_updated(cursor, "Entrada fixa não encontrada.")

    def delete_fixed_income(self, income_id: int) -> None:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM fixed_incomes WHERE id = ?", (int(income_id),))
            self._ensure_updated(cursor, "Entrada fixa não encontrada.")

    def add_debt(
        self,
        description: str,
        creditor: str,
        category: str,
        total_amount: float,
        outstanding_amount: float,
        due_date: str,
        installments_total: int = 1,
        installments_paid: int = 0,
        scope: str = "personal",
        notes: str = "",
    ) -> None:
        values = self._debt_values(
            description, creditor, category, total_amount, outstanding_amount, due_date,
            installments_total, installments_paid, scope, notes,
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO debts
                    (description, creditor, category, total_amount, outstanding_amount, due_date,
                     installments_total, installments_paid, status, scope, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )

    def update_debt(
        self,
        debt_id: int,
        description: str,
        creditor: str,
        category: str,
        total_amount: float,
        outstanding_amount: float,
        due_date: str,
        installments_total: int = 1,
        installments_paid: int = 0,
        scope: str = "personal",
        notes: str = "",
    ) -> None:
        values = self._debt_values(
            description, creditor, category, total_amount, outstanding_amount, due_date,
            installments_total, installments_paid, scope, notes,
        )
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE debts
                SET description = ?, creditor = ?, category = ?, total_amount = ?,
                    outstanding_amount = ?, due_date = ?, installments_total = ?,
                    installments_paid = ?, status = ?, scope = ?, notes = ?
                WHERE id = ?
                """,
                values + (int(debt_id),),
            )
            self._ensure_updated(cursor, "Dívida não encontrada.")

    def _debt_values(
        self,
        description: str,
        creditor: str,
        category: str,
        total_amount: float,
        outstanding_amount: float,
        due_date: str,
        installments_total: int,
        installments_paid: int,
        scope: str,
        notes: str,
    ) -> tuple[Any, ...]:
        total = self._positive(total_amount, "valor total")
        outstanding = self._positive(outstanding_amount, "saldo devedor", allow_zero=True)
        installments = int(installments_total)
        paid = int(installments_paid)
        if outstanding > total:
            raise ValueError("O saldo devedor não pode ser maior que o valor total.")
        if installments < 1 or not 0 <= paid <= installments:
            raise ValueError("Confira a quantidade de parcelas pagas e totais.")
        if outstanding > 0 and paid == installments:
            raise ValueError("Uma dívida com todas as parcelas pagas deve ter saldo devedor igual a zero.")
        if outstanding == 0:
            paid = installments
        if scope not in {"personal", "work"}:
            raise ValueError("Uso pessoal ou de trabalho inválido.")
        return (
            self._required_text(description, "descrição"),
            self._required_text(creditor, "credor"),
            self._required_text(category, "categoria"),
            total,
            outstanding,
            self._iso_date(due_date, "vencimento"),
            installments,
            paid,
            "paid" if outstanding == 0 else "open",
            scope,
            notes.strip(),
        )

    def delete_debt(self, debt_id: int) -> None:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM debts WHERE id = ?", (int(debt_id),))
            self._ensure_updated(cursor, "Dívida não encontrada.")

    def confirm_income_received(self, transaction_id: int, received_date: str | None = None) -> None:
        actual_date = self._iso_date(received_date or date.today().isoformat(), "data de recebimento")
        with self.connect() as connection:
            transaction = connection.execute(
                "SELECT kind, status FROM transactions WHERE id = ?", (int(transaction_id),)
            ).fetchone()
            if transaction is None:
                raise ValueError("Recebimento não encontrado.")
            if transaction["kind"] != "income" or transaction["status"] != "pending":
                raise ValueError("Este lançamento não está aguardando recebimento.")
            connection.execute(
                "UPDATE transactions SET status = 'paid', transaction_date = ? WHERE id = ?",
                (actual_date, int(transaction_id)),
            )

    def add_goal(
        self,
        name: str,
        current_amount: float,
        target_amount: float,
        deadline: str,
        monthly_contribution: float = 0,
        notes: str = "",
    ) -> None:
        values = self._goal_values(name, current_amount, target_amount, deadline, monthly_contribution, notes)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO goals (name, current_amount, target_amount, deadline, monthly_contribution, notes) VALUES (?, ?, ?, ?, ?, ?)",
                values,
            )

    def update_goal(
        self,
        goal_id: int,
        name: str,
        current_amount: float,
        target_amount: float,
        deadline: str,
        monthly_contribution: float = 0,
        notes: str = "",
    ) -> None:
        values = self._goal_values(name, current_amount, target_amount, deadline, monthly_contribution, notes)
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE goals
                SET name = ?, current_amount = ?, target_amount = ?, deadline = ?, monthly_contribution = ?, notes = ?
                WHERE id = ?
                """,
                values + (int(goal_id),),
            )
            self._ensure_updated(cursor, "Meta não encontrada.")

    def _goal_values(
        self,
        name: str,
        current_amount: float,
        target_amount: float,
        deadline: str,
        monthly_contribution: float,
        notes: str,
    ) -> tuple[Any, ...]:
        return (
            self._required_text(name, "nome da meta"),
            self._positive(current_amount, "valor já reservado", allow_zero=True),
            self._positive(target_amount, "valor da meta"),
            self._iso_date(deadline, "prazo", optional=True),
            self._positive(monthly_contribution, "aporte mensal", allow_zero=True),
            notes.strip(),
        )

    def delete_goal(self, goal_id: int) -> None:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM goals WHERE id = ?", (int(goal_id),))
            self._ensure_updated(cursor, "Meta não encontrada.")

    def add_budget(self, category: str, monthly_limit: float, notes: str = "") -> None:
        values = self._budget_values(category, monthly_limit, notes)
        try:
            with self.connect() as connection:
                connection.execute("INSERT INTO budgets (category, monthly_limit, notes) VALUES (?, ?, ?)", values)
        except sqlite3.IntegrityError as error:
            raise ValueError("Já existe um orçamento para esta categoria.") from error

    def update_budget(self, budget_id: int, category: str, monthly_limit: float, notes: str = "") -> None:
        values = self._budget_values(category, monthly_limit, notes)
        try:
            with self.connect() as connection:
                cursor = connection.execute(
                    "UPDATE budgets SET category = ?, monthly_limit = ?, notes = ? WHERE id = ?",
                    values + (int(budget_id),),
                )
                self._ensure_updated(cursor, "Orçamento não encontrado.")
        except sqlite3.IntegrityError as error:
            raise ValueError("Já existe um orçamento para esta categoria.") from error

    def _budget_values(self, category: str, monthly_limit: float, notes: str) -> tuple[Any, ...]:
        return (
            self._required_text(category, "categoria"),
            self._positive(monthly_limit, "limite mensal"),
            notes.strip(),
        )

    def delete_budget(self, budget_id: int) -> None:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM budgets WHERE id = ?", (int(budget_id),))
            self._ensure_updated(cursor, "Orçamento não encontrado.")

    def add_investment(
        self,
        name: str,
        investment_type: str,
        invested: float,
        current_value: float,
        institution: str = "",
        quantity: float = 0,
        average_price: float = 0,
        notes: str = "",
        updated_at: str | None = None,
    ) -> None:
        values = self._investment_values(
            name, investment_type, invested, current_value, institution,
            quantity, average_price, notes, updated_at,
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO investments
                    (name, investment_type, invested, current_value, institution, quantity, average_price, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )

    def update_investment(
        self,
        investment_id: int,
        name: str,
        investment_type: str,
        invested: float,
        current_value: float,
        institution: str = "",
        quantity: float = 0,
        average_price: float = 0,
        notes: str = "",
        updated_at: str | None = None,
    ) -> None:
        values = self._investment_values(
            name, investment_type, invested, current_value, institution,
            quantity, average_price, notes, updated_at,
        )
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE investments
                SET name = ?, investment_type = ?, invested = ?, current_value = ?, institution = ?,
                    quantity = ?, average_price = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                values + (int(investment_id),),
            )
            self._ensure_updated(cursor, "Investimento não encontrado.")

    def _investment_values(
        self,
        name: str,
        investment_type: str,
        invested: float,
        current_value: float,
        institution: str,
        quantity: float,
        average_price: float,
        notes: str,
        updated_at: str | None,
    ) -> tuple[Any, ...]:
        return (
            self._required_text(name, "nome do investimento"),
            self._required_text(investment_type, "tipo"),
            self._positive(invested, "valor investido", allow_zero=True),
            self._positive(current_value, "valor atual", allow_zero=True),
            institution.strip(),
            self._positive(quantity, "quantidade", allow_zero=True),
            self._positive(average_price, "preço médio", allow_zero=True),
            notes.strip(),
            self._iso_date(updated_at or date.today().isoformat(), "atualização"),
        )

    def delete_investment(self, investment_id: int) -> None:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM investments WHERE id = ?", (int(investment_id),))
            self._ensure_updated(cursor, "Investimento não encontrado.")

    def snapshot(self) -> dict[str, Any]:
        return {
            "workspace": self.workspace(),
            "accounts": self.accounts(),
            "transactions": self.transactions(),
            "fixed_expenses": self.fixed_expenses(),
            "fixed_incomes": self.fixed_incomes(),
            "debts": self.debts(),
            "goals": self.goals(),
            "budgets": self.budgets(),
            "investments": self.investments(),
        }
