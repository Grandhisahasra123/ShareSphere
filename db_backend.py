"""
Database backend for ShareSphere.
Supports Supabase PostgreSQL (via psycopg) and local SQLite fallback.
"""

import os
import re
import sqlite3
from pathlib import Path

# Load .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import psycopg
    from psycopg import errors as pg_errors
    HAS_PSYCOPG = True
except ImportError:
    HAS_PSYCOPG = False
    pg_errors = None

DB_PATH = Path(__file__).resolve().parent / "sharesphere.db"

# Unified DB exceptions
if HAS_PSYCOPG:
    DBIntegrityError = (sqlite3.IntegrityError, pg_errors.IntegrityError)
    DBError = (sqlite3.Error, pg_errors.Error)
else:
    DBIntegrityError = (sqlite3.IntegrityError,)
    DBError = (sqlite3.Error,)


def get_database_url():
    """Retrieves PostgreSQL connection URL from environment or Streamlit secrets."""
    url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or os.environ.get("SUPABASE_DB_URL")
    if not url:
        try:
            import streamlit as st
            if hasattr(st, "secrets"):
                if "DATABASE_URL" in st.secrets:
                    url = st.secrets["DATABASE_URL"]
                elif "postgres" in st.secrets and "url" in st.secrets["postgres"]:
                    url = st.secrets["postgres"]["url"]
                elif "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
                    url = st.secrets["connections"]["postgresql"].get("url", "")
        except Exception:
            pass

    if url:
        url = url.strip()
        # Supabase requires SSL; ensure sslmode=require if connecting to Supabase
        if "supabase" in url and "sslmode=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}sslmode=require"
        return url

    return None


def is_postgres():
    """True if DATABASE_URL is configured and psycopg is available."""
    return bool(get_database_url() and HAS_PSYCOPG)


class HybridRow(dict):
    """
    Dictionary-like row that also supports integer indexing like row[0]
    to ensure full compatibility with sqlite3.Row across all existing queries.
    """
    def __init__(self, values, column_names):
        super().__init__()
        self._values = tuple(values)
        for i, name in enumerate(column_names):
            self[name] = values[i]

    def __getitem__(self, item):
        if isinstance(item, int):
            return self._values[item]
        return super().__getitem__(item)


class PostgresCursorWrapper:
    """Wraps a psycopg Cursor to match sqlite3 cursor behaviors."""
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def fetchone(self):
        if not self._cursor.description:
            return None
        row = self._cursor.fetchone()
        if row is None:
            return None
        col_names = [desc.name for desc in self._cursor.description]
        return HybridRow(row, col_names)

    def fetchall(self):
        if not self._cursor.description:
            return []
        rows = self._cursor.fetchall()
        if not rows:
            return []
        col_names = [desc.name for desc in self._cursor.description]
        return [HybridRow(r, col_names) for r in rows]

    def __iter__(self):
        return self

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row

    def close(self):
        try:
            self._cursor.close()
        except Exception:
            pass


class PostgresConnectionWrapper:
    """
    Wraps a psycopg Connection to provide full API compatibility with sqlite3.Connection
    as used in ShareSphere (e.g. conn.execute(), isolation_level, commit(), rollback()).
    """
    def __init__(self, raw_conn):
        self._conn = raw_conn
        self._isolation_level = None
        self.row_factory = None

    @property
    def isolation_level(self):
        return self._isolation_level

    @isolation_level.setter
    def isolation_level(self, val):
        self._isolation_level = val

    def cursor(self):
        return PostgresCursorWrapper(self._conn.cursor())

    def _adapt_query(self, sql):
        # 1. Adapt datetime('now') -> TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
        sql_adapted = re.sub(
            r"datetime\s*\(\s*['\"]now['\"]\s*\)",
            "TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')",
            sql,
            flags=re.IGNORECASE
        )
        # 2. Replace parameter placeholders '?' with '%s'
        sql_adapted = sql_adapted.replace("?", "%s")
        return sql_adapted

    def execute(self, sql, params=None):
        clean_sql = sql.strip()
        upper_sql = clean_sql.upper()

        # Handle SQLite transaction statements in PostgreSQL
        if upper_sql in ("BEGIN IMMEDIATE", "BEGIN"):
            return self
        if upper_sql == "COMMIT":
            self._conn.commit()
            return self
        if upper_sql == "ROLLBACK":
            self._conn.rollback()
            return self
        if upper_sql.startswith("PRAGMA"):
            return self

        adapted_sql = self._adapt_query(clean_sql)
        cursor = self._conn.cursor()
        if params is not None:
            cursor.execute(adapted_sql, params)
        else:
            cursor.execute(adapted_sql)
        return PostgresCursorWrapper(cursor)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()
        self.close()


def get_db_connection():
    """Returns a connection to Supabase PostgreSQL if configured, else SQLite."""
    db_url = get_database_url()
    if db_url and HAS_PSYCOPG:
        raw_conn = psycopg.connect(db_url)
        return PostgresConnectionWrapper(raw_conn)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def init_database():
    """Initializes tables and indexes idempotently on the active database."""
    if is_postgres():
        _init_postgres()
        _check_and_migrate_if_empty()
    else:
        _init_sqlite()


def _init_postgres():
    conn = get_db_connection()
    try:
        # 1. Students table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_salt BYTEA NOT NULL,
                password_hash BYTEA NOT NULL
            )
            """
        )

        # 2. Items table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                fee_type TEXT NOT NULL,
                fee_amount DOUBLE PRECISION NOT NULL,
                deposit DOUBLE PRECISION NOT NULL,
                estimated_price DOUBLE PRECISION NOT NULL DEFAULT 0,
                owner_student_id INTEGER NOT NULL REFERENCES students (id),
                created_at TEXT NOT NULL,
                currently_borrowed INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        # 3. Borrowing requests table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS borrowing_requests (
                id TEXT PRIMARY KEY,
                item_id TEXT NOT NULL REFERENCES items (id),
                borrower_student_id INTEGER NOT NULL REFERENCES students (id),
                owner_student_id INTEGER NOT NULL REFERENCES students (id),
                requested_days INTEGER NOT NULL,
                borrowing_fee DOUBLE PRECISION NOT NULL,
                refundable_deposit DOUBLE PRECISION NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payment_status TEXT NOT NULL DEFAULT 'Unpaid',
                terms_accepted_at TEXT,
                paid_at TEXT,
                return_requested_at TEXT,
                return_condition TEXT,
                damage_notes TEXT,
                damage_deduction DOUBLE PRECISION DEFAULT 0.0,
                borrower_response TEXT,
                refund_amount DOUBLE PRECISION DEFAULT 0.0,
                refunded_at TEXT,
                dispute_reason TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uniq_pending_borrower_item
            ON borrowing_requests (item_id, borrower_student_id)
            WHERE status = 'Pending'
            """
        )

        # 4. Demo payments table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS demo_payments (
                id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL REFERENCES borrowing_requests (id),
                borrower_student_id INTEGER NOT NULL REFERENCES students (id),
                owner_student_id INTEGER NOT NULL REFERENCES students (id),
                borrowing_fee DOUBLE PRECISION NOT NULL,
                refundable_deposit DOUBLE PRECISION NOT NULL,
                total_paid DOUBLE PRECISION NOT NULL,
                payment_type TEXT NOT NULL DEFAULT 'Demo Payment',
                payment_status TEXT NOT NULL DEFAULT 'Completed',
                paid_at TEXT NOT NULL,
                refund_amount DOUBLE PRECISION DEFAULT 0.0,
                refund_status TEXT NOT NULL DEFAULT 'Not Refunded',
                refunded_at TEXT,
                refund_notes TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uniq_demo_payment_request
            ON demo_payments (request_id)
            """
        )
        conn.commit()
    finally:
        conn.close()


def _check_and_migrate_if_empty():
    """If Postgres database is brand new and SQLite has existing data, auto-migrate."""
    if not DB_PATH.exists():
        return
    conn = get_db_connection()
    try:
        res = conn.execute("SELECT COUNT(*) FROM students").fetchone()
        if res and res[0] == 0:
            migrate_sqlite_data_to_postgres()
    except Exception:
        pass
    finally:
        conn.close()


def _init_sqlite():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    # 1. Students table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_salt BLOB NOT NULL,
            password_hash BLOB NOT NULL
        )
        """
    )

    # 2. Items table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            fee_type TEXT NOT NULL,
            fee_amount REAL NOT NULL,
            deposit REAL NOT NULL,
            estimated_price REAL NOT NULL DEFAULT 0,
            owner_student_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            currently_borrowed INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (owner_student_id) REFERENCES students (id)
        )
        """
    )
    item_cols = [c["name"] for c in connection.execute("PRAGMA table_info(items)").fetchall()]
    if "estimated_price" not in item_cols:
        connection.execute("ALTER TABLE items ADD COLUMN estimated_price REAL NOT NULL DEFAULT 0")
    if "currently_borrowed" not in item_cols:
        connection.execute("ALTER TABLE items ADD COLUMN currently_borrowed INTEGER NOT NULL DEFAULT 0")

    # 3. Borrowing requests table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS borrowing_requests (
            id TEXT PRIMARY KEY,
            item_id TEXT NOT NULL,
            borrower_student_id INTEGER NOT NULL,
            owner_student_id INTEGER NOT NULL,
            requested_days INTEGER NOT NULL,
            borrowing_fee REAL NOT NULL,
            refundable_deposit REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            payment_status TEXT NOT NULL DEFAULT 'Unpaid',
            terms_accepted_at TEXT,
            paid_at TEXT,
            return_requested_at TEXT,
            return_condition TEXT,
            damage_notes TEXT,
            damage_deduction REAL DEFAULT 0.0,
            borrower_response TEXT,
            refund_amount REAL DEFAULT 0.0,
            refunded_at TEXT,
            dispute_reason TEXT,
            FOREIGN KEY (item_id) REFERENCES items (id),
            FOREIGN KEY (borrower_student_id) REFERENCES students (id),
            FOREIGN KEY (owner_student_id) REFERENCES students (id)
        )
        """
    )
    req_cols = [c["name"] for c in connection.execute("PRAGMA table_info(borrowing_requests)").fetchall()]
    safe_new_cols = [
        ("payment_status", "TEXT NOT NULL DEFAULT 'Unpaid'"),
        ("terms_accepted_at", "TEXT"),
        ("paid_at", "TEXT"),
        ("return_requested_at", "TEXT"),
        ("return_condition", "TEXT"),
        ("damage_notes", "TEXT"),
        ("damage_deduction", "REAL DEFAULT 0.0"),
        ("borrower_response", "TEXT"),
        ("refund_amount", "REAL DEFAULT 0.0"),
        ("refunded_at", "TEXT"),
        ("dispute_reason", "TEXT"),
    ]
    for col_name, col_def in safe_new_cols:
        if col_name not in req_cols:
            connection.execute(f"ALTER TABLE borrowing_requests ADD COLUMN {col_name} {col_def}")

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_pending_borrower_item
        ON borrowing_requests (item_id, borrower_student_id)
        WHERE status = 'Pending'
        """
    )

    # 4. Demo payments table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS demo_payments (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            borrower_student_id INTEGER NOT NULL,
            owner_student_id INTEGER NOT NULL,
            borrowing_fee REAL NOT NULL,
            refundable_deposit REAL NOT NULL,
            total_paid REAL NOT NULL,
            payment_type TEXT NOT NULL DEFAULT 'Demo Payment',
            payment_status TEXT NOT NULL DEFAULT 'Completed',
            paid_at TEXT NOT NULL,
            refund_amount REAL DEFAULT 0.0,
            refund_status TEXT NOT NULL DEFAULT 'Not Refunded',
            refunded_at TEXT,
            refund_notes TEXT,
            FOREIGN KEY (request_id) REFERENCES borrowing_requests (id),
            FOREIGN KEY (borrower_student_id) REFERENCES students (id),
            FOREIGN KEY (owner_student_id) REFERENCES students (id)
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_demo_payment_request
        ON demo_payments (request_id)
        """
    )
    connection.commit()
    connection.close()


def migrate_sqlite_data_to_postgres():
    """Migrates all rows from local SQLite database into PostgreSQL idempotently."""
    if not is_postgres():
        return False, "PostgreSQL is not configured."
    if not DB_PATH.exists():
        return False, f"SQLite database {DB_PATH} not found."

    sq_conn = sqlite3.connect(DB_PATH)
    sq_conn.row_factory = sqlite3.Row
    pg_conn = get_db_connection()

    try:
        # Ensure PostgreSQL tables exist first
        _init_postgres()

        # 1. Students
        sq_students = sq_conn.execute("SELECT * FROM students ORDER BY id").fetchall()
        for s in sq_students:
            pg_conn.execute(
                """
                INSERT INTO students (id, name, email, password_salt, password_hash)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING
                """,
                (s["id"], s["name"], s["email"], bytes(s["password_salt"]), bytes(s["password_hash"]))
            )
        # Advance sequence for students id
        if sq_students:
            pg_conn.execute(
                "SELECT setval(pg_get_serial_sequence('students', 'id'), COALESCE((SELECT MAX(id) FROM students), 1))"
            )

        # 2. Items
        sq_items = sq_conn.execute("SELECT * FROM items").fetchall()
        for item in sq_items:
            pg_conn.execute(
                """
                INSERT INTO items (
                    id, name, description, fee_type, fee_amount, deposit,
                    estimated_price, owner_student_id, created_at, currently_borrowed
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    item["id"], item["name"], item["description"], item["fee_type"],
                    float(item["fee_amount"]), float(item["deposit"]), float(item["estimated_price"] or 0.0),
                    int(item["owner_student_id"]), item["created_at"], int(item["currently_borrowed"] or 0)
                )
            )

        # 3. Borrowing requests
        sq_reqs = sq_conn.execute("SELECT * FROM borrowing_requests").fetchall()
        for r in sq_reqs:
            pg_conn.execute(
                """
                INSERT INTO borrowing_requests (
                    id, item_id, borrower_student_id, owner_student_id, requested_days,
                    borrowing_fee, refundable_deposit, status, created_at, payment_status,
                    terms_accepted_at, paid_at, return_requested_at, return_condition,
                    damage_notes, damage_deduction, borrower_response, refund_amount,
                    refunded_at, dispute_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    r["id"], r["item_id"], int(r["borrower_student_id"]), int(r["owner_student_id"]),
                    int(r["requested_days"]), float(r["borrowing_fee"]), float(r["refundable_deposit"]),
                    r["status"], r["created_at"], r["payment_status"] or "Unpaid",
                    r["terms_accepted_at"], r["paid_at"], r["return_requested_at"], r["return_condition"],
                    r["damage_notes"], float(r["damage_deduction"] or 0.0), r["borrower_response"],
                    float(r["refund_amount"] or 0.0), r["refunded_at"], r["dispute_reason"]
                )
            )

        # 4. Demo payments
        sq_pmts = sq_conn.execute("SELECT * FROM demo_payments").fetchall()
        for p in sq_pmts:
            pg_conn.execute(
                """
                INSERT INTO demo_payments (
                    id, request_id, borrower_student_id, owner_student_id, borrowing_fee,
                    refundable_deposit, total_paid, payment_type, payment_status, paid_at,
                    refund_amount, refund_status, refunded_at, refund_notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    p["id"], p["request_id"], int(p["borrower_student_id"]), int(p["owner_student_id"]),
                    float(p["borrowing_fee"]), float(p["refundable_deposit"]), float(p["total_paid"]),
                    p["payment_type"] or "Demo Payment", p["payment_status"] or "Completed", p["paid_at"],
                    float(p["refund_amount"] or 0.0), p["refund_status"] or "Not Refunded", p["refunded_at"], p["refund_notes"]
                )
            )

        pg_conn.commit()
        return True, (
            f"Successfully migrated {len(sq_students)} students, {len(sq_items)} items, "
            f"{len(sq_reqs)} borrowing requests, and {len(sq_pmts)} demo payments."
        )
    finally:
        sq_conn.close()
        pg_conn.close()
