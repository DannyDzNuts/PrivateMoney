from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .models import Account, Budget, RecurringCharge, Transaction


SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    institution TEXT NOT NULL DEFAULT '',
    current_balance_cents INTEGER NOT NULL DEFAULT 0,
    available_balance_cents INTEGER,
    mask TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    posted_date TEXT NOT NULL,
    merchant TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    account_name TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    pending INTEGER NOT NULL DEFAULT 0,
    external_id TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS budgets (
    category TEXT PRIMARY KEY,
    spent_cents INTEGER NOT NULL DEFAULT 0,
    limit_cents INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recurring (
    id TEXT PRIMARY KEY,
    merchant TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    cadence TEXT NOT NULL,
    next_date TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS net_worth_series (
    position INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    value_cents INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cashflow_series (
    position INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    income_cents INTEGER NOT NULL,
    outflow_cents INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS plaid_session (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    client_id TEXT NOT NULL DEFAULT '',
    secret TEXT NOT NULL DEFAULT '',
    environment TEXT NOT NULL DEFAULT 'Production',
    access_token TEXT NOT NULL DEFAULT '',
    item_id TEXT NOT NULL DEFAULT '',
    cursor TEXT
);
"""


class EncryptedStoreUnavailable(RuntimeError):
    pass


class VaultError(RuntimeError):
    pass


def _cents(value: float | None) -> int | None:
    if value is None:
        return None
    return int(round(float(value) * 100))


def _money(value: int | None) -> float | None:
    if value is None:
        return None
    return round(int(value) / 100.0, 2)


def _transaction_id(tx: Transaction) -> str:
    if tx.external_id:
        return f"external:{tx.external_id}"
    raw = "|".join(
        [
            tx.posted.isoformat(),
            tx.merchant,
            tx.category,
            tx.account,
            f"{tx.amount:.2f}",
            "1" if tx.pending else "0",
        ]
    )
    return "local:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


class EncryptedStore:
    """SQLCipher-backed storage. Plaintext SQLite fallback is intentionally disabled."""

    def __init__(self, path: Path, key_hex: str):
        try:
            from sqlcipher3 import dbapi2 as sqlite
        except Exception as exc:
            raise EncryptedStoreUnavailable(
                "SQLCipher is not installed. Plaintext fallback is intentionally disabled."
            ) from exc

        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.parent.chmod(0o700)
        except OSError:
            pass

        self.conn = sqlite.connect(str(self.path))
        try:
            self.conn.execute(f"PRAGMA key = \"x'{key_hex}'\";")
            version = self.conn.execute("PRAGMA cipher_version;").fetchone()
            if not version or not version[0]:
                raise EncryptedStoreUnavailable("The active SQLite binding does not provide SQLCipher.")
            self.conn.execute("PRAGMA cipher_memory_security = ON;")
            self.conn.execute("PRAGMA foreign_keys = ON;")
            # Any schema access here also validates an existing vault key.
            self.conn.executescript(SCHEMA)
            self.conn.commit()
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        except Exception:
            self.conn.close()
            raise

    def close(self):
        self.conn.close()

    def set_metadata(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO metadata(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_metadata(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def has_finance_data(self) -> bool:
        row = self.conn.execute("SELECT COUNT(*) FROM accounts").fetchone()
        tx = self.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()
        return bool((row and row[0]) or (tx and tx[0]))

    def save_state(self, state):
        accounts = state.accounts()
        transactions = state.transactions()
        budgets = state.budgets()
        recurring = state.recurring()
        net_worth = state.net_worth()
        cashflow = state.cashflow()

        with self.conn:
            self.conn.execute(
                "INSERT INTO metadata(key,value) VALUES('finance_source',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (state.source,),
            )

            self.conn.execute("DELETE FROM accounts")
            self.conn.executemany(
                """
                INSERT INTO accounts(
                    id,name,kind,institution,current_balance_cents,
                    available_balance_cents,mask
                ) VALUES(?,?,?,?,?,?,?)
                """,
                [
                    (
                        a.id,
                        a.name,
                        a.kind,
                        a.institution,
                        _cents(a.current_balance),
                        _cents(a.available_balance),
                        a.mask,
                    )
                    for a in accounts
                ],
            )

            self.conn.execute("DELETE FROM transactions")
            self.conn.executemany(
                """
                INSERT INTO transactions(
                    id,posted_date,merchant,category,account_name,
                    amount_cents,pending,external_id
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        _transaction_id(t),
                        t.posted.isoformat(),
                        t.merchant,
                        t.category,
                        t.account,
                        _cents(t.amount),
                        1 if t.pending else 0,
                        t.external_id,
                    )
                    for t in transactions
                ],
            )

            self.conn.execute("DELETE FROM budgets")
            self.conn.executemany(
                "INSERT INTO budgets(category,spent_cents,limit_cents) VALUES(?,?,?)",
                [(b.category, _cents(b.spent), _cents(b.limit)) for b in budgets],
            )

            self.conn.execute("DELETE FROM recurring")
            self.conn.executemany(
                """
                INSERT INTO recurring(id,merchant,amount_cents,cadence,next_date,category)
                VALUES(?,?,?,?,?,?)
                """,
                [
                    (
                        hashlib.sha256(
                            f"{r.merchant}|{r.cadence}|{r.next_date.isoformat()}".encode("utf-8")
                        ).hexdigest(),
                        r.merchant,
                        _cents(r.amount),
                        r.cadence,
                        r.next_date.isoformat(),
                        r.category,
                    )
                    for r in recurring
                ],
            )

            self.conn.execute("DELETE FROM net_worth_series")
            self.conn.executemany(
                "INSERT INTO net_worth_series(position,label,value_cents) VALUES(?,?,?)",
                [(i, label, _cents(value)) for i, (label, value) in enumerate(net_worth)],
            )

            self.conn.execute("DELETE FROM cashflow_series")
            self.conn.executemany(
                "INSERT INTO cashflow_series(position,label,income_cents,outflow_cents) VALUES(?,?,?,?)",
                [
                    (i, label, _cents(income), _cents(outflow))
                    for i, (label, income, outflow) in enumerate(cashflow)
                ],
            )

    def load_state_snapshot(self) -> dict[str, Any]:
        accounts = [
            Account(
                id=row[0],
                name=row[1],
                kind=row[2],
                institution=row[3] or "",
                current_balance=_money(row[4]) or 0.0,
                available_balance=_money(row[5]),
                mask=row[6],
            )
            for row in self.conn.execute(
                """
                SELECT id,name,kind,institution,current_balance_cents,
                       available_balance_cents,mask
                FROM accounts ORDER BY rowid
                """
            )
        ]

        from datetime import date

        transactions = [
            Transaction(
                posted=date.fromisoformat(row[0]),
                merchant=row[1],
                category=row[2] or "Other",
                account=row[3],
                amount=_money(row[4]) or 0.0,
                pending=bool(row[5]),
                external_id=row[6],
            )
            for row in self.conn.execute(
                """
                SELECT posted_date,merchant,category,account_name,
                       amount_cents,pending,external_id
                FROM transactions
                ORDER BY posted_date DESC, rowid DESC
                """
            )
        ]

        budgets = [
            Budget(row[0], _money(row[1]) or 0.0, _money(row[2]) or 0.0)
            for row in self.conn.execute(
                "SELECT category,spent_cents,limit_cents FROM budgets ORDER BY rowid"
            )
        ]

        recurring = [
            RecurringCharge(
                merchant=row[0],
                amount=_money(row[1]) or 0.0,
                cadence=row[2],
                next_date=date.fromisoformat(row[3]),
                category=row[4] or "Other",
            )
            for row in self.conn.execute(
                "SELECT merchant,amount_cents,cadence,next_date,category FROM recurring ORDER BY next_date"
            )
        ]

        net_worth = [
            (row[0], _money(row[1]) or 0.0)
            for row in self.conn.execute(
                "SELECT label,value_cents FROM net_worth_series ORDER BY position"
            )
        ]

        cashflow = [
            (row[0], _money(row[1]) or 0.0, _money(row[2]) or 0.0)
            for row in self.conn.execute(
                "SELECT label,income_cents,outflow_cents FROM cashflow_series ORDER BY position"
            )
        ]

        return {
            "source": self.get_metadata("finance_source") or "local",
            "accounts": accounts,
            "transactions": transactions,
            "budgets": budgets,
            "recurring": recurring,
            "net_worth": net_worth,
            "cashflow": cashflow,
        }

    def save_plaid_session(self, session: dict[str, Any]):
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO plaid_session(
                    id,client_id,secret,environment,access_token,item_id,cursor
                ) VALUES(1,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    client_id=excluded.client_id,
                    secret=excluded.secret,
                    environment=excluded.environment,
                    access_token=excluded.access_token,
                    item_id=excluded.item_id,
                    cursor=excluded.cursor
                """,
                (
                    session.get("client_id", ""),
                    session.get("secret", ""),
                    session.get("environment", "Sandbox"),
                    session.get("access_token", ""),
                    session.get("item_id", ""),
                    session.get("cursor"),
                ),
            )

    def save_import_profile(self, signature: str, profile: dict[str, Any]):
        self.set_metadata(
            f"import_profile:{signature}",
            json.dumps(profile, sort_keys=True, separators=(",", ":")),
        )

    def load_import_profile(self, signature: str) -> dict[str, Any] | None:
        raw = self.get_metadata(f"import_profile:{signature}")
        if not raw:
            return None
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None

    def load_plaid_session(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT client_id,secret,environment,access_token,item_id,cursor
            FROM plaid_session WHERE id=1
            """
        ).fetchone()
        if not row:
            return None
        return {
            "client_id": row[0],
            "secret": row[1],
            "environment": row[2],
            "access_token": row[3],
            "item_id": row[4],
            "cursor": row[5],
        }


class VaultManager:
    """Owns the encrypted vault and Argon2id key derivation."""

    SALT_BYTES = 16

    def __init__(self, base_dir: Path | None = None):
        if base_dir is None:
            data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
            base_dir = data_home / "PrivateMoney"
        self.base_dir = Path(base_dir)
        self.db_path = self.base_dir / "vault.db"
        self.salt_path = self.base_dir / "vault.salt"
        self.store: EncryptedStore | None = None

    @property
    def exists(self) -> bool:
        return self.db_path.exists() and self.salt_path.exists()

    @property
    def unlocked(self) -> bool:
        return self.store is not None

    def _derive_key(self, passphrase: str, salt: bytes) -> str:
        try:
            from argon2.low_level import Type, hash_secret_raw
        except Exception as exc:
            raise EncryptedStoreUnavailable("Argon2id support is not installed.") from exc

        if not passphrase:
            raise VaultError("Vault passphrase cannot be empty.")

        raw = hash_secret_raw(
            secret=passphrase.encode("utf-8"),
            salt=salt,
            time_cost=3,
            memory_cost=65536,
            parallelism=2,
            hash_len=32,
            type=Type.ID,
        )
        return raw.hex()

    def create(self, passphrase: str):
        if self.exists:
            raise VaultError("An encrypted vault already exists.")
        if len(passphrase) < 10:
            raise VaultError("Use a vault passphrase of at least 10 characters.")

        self.base_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.base_dir.chmod(0o700)
        except OSError:
            pass

        salt = os.urandom(self.SALT_BYTES)
        fd = os.open(self.salt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(salt)
        except Exception:
            self.salt_path.unlink(missing_ok=True)
            raise

        try:
            self.store = EncryptedStore(self.db_path, self._derive_key(passphrase, salt))
            self.store.set_metadata("vault_version", "1")
        except Exception:
            self.store = None
            self.db_path.unlink(missing_ok=True)
            self.salt_path.unlink(missing_ok=True)
            raise

    def unlock(self, passphrase: str):
        if not self.exists:
            raise VaultError("No encrypted vault exists yet.")
        salt = self.salt_path.read_bytes()
        if len(salt) != self.SALT_BYTES:
            raise VaultError("Vault salt is invalid.")
        try:
            store = EncryptedStore(self.db_path, self._derive_key(passphrase, salt))
            if store.get_metadata("vault_version") != "1":
                store.close()
                raise VaultError("Vault format is not recognized.")
        except VaultError:
            raise
        except Exception as exc:
            raise VaultError("Could not unlock the vault. Check the passphrase.") from exc
        self.store = store

    def lock(self):
        if self.store is not None:
            self.store.close()
            self.store = None

    def destroy(self):
        """Permanently delete all local PrivateMoney vault material."""
        self.lock()
        targets = (
            self.db_path,
            self.salt_path,
            Path(str(self.db_path) + "-wal"),
            Path(str(self.db_path) + "-shm"),
            Path(str(self.db_path) + "-journal"),
        )
        errors = []
        for path in targets:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f"{path.name}: {exc}")
        if errors:
            raise VaultError("Could not delete all PrivateMoney data: " + "; ".join(errors))
        try:
            fd = os.open(self.base_dir, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass

    def save_import_profile(self, signature: str, profile: dict[str, Any]):
        if not self.store:
            raise VaultError("PrivateMoney is locked.")
        self.store.save_import_profile(signature, profile)

    def load_import_profile(self, signature: str) -> dict[str, Any] | None:
        if not self.store:
            return None
        return self.store.load_import_profile(signature)

    def save_runtime(self, state, plaid):
        if not self.store:
            return
        self.store.save_state(state)
        self.store.save_plaid_session(plaid.session_snapshot())

    def restore_runtime(self, state, plaid) -> bool:
        if not self.store:
            return False
        restored = False
        if self.store.has_finance_data():
            state.restore_snapshot(self.store.load_state_snapshot())
            restored = True
        session = self.store.load_plaid_session()
        if session:
            plaid.restore_session(session)
        return restored
