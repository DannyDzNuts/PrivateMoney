from __future__ import annotations
import json
import secrets
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from threading import RLock
from .models import Account, Transaction


class PlaidError(RuntimeError):
    pass


class PlaidBridge:
    """Minimal Plaid client for a single-user local desktop app.

    Credentials, access tokens, and sync cursors are intentionally kept in memory only
    in the current development build. Nothing sensitive is written to disk.
    """
    HOST = "https://production.plaid.com"
    ENVIRONMENT = "Production"

    def __init__(self, state):
        self.state = state
        self._lock = RLock()
        self._client_id = ""
        self._secret = ""
        self._environment = self.ENVIRONMENT
        self._access_token = ""
        self._item_id = ""
        self._cursor: str | None = None
        self._transactions: dict[str, dict] = {}
        self._link_sessions: dict[str, tuple[str, float]] = {}
        self._status = "Not configured"

    @property
    def configured(self) -> bool:
        with self._lock:
            return bool(self._client_id and self._secret)

    @property
    def connected(self) -> bool:
        with self._lock:
            return bool(self._access_token)

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def environment(self) -> str:
        return self.ENVIRONMENT

    def session_snapshot(self) -> dict:
        with self._lock:
            return {
                "client_id": self._client_id,
                "secret": self._secret,
                "environment": self.ENVIRONMENT,
                "access_token": self._access_token,
                "item_id": self._item_id,
                "cursor": self._cursor,
            }

    def restore_session(self, session: dict):
        with self._lock:
            saved_environment = str(session.get("environment") or "")
            self._environment = self.ENVIRONMENT
            self._transactions.clear()

            # Production-only from 0.5.4 onward. Never reuse Sandbox credentials/tokens.
            if saved_environment and saved_environment != self.ENVIRONMENT:
                self._client_id = ""
                self._secret = ""
                self._access_token = ""
                self._item_id = ""
                self._cursor = None
                self._status = "Production Plaid credentials required · previous Sandbox session was not reused"
                return

            self._client_id = str(session.get("client_id") or "").strip()
            self._secret = str(session.get("secret") or "").strip()
            self._access_token = str(session.get("access_token") or "").strip()
            self._item_id = str(session.get("item_id") or "").strip()
            self._cursor = session.get("cursor")
            if self._access_token:
                self._status = "Connected from encrypted storage · ready to refresh & sync"
            elif self._client_id and self._secret:
                self._status = "Production API credentials restored · next: Connect bank"
            else:
                self._status = "Not configured"

    def clear_sensitive_session(self):
        with self._lock:
            self._client_id = ""
            self._secret = ""
            self._access_token = ""
            self._item_id = ""
            self._cursor = None
            self._transactions.clear()
            self._status = "Not configured"

    def configure(self, client_id: str, secret: str, environment: str | None = None):
        # Strip copied whitespace/newlines and always use Production.
        client_id = "".join(client_id.split())
        secret = "".join(secret.split())
        if not client_id or not secret:
            raise PlaidError("Plaid client ID and Production secret are required.")
        with self._lock:
            self._client_id = client_id
            self._secret = secret
            self._environment = self.ENVIRONMENT
            self._access_token = ""
            self._item_id = ""
            self._cursor = None
            self._transactions.clear()
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
            self._link_sessions[nonce] = (link_token, datetime.now(timezone.utc).timestamp())
            self._status = "Waiting for bank connection in Plaid Link"
        return nonce

    def link_token_for(self, nonce: str) -> str | None:
        with self._lock:
            row = self._link_sessions.get(nonce)
            return row[0] if row else None

    def exchange_and_sync(self, nonce: str, public_token: str) -> dict:
        with self._lock:
            if nonce not in self._link_sessions:
                raise PlaidError("This Plaid Link session is no longer valid.")
            self._status = "Exchanging Plaid token"
        exchanged = self._request("/item/public_token/exchange", {"public_token": public_token})
        access_token = exchanged.get("access_token")
        item_id = exchanged.get("item_id")
        if not access_token or not item_id:
            raise PlaidError("Plaid token exchange did not return an Item.")
        with self._lock:
            self._access_token = access_token
            self._item_id = item_id
            self._cursor = None
            self._transactions.clear()
            self._link_sessions.pop(nonce, None)
            self._status = "Connected · loading accounts and transactions"
        self.sync()
        return {"ok": True, "item_connected": True, "source": "plaid"}

    def refresh_and_sync(self) -> dict:
        """Request fresh Plaid data when the optional refresh product is available.

        If Transactions Refresh is not enabled for the Plaid account or Item,
        fall back to syncing Plaid's latest cached transaction state.
        """
        with self._lock:
            access_token = self._access_token
        if not access_token:
            raise PlaidError("No Plaid Item is connected in this session.")

        try:
            with self._lock:
                self._status = "Requesting an on-demand bank refresh from Plaid…"
            self._request("/transactions/refresh", {"access_token": access_token}, timeout=75)
            with self._lock:
                self._status = "Bank refresh completed · syncing transaction changes…"
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
            with self._lock:
                self._status = "On-demand refresh unavailable · syncing Plaid's latest available data…"

        return self.sync()

    def sync(self) -> dict:
        with self._lock:
            access_token = self._access_token
            cursor = self._cursor
        if not access_token:
            raise PlaidError("No Plaid Item is connected in this session.")

        accounts_payload = self._request("/accounts/get", {"access_token": access_token})
        accounts = [self._map_account(x) for x in accounts_payload.get("accounts", [])]
        account_names = {x.get("account_id"): x.get("name") or "Account" for x in accounts_payload.get("accounts", [])}

        original_cursor = cursor
        working_cursor = cursor
        while True:
            body = {"access_token": access_token, "count": 500}
            if working_cursor:
                body["cursor"] = working_cursor
            try:
                page = self._request("/transactions/sync", body)
            except PlaidError:
                if original_cursor and working_cursor != original_cursor:
                    working_cursor = original_cursor
                    continue
                raise
            for tx in page.get("added", []):
                self._transactions[tx["transaction_id"]] = tx
            for tx in page.get("modified", []):
                self._transactions[tx["transaction_id"]] = tx
            for tx in page.get("removed", []):
                self._transactions.pop(tx.get("transaction_id"), None)
            working_cursor = page.get("next_cursor") or working_cursor
            if not page.get("has_more"):
                break

        mapped_transactions = [self._map_transaction(x, account_names) for x in self._transactions.values()]
        self.state.replace_with_plaid(accounts, mapped_transactions)
        with self._lock:
            self._cursor = working_cursor
            self._status = f"Connected · {len(accounts)} accounts · {len(mapped_transactions)} transactions"
        return {"accounts": len(accounts), "transactions": len(mapped_transactions)}

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
                code = body.get("error_code") or body.get("error_type") or f"HTTP {exc.code}"
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
                raise PlaidError(f"Plaid request failed with HTTP {exc.code}.") from None
        except urllib.error.URLError as exc:
            raise PlaidError(f"Could not reach Plaid: {exc.reason}") from None

    @staticmethod
    def _map_account(raw: dict) -> Account:
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
            institution="Plaid linked",
            current_balance=signed,
            available_balance=signed_available,
            mask=raw.get("mask"),
        )

    @staticmethod
    def _map_transaction(raw: dict, account_names: dict[str, str]) -> Transaction:
        posted_raw = raw.get("date") or raw.get("authorized_date") or date.today().isoformat()
        try:
            posted = date.fromisoformat(posted_raw)
        except ValueError:
            posted = date.today()
        pfc = raw.get("personal_finance_category") or {}
        category = pfc.get("primary") or "Other"
        category = str(category).replace("_", " ").title()
        merchant = raw.get("merchant_name") or raw.get("name") or "Transaction"
        # Plaid Transactions uses positive amounts for most outflows. PrivateMoney uses negative outflows.
        amount = -float(raw.get("amount") or 0.0)
        return Transaction(
            posted=posted,
            merchant=str(merchant),
            category=category,
            account=account_names.get(raw.get("account_id"), "Account"),
            amount=amount,
            pending=bool(raw.get("pending")),
            external_id=raw.get("transaction_id"),
        )
