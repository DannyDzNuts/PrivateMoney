from __future__ import annotations
import os
from collections import defaultdict
from datetime import date
from threading import RLock
from .models import Account, Transaction
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
            self._source = "plaid"
            self._accounts = list(accounts)
            self._transactions = sorted(transactions, key=lambda x: x.posted, reverse=True)
            self._recurring = []
            self._net_worth = [("Now", round(sum(a.current_balance for a in accounts), 2))]
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
