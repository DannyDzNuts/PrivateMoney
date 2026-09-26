from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from threading import RLock

from . import __version__
from .models import Account, Transaction


class PlaidError(RuntimeError):
    pass


class PlaidBridge:
    """Production Plaid client with support for multiple linked Items/banks."""

    HOST = "https://production.plaid.com"
    ENVIRONMENT = "Production"

    def __init__(self, state):
        self.state = state
        self._lock = RLock()
        self._client_id = ""
        self._secret = ""
        self._environment = self.ENVIRONMENT

        # item_id -> {
        #   access_token, cursor, accounts (raw list),
        #   transactions (transaction_id -> raw dict), institution_name
        # }
        self._items: dict[str, dict] = {}
        self._link_sessions: dict[str, tuple[str, float]] = {}
        self._status = "Not configured"

    @property
    def configured(self) -> bool:
        with self._lock:
            return bool(self._client_id and self._secret)

    @property
    def connected(self) -> bool:
        with self._lock:
            return bool(self._items)

    @property
    def linked_item_count(self) -> int:
        with self._lock:
            return len(self._items)

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def environment(self) -> str:
        return self.ENVIRONMENT

    def session_snapshot(self) -> dict:
        with self._lock:
            items = []
            for item_id, item in self._items.items():
                items.append(
                    {
                        "item_id": item_id,
                        "access_token": item.get("access_token", ""),
                        "cursor": item.get("cursor"),
                        "accounts": list(item.get("accounts") or []),
                        "transactions": list((item.get("transactions") or {}).values()),
                        "institution_name": item.get("institution_name", ""),
                    }
                )
            return {
                "client_id": self._client_id,
                "secret": self._secret,
                "environment": self.ENVIRONMENT,
                "items": items,
            }

    def restore_session(self, session: dict):
        with self._lock:
            saved_environment = str(session.get("environment") or "")
            self._environment = self.ENVIRONMENT
            self._items.clear()

            if saved_environment and saved_environment != self.ENVIRONMENT:
                self._client_id = ""
                self._secret = ""
                self._status = (
                    "Production Plaid credentials required · previous Sandbox session was not reused"
                )
                return

            self._client_id = str(session.get("client_id") or "").strip()
            self._secret = str(session.get("secret") or "").strip()

            items = session.get("items")
            if isinstance(items, list):
                for raw_item in items:
                    if not isinstance(raw_item, dict):
                        continue
                    item_id = str(raw_item.get("item_id") or "").strip()
                    access_token = str(raw_item.get("access_token") or "").strip()
                    if not item_id or not access_token:
                        continue
                    tx_rows = raw_item.get("transactions") or []
                    tx_cache = {
                        str(tx.get("transaction_id")): tx
                        for tx in tx_rows
                        if isinstance(tx, dict) and tx.get("transaction_id")
                    }
                    self._items[item_id] = {
                        "access_token": access_token,
                        "cursor": raw_item.get("cursor"),
                        "accounts": list(raw_item.get("accounts") or []),
                        "transactions": tx_cache,
                        "institution_name": str(
                            raw_item.get("institution_name") or ""
                        ).strip(),
                    }
            else:
                # Backward migration from the pre-0.6 single-Item vault format.
                item_id = str(session.get("item_id") or "").strip()
                access_token = str(session.get("access_token") or "").strip()
                if item_id and access_token:
                    # The old vault did not retain a per-Item transaction cache.
                    # Reset the cursor so the first sync rebuilds this Item fully.
                    self._items[item_id] = {
                        "access_token": access_token,
                        "cursor": None,
                        "accounts": [],
                        "transactions": {},
                        "institution_name": "",
                    }

            if self._items:
                count = len(self._items)
                self._status = (
                    f"{count} linked bank{'s' if count != 1 else ''} restored · ready to sync"
                )
            elif self._client_id and self._secret:
                self._status = "Production API credentials restored · next: Connect bank"
            else:
                self._status = "Not configured"

    def clear_sensitive_session(self):
        with self._lock:
            self._client_id = ""
            self._secret = ""
            self._items.clear()
            self._link_sessions.clear()
            self._status = "Not configured"

    def configure(self, client_id: str, secret: str, environment: str | None = None):
        client_id = "".join(client_id.split())
        secret = "".join(secret.split())
        if not client_id or not secret:
            raise PlaidError("Plaid client ID and Production secret are required.")

        with self._lock:
            changed_team = bool(self._client_id and self._client_id != client_id)
            self._client_id = client_id
            self._secret = secret
            self._environment = self.ENVIRONMENT
            if changed_team:
                # Access tokens are scoped to a Plaid team/client ID.
                self._items.clear()

            if self._items:
                count = len(self._items)
                self._status = (
                    f"Production API credentials updated · {count} linked bank"
                    f"{'s' if count != 1 else ''} retained"
                )
            else:
                self._status = "Production API credentials set · next: Connect bank"

    def create_link_session(self) -> str:
        if not self.configured:
            raise PlaidError("Configure Plaid first.")
        payload = {
            "user": {"client_user_id": "private-money-local-user"},
            "client_name": "PrivateMoney",
            "products": ["transactions"],
            "country_codes": ["US"],
            "language": "en",
            "transactions": {"days_requested": 180},
        }
        data = self._request("/link/token/create", payload)
        link_token = data.get("link_token")
        if not link_token:
            raise PlaidError("Plaid did not return a Link token.")
        nonce = secrets.token_urlsafe(32)
        with self._lock:
            self._link_sessions[nonce] = (
                link_token,
                datetime.now(timezone.utc).timestamp(),
            )
            self._status = "Waiting for bank connection in Plaid Link"
        return nonce

    def link_token_for(self, nonce: str) -> str | None:
        with self._lock:
            row = self._link_sessions.get(nonce)
            return row[0] if row else None

    def exchange_and_sync(
        self,
        nonce: str,
        public_token: str,
        institution_name: str = "",
    ) -> dict:
        with self._lock:
            if nonce not in self._link_sessions:
                raise PlaidError("This Plaid Link session is no longer valid.")
            self._status = "Exchanging Plaid token"

        exchanged = self._request(
            "/item/public_token/exchange",
            {"public_token": public_token},
        )
        access_token = str(exchanged.get("access_token") or "").strip()
        item_id = str(exchanged.get("item_id") or "").strip()
        if not access_token or not item_id:
            raise PlaidError("Plaid token exchange did not return an Item.")

        with self._lock:
            previous = self._items.get(item_id) or {}
            self._items[item_id] = {
                "access_token": access_token,
                "cursor": previous.get("cursor"),
                "accounts": list(previous.get("accounts") or []),
                "transactions": dict(previous.get("transactions") or {}),
                "institution_name": institution_name.strip()
                or previous.get("institution_name", ""),
            }
            self._link_sessions.pop(nonce, None)
            count = len(self._items)
            self._status = (
                f"Connected bank {count} · loading accounts and transactions"
            )

        # Sync all retained Items. This is especially important when migrating
        # the legacy single-Item format, whose cached accounts/transactions were
        # not persisted separately.
        self.sync()

        with self._lock:
            count = len(self._items)
        return {
            "ok": True,
            "item_connected": True,
            "linked_items": count,
            "source": "plaid",
        }

    def refresh_and_sync(self) -> dict:
        with self._lock:
            item_ids = list(self._items)

        if not item_ids:
            raise PlaidError("No Plaid bank is connected in this session.")

        errors: list[str] = []
        synced = 0
        for item_id in item_ids:
            with self._lock:
                item = self._items.get(item_id) or {}
                access_token = item.get("access_token", "")
            if not access_token:
                continue

            try:
                with self._lock:
                    self._status = (
                        f"Refreshing linked bank {synced + 1} of {len(item_ids)}…"
                    )
                try:
                    self._request(
                        "/transactions/refresh",
                        {"access_token": access_token},
                        timeout=75,
                    )
                except PlaidError as exc:
                    text = str(exc)
                    fallback_codes = (
                        "PRODUCT_NOT_ENABLED",
                        "PRODUCTS_NOT_SUPPORTED",
                        "PRODUCT_NOT_SUPPORTED",
                        "NO_AUTH_ACCOUNTS",
                    )
                    if not any(code in text for code in fallback_codes):
                        raise

                self._sync_item(item_id)
                synced += 1
            except PlaidError as exc:
                errors.append(f"{item_id}: {exc}")

        self._publish_merged_state()

        with self._lock:
            account_count, tx_count = self._merged_counts_locked()
            if errors and synced:
                self._status = (
                    f"Synced {synced} of {len(item_ids)} linked banks · "
                    f"{account_count} accounts · {len(errors)} bank needs attention"
                )
            elif errors:
                self._status = "Sync failed for all linked banks"
            else:
                self._status = (
                    f"Connected · {len(item_ids)} linked banks · "
                    f"{account_count} accounts · {tx_count} transactions"
                )

        if errors and not synced:
            raise PlaidError(errors[0])

        return {
            "items": len(item_ids),
            "synced_items": synced,
            "accounts": account_count,
            "transactions": tx_count,
            "errors": errors,
        }

    def sync(self) -> dict:
        with self._lock:
            item_ids = list(self._items)
        if not item_ids:
            raise PlaidError("No Plaid bank is connected in this session.")

        errors: list[str] = []
        synced = 0
        for item_id in item_ids:
            try:
                self._sync_item(item_id)
                synced += 1
            except PlaidError as exc:
                errors.append(f"{item_id}: {exc}")

        self._publish_merged_state()
        with self._lock:
            account_count, tx_count = self._merged_counts_locked()
            if errors and synced:
                self._status = (
                    f"Synced {synced} of {len(item_ids)} linked banks · "
                    f"{account_count} accounts"
                )
            elif errors:
                self._status = "Sync failed for all linked banks"
            else:
                self._status = (
                    f"Connected · {len(item_ids)} linked banks · "
                    f"{account_count} accounts · {tx_count} transactions"
                )

        if errors and not synced:
            raise PlaidError(errors[0])
        return {
            "items": len(item_ids),
            "synced_items": synced,
            "accounts": account_count,
            "transactions": tx_count,
            "errors": errors,
        }

    def _sync_item(self, item_id: str):
        with self._lock:
            item = self._items.get(item_id)
            if not item:
                raise PlaidError("Linked Plaid Item no longer exists.")
            access_token = item.get("access_token", "")
            cursor = item.get("cursor")
            existing_transactions = dict(item.get("transactions") or {})

        if not access_token:
            raise PlaidError("Linked Plaid Item has no access token.")

        accounts_payload = self._request(
            "/accounts/get",
            {"access_token": access_token},
        )
        raw_accounts = list(accounts_payload.get("accounts", []) or [])

        working_transactions = (
            dict(existing_transactions) if cursor else {}
        )
        working_cursor = cursor

        while True:
            body = {"access_token": access_token, "count": 500}
            if working_cursor:
                body["cursor"] = working_cursor
            page = self._request("/transactions/sync", body)

            for tx in page.get("added", []) or []:
                txid = tx.get("transaction_id")
                if txid:
                    working_transactions[str(txid)] = tx
            for tx in page.get("modified", []) or []:
                txid = tx.get("transaction_id")
                if txid:
                    working_transactions[str(txid)] = tx
            for tx in page.get("removed", []) or []:
                txid = tx.get("transaction_id")
                if txid:
                    working_transactions.pop(str(txid), None)

            working_cursor = page.get("next_cursor") or working_cursor
            if not page.get("has_more"):
                break

        with self._lock:
            current = self._items.get(item_id)
            if not current:
                return
            current["accounts"] = raw_accounts
            current["transactions"] = working_transactions
            current["cursor"] = working_cursor

    def _publish_merged_state(self):
        with self._lock:
            items = [
                {
                    "accounts": list(item.get("accounts") or []),
                    "transactions": list(
                        (item.get("transactions") or {}).values()
                    ),
                    "institution_name": item.get("institution_name", ""),
                }
                for item in self._items.values()
            ]

        accounts_by_id: dict[str, Account] = {}
        transactions_by_id: dict[str, Transaction] = {}

        for item in items:
            raw_accounts = item["accounts"]
            institution_name = item["institution_name"]
            account_names = {
                str(raw.get("account_id")): raw.get("name") or "Account"
                for raw in raw_accounts
                if raw.get("account_id")
            }

            for raw in raw_accounts:
                mapped = self._map_account(raw, institution_name)
                accounts_by_id[mapped.id] = mapped

            for raw in item["transactions"]:
                txid = str(raw.get("transaction_id") or "")
                mapped = self._map_transaction(raw, account_names)
                if txid:
                    transactions_by_id[txid] = mapped
                else:
                    transactions_by_id[secrets.token_hex(12)] = mapped

        self.state.replace_with_plaid(
            list(accounts_by_id.values()),
            list(transactions_by_id.values()),
        )

    def _merged_counts_locked(self) -> tuple[int, int]:
        account_ids = set()
        transaction_ids = set()
        for item in self._items.values():
            for account in item.get("accounts") or []:
                account_id = account.get("account_id")
                if account_id:
                    account_ids.add(str(account_id))
            for txid in (item.get("transactions") or {}):
                transaction_ids.add(str(txid))
        return len(account_ids), len(transaction_ids)

    def _request(self, path: str, payload: dict, timeout: int = 45) -> dict:
        with self._lock:
            client_id = self._client_id
            secret = self._secret
            host = self.HOST
        if not client_id or not secret:
            raise PlaidError("Plaid is not configured.")

        raw = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            host + path,
            data=raw,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "PLAID-CLIENT-ID": client_id,
                "PLAID-SECRET": secret,
                "User-Agent": f"PrivateMoney/{__version__}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode("utf-8"))
                code = (
                    body.get("error_code")
                    or body.get("error_type")
                    or f"HTTP {exc.code}"
                )
                message = body.get("error_message") or "Plaid request failed."
                request_id = body.get("request_id")
                suffix = f" · request {request_id}" if request_id else ""

                if code == "INVALID_API_KEYS":
                    raise PlaidError(
                        "INVALID_API_KEYS: Plaid rejected the Production client ID/secret. "
                        "Use the Production secret from the same Plaid team, not the Sandbox secret"
                        + suffix
                    ) from None
                if code == "UNAUTHORIZED_ENVIRONMENT":
                    raise PlaidError(
                        "UNAUTHORIZED_ENVIRONMENT: this Plaid team is not enabled for Production/Trial access"
                        + suffix
                    ) from None
                raise PlaidError(f"{code}: {message}{suffix}") from None
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise PlaidError(
                    f"Plaid request failed with HTTP {exc.code}."
                ) from None
        except urllib.error.URLError as exc:
            raise PlaidError(f"Could not reach Plaid: {exc.reason}") from None

    @staticmethod
    def _map_account(raw: dict, institution_name: str = "") -> Account:
        balances = raw.get("balances") or {}
        current = balances.get("current")
        available = balances.get("available")
        current = float(current or 0.0)
        typ = raw.get("type") or "other"
        subtype = raw.get("subtype") or typ
        signed = -abs(current) if typ in {"credit", "loan"} else current
        signed_available = None if available is None else float(available)
        return Account(
            id=raw.get("account_id") or secrets.token_hex(8),
            name=raw.get("name") or "Account",
            kind=str(subtype),
            institution=institution_name or "Plaid linked",
            current_balance=signed,
            available_balance=signed_available,
            mask=raw.get("mask"),
        )

    @staticmethod
    def _map_transaction(
        raw: dict,
        account_names: dict[str, str],
    ) -> Transaction:
        posted_raw = (
            raw.get("date")
            or raw.get("authorized_date")
            or date.today().isoformat()
        )
        try:
            posted = date.fromisoformat(posted_raw)
        except ValueError:
            posted = date.today()

        pfc = raw.get("personal_finance_category") or {}
        category = pfc.get("primary") or "Other"
        category = str(category).replace("_", " ").title()
        merchant = raw.get("merchant_name") or raw.get("name") or "Transaction"
        amount = -float(raw.get("amount") or 0.0)

        return Transaction(
            posted=posted,
            merchant=str(merchant),
            category=category,
            account=account_names.get(str(raw.get("account_id")), "Account"),
            amount=amount,
            pending=bool(raw.get("pending")),
            external_id=raw.get("transaction_id"),
        )
