from __future__ import annotations
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    institution TEXT,
    current_balance_cents INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    posted_date TEXT NOT NULL,
    merchant TEXT NOT NULL,
    normalized_merchant TEXT,
    category TEXT,
    amount_cents INTEGER NOT NULL,
    pending INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    source_fingerprint TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY,
    month TEXT NOT NULL,
    category TEXT NOT NULL,
    limit_cents INTEGER NOT NULL,
    UNIQUE(month, category)
);
CREATE TABLE IF NOT EXISTS recurring_rules (
    id INTEGER PRIMARY KEY,
    merchant_pattern TEXT NOT NULL,
    cadence TEXT NOT NULL,
    expected_amount_cents INTEGER,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS net_worth_snapshots (
    snapshot_date TEXT PRIMARY KEY,
    assets_cents INTEGER NOT NULL,
    liabilities_cents INTEGER NOT NULL
);
"""

class EncryptedStoreUnavailable(RuntimeError):
    pass

class EncryptedStore:
    """SQLCipher-backed storage. The app intentionally does not fall back to plaintext SQLite."""
    def __init__(self, path: Path, key_hex: str):
        try:
            from sqlcipher3 import dbapi2 as sqlite
        except Exception as exc:
            raise EncryptedStoreUnavailable(
                "SQLCipher binding is not installed. Plaintext fallback is intentionally disabled."
            ) from exc
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite.connect(str(self.path))
        self.conn.execute(f"PRAGMA key = \"x'{key_hex}'\";")
        self.conn.execute("PRAGMA cipher_memory_security = ON;")
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()
