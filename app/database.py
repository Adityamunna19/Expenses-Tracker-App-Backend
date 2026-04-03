from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "expenses.db"


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS auth_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id
            ON auth_sessions(user_id);

            CREATE TABLE IF NOT EXISTS raw_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                sender TEXT NOT NULL DEFAULT '',
                message_text TEXT NOT NULL,
                received_at TEXT,
                parse_status TEXT NOT NULL DEFAULT 'pending',
                parse_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS merchant_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias TEXT NOT NULL UNIQUE,
                merchant_clean TEXT NOT NULL,
                default_category TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.9,
                source TEXT NOT NULL DEFAULT 'system',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_message_id INTEGER,
                source_type TEXT NOT NULL,
                title TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount >= 0),
                currency TEXT NOT NULL DEFAULT 'INR',
                category TEXT NOT NULL,
                payment_method TEXT NOT NULL DEFAULT 'unknown',
                merchant_raw TEXT NOT NULL DEFAULT '',
                merchant_clean TEXT NOT NULL DEFAULT '',
                expense_at TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending_review',
                categorization_confidence REAL NOT NULL DEFAULT 0,
                categorization_strategy TEXT NOT NULL DEFAULT 'rule_based',
                needs_review INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(raw_message_id) REFERENCES raw_messages(id)
            );

            CREATE INDEX IF NOT EXISTS idx_transactions_expense_at
            ON transactions(expense_at DESC);

            CREATE INDEX IF NOT EXISTS idx_transactions_status
            ON transactions(status);

            CREATE INDEX IF NOT EXISTS idx_transactions_merchant_clean
            ON transactions(merchant_clean);

            CREATE TABLE IF NOT EXISTS receivable_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expense_id INTEGER,
                title TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                note TEXT NOT NULL DEFAULT '',
                remind_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                received_transaction_id INTEGER,
                received_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(expense_id) REFERENCES transactions(id),
                FOREIGN KEY(received_transaction_id) REFERENCES transactions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_receivable_reminders_remind_at
            ON receivable_reminders(remind_at ASC);

            CREATE INDEX IF NOT EXISTS idx_receivable_reminders_status
            ON receivable_reminders(status);
            """
        )

        ensure_column(
            connection,
            "transactions",
            "user_id",
            "INTEGER REFERENCES users(id)",
        )
        ensure_column(
            connection,
            "receivable_reminders",
            "user_id",
            "INTEGER REFERENCES users(id)",
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transactions_user_id
            ON transactions(user_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_receivable_reminders_user_id
            ON receivable_reminders(user_id)
            """
        )

        seed_default_aliases(connection)
        connection.commit()


def seed_default_aliases(connection: sqlite3.Connection) -> None:
    aliases = [
        ("swiggy", "Swiggy", "Food", 0.98),
        ("zomato", "Zomato", "Food", 0.98),
        ("uber", "Uber", "Travel", 0.96),
        ("ola", "Ola", "Travel", 0.96),
        ("amazon", "Amazon", "Shopping", 0.95),
        ("flipkart", "Flipkart", "Shopping", 0.95),
        ("dmart", "DMart", "Groceries", 0.97),
        ("bigbasket", "BigBasket", "Groceries", 0.97),
        ("apollo", "Apollo Pharmacy", "Health", 0.93),
        ("phonepe", "PhonePe", "Transfers", 0.65),
        ("gpay", "Google Pay", "Transfers", 0.65),
    ]
    connection.executemany(
        """
        INSERT OR IGNORE INTO merchant_aliases
        (alias, merchant_clean, default_category, confidence, source)
        VALUES (?, ?, ?, ?, 'system')
        """,
        aliases,
    )


def ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    existing_columns = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in existing_columns:
        return
    connection.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
    )


@contextmanager
def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()
