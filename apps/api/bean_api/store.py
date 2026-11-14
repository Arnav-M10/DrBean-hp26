"""One authoritative local SQLite store; never an implicit hosted fallback."""

from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3
from typing import Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Store:
    """Connection-per-transaction store, safe across request threads/processes.

    ``BEGIN IMMEDIATE`` serializes reservations, while unique indexes enforce
    durable work identities even if application code changes. Provider and solver
    calls must happen after the transaction closes.
    """

    SCHEMA_VERSION = 2

    def __init__(self, path: str | Path):
        self.path = str(Path(path).resolve())
        if str(path) == ":memory:":
            raise ValueError("Use an explicit file-backed SQLite lane for durable work")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.migrate()
        os.chmod(self.path, 0o600)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def migrate(self) -> None:
        migration = Path(__file__).resolve().parent / "migrations" / "0001_initial.sql"
        with closing(self.connect()) as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > self.SCHEMA_VERSION:
                raise RuntimeError("Database schema is newer than this application")
            conn.execute("PRAGMA journal_mode=WAL")
            if version < 1:
                # Idempotent, additive migration; no table or populated data drops.
                conn.executescript("BEGIN IMMEDIATE;\n" + migration.read_text() + "\nCOMMIT;")
                conn.execute("INSERT OR IGNORE INTO schema_migrations VALUES (?, ?)", (1, utc_now()))
                conn.execute("PRAGMA user_version=1")
            if version < 2:
                research = migration.with_name("0002_research.sql")
                conn.executescript("BEGIN IMMEDIATE;\n" + research.read_text() +
                    "\nINSERT OR IGNORE INTO schema_migrations VALUES (2, strftime('%Y-%m-%dT%H:%M:%fZ','now'));"
                    "\nPRAGMA user_version=2;\nCOMMIT;")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("PRAGMA query_only=ON")
            yield conn
        finally:
            conn.close()

    def backup(self, destination: str | Path) -> None:
        """Consistent SQLite backup; caller owns access and restore verification."""
        with closing(self.connect()) as source, closing(sqlite3.connect(str(destination))) as target:
            source.backup(target)
        os.chmod(destination, 0o600)
