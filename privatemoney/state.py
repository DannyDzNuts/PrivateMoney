from __future__ import annotations
import os
import uuid
from collections import defaultdict
from datetime import date
from threading import RLock
from .models import Account, Transaction
from .importers import external_id_for
from .sample_data import ACCOUNTS, BUDGETS, CASHFLOW, NET_WORTH, RECURRING, SPENDING, TRANSACTIONS


class FinanceState:
    def __init__(self):
        self._lock = RLock()
        self._version = 0
        self._source = "local"
        use_samples = os.environ.get("PRIVATE_MONEY_SAMPLE_DATA") == "1"
        self._accounts = list(ACCOUNTS) if use_samples else []
        self._transactions = list(TRANSACTIONS) if use_samples else []
        self._budgets = list(BUDGETS) if use_samples else []
        self._recurring = list(RECURRING) if use_samples else []
        self._net_worth = list(NET_WORTH) if use_samples else []
        self._spending = list(SPENDING) if use_samples else []
        self._cashflow = list(CASHFLOW) if use_samples else []

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    @property
    def source(self) -> str:
        with self._lock:
            return self._source

    def clear_runtime(self):
        with self._lock:
            self._source = "local"
            self._accounts = []
            self._transactions = []
            self._budgets = []
            self._recurring = []
            self._net_worth = []
            self._spending = []
            self._cashflow = []
            self._version += 1

    def accounts(self):
        with self._lock:
            return list(self._accounts)

    def transactions(self):
        with self._lock:
            return list(self._transactions)

    def budgets(self):
        with self._lock:
            return list(self._budgets)

    def recurring(self):
        with self._lock:
            return list(self._recurring)

    def net_worth(self):
        with self._lock:
            return list(self._net_worth)

    def spending(self):
        with self._lock:
            return list(self._spending)

    def cashflow(self):
        with self._lock:
            return list(self._cashflow)

    def summary(self) -> dict:
        with self._lock:
            net = sum(a.current_balance for a in self._accounts)
            cash = sum((a.available_balance if a.available_balance is not None else a.current_balance)
                       for a in self._accounts if a.kind in {"checking", "savings", "depository"})
            txs = list(self._transactions)
            today = date.today()
            month_spend = sum(-t.amount for t in txs if t.amount < 0 and t.posted.year == today.year and t.posted.month == today.month)
            month_income = sum(t.amount for t in txs if t.amount > 0 and t.posted.year == today.year and t.posted.month == today.month)
            upcoming = sum(r.amount for r in self._recurring)
            return {
                "source": self._source,
                "net_worth": round(net, 2),
                "cash_available": round(cash, 2),
                "month_spending": round(month_spend, 2),
                "month_income": round(month_income, 2),
                "upcoming_recurring": round(upcoming, 2),
                "account_count": len(self._accounts),
                "transaction_count": len(txs),
            }

    def import_transactions(self, account_name: str, rows, use_account_column: bool = False) -> dict:
        account_name = account_name.strip()
        if not account_name and not use_account_column:
            raise ValueError("Account name is required.")

        with self._lock:
            existing_ids = {t.external_id for t in self._transactions if t.external_id}
            accounts_by_name = {a.name.casefold(): a for a in self._accounts}
            latest_balances = {}
            imported = 0
            duplicates = 0
            created = 0

            for row in rows:
                target_name = (
                    (row.account_hint or "").strip()
                    if use_account_column
                    else account_name
                )
                if not target_name:
                    target_name = account_name
                if not target_name:
                    raise ValueError("One or more rows do not contain an account value.")

                key = target_name.casefold()
                account = accounts_by_name.get(key)
                if account is None:
                    account = Account(
                        id=f"local-{uuid.uuid4()}",
                        name=target_name,
                        kind="checking",
                        institution="Imported",
                        current_balance=0.0,
                        available_balance=None,
                        mask=None,
                    )
                    self._accounts.append(account)
                    accounts_by_name[key] = account
                    created += 1

                external_id = external_id_for(account.name, row)
                if external_id in existing_ids:
                    duplicates += 1
                else:
                    self._transactions.append(
                        Transaction(
                            posted=row.posted,
                            merchant=row.merchant,
                            category="Other",
                            account=account.name,
                            amount=round(row.amount_cents / 100.0, 2),
                            pending=False,
                            external_id=external_id,
                        )
                    )
                    existing_ids.add(external_id)
                    imported += 1

                if row.balance_cents is not None:
                    previous = latest_balances.get(key)
                    if previous is None or row.posted > previous[0]:
                        latest_balances[key] = (row.posted, row.balance_cents, account)

            for _, balance_cents, account in latest_balances.values():
                account.current_balance = round(balance_cents / 100.0, 2)

            self._transactions.sort(key=lambda x: x.posted, reverse=True)
            self._spending = self._derive_spending(self._transactions)
            self._cashflow = self._derive_cashflow(self._transactions)
            if not self._net_worth:
                self._net_worth = [(
                    "Now",
                    round(sum(a.current_balance for a in self._accounts), 2),
                )]
            elif latest_balances:
                self._net_worth = [(
                    "Now",
                    round(sum(a.current_balance for a in self._accounts), 2),
                )]

            if imported or created or latest_balances:
                self._version += 1
            return {
                "imported": imported,
                "duplicates": duplicates,
                "accounts_created": created,
            }

    def restore_snapshot(self, snapshot: dict):
        with self._lock:
            self._source = snapshot.get("source") or "local"
            self._accounts = list(snapshot.get("accounts") or [])
            self._transactions = sorted(
                list(snapshot.get("transactions") or []),
                key=lambda x: x.posted,
                reverse=True,
            )
            self._budgets = list(snapshot.get("budgets") or [])
            self._recurring = list(snapshot.get("recurring") or [])
            self._net_worth = list(snapshot.get("net_worth") or [])
            self._spending = self._derive_spending(self._transactions)
            self._cashflow = list(snapshot.get("cashflow") or [])
            if not self._cashflow and self._transactions:
                self._cashflow = self._derive_cashflow(self._transactions)
            self._version += 1

    def replace_with_plaid(self, accounts: list[Account], transactions: list[Transaction]):
        with self._lock:
            local_accounts = [
                a for a in self._accounts if str(a.id).startswith("local-")
            ]
            local_names = {a.name for a in local_accounts}
            local_transactions = [
                t for t in self._transactions
                if (
                    (t.external_id and str(t.external_id).startswith(("csv:", "ofx:")))
                    or t.account in local_names
                )
            ]

            account_map = {a.id: a for a in local_accounts}
            for account in accounts:
                account_map[account.id] = account

            tx_map = {}
            for tx in local_transactions:
                key = tx.external_id or (
                    f"local:{tx.posted}:{tx.merchant}:{tx.amount}:{tx.account}"
                )
                tx_map[key] = tx
            for tx in transactions:
                key = tx.external_id or (
                    f"plaid:{tx.posted}:{tx.merchant}:{tx.amount}:{tx.account}"
                )
                tx_map[key] = tx

            self._source = "plaid"
            self._accounts = list(account_map.values())
            self._transactions = sorted(
                tx_map.values(), key=lambda x: x.posted, reverse=True
            )
            self._recurring = []
            self._net_worth = [(
                "Now",
                round(sum(a.current_balance for a in self._accounts), 2),
            )]
            self._spending = self._derive_spending(self._transactions)
            self._cashflow = self._derive_cashflow(self._transactions)
            self._version += 1

    @staticmethod
    def _derive_spending(transactions: list[Transaction]):
        if not transactions:
            return []
        latest = max(t.posted for t in transactions)
        totals = defaultdict(float)
        for t in transactions:
            if t.amount < 0 and t.posted.year == latest.year and t.posted.month == latest.month:
                totals[t.category or "Other"] += -t.amount
        return sorted(((k, round(v, 2)) for k, v in totals.items()), key=lambda x: x[1], reverse=True)[:6]

    @staticmethod
    def _derive_cashflow(transactions: list[Transaction]):
        monthly = defaultdict(lambda: [0.0, 0.0])
        for t in transactions:
            key = (t.posted.year, t.posted.month)
            if t.amount >= 0:
                monthly[key][0] += t.amount
            else:
                monthly[key][1] += -t.amount
        keys = sorted(monthly)[-6:]
        return [(date(y, m, 1).strftime("%b"), round(monthly[(y,m)][0],2), round(monthly[(y,m)][1],2)) for y,m in keys]
