from __future__ import annotations
import os
import re
import uuid
from collections import defaultdict
from statistics import median
from datetime import date, timedelta
from threading import RLock
from .models import Account, Budget, Goal, RecurringCharge, Transaction
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
        self._goals = []
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
            self._goals = []
            self._recurring = []
            self._net_worth = []
            self._spending = []
            self._cashflow = []
            self._version += 1

    def accounts(self):
        with self._lock:
            return list(self._accounts)

    def account_display_name(self, account_name: str) -> str:
        with self._lock:
            for account in self._accounts:
                if account.name == account_name:
                    return (account.nickname or "").strip() or account.name
            return account_name

    def set_account_nickname(self, account_id: str, nickname: str):
        nickname = nickname.strip()
        with self._lock:
            for account in self._accounts:
                if account.id != account_id:
                    continue
                value = nickname or None
                if account.nickname == value:
                    return False
                account.nickname = value
                self._version += 1
                return True
        return False

    def transactions(self):
        with self._lock:
            return list(self._transactions)

    def budgets(self):
        with self._lock:
            today=date.today()
            for budget in self._budgets:
                budget.spent=round(sum(
                    -tx.amount for tx in self._transactions
                    if tx.amount < 0 and tx.category == budget.category
                    and tx.posted.year == today.year and tx.posted.month == today.month
                ),2)
            return list(self._budgets)

    def set_budget(self, category: str, limit: float):
        category=category.strip() or "Other"
        limit=max(0.0,float(limit))
        with self._lock:
            today=date.today()
            spent=sum(
                -tx.amount for tx in self._transactions
                if tx.amount < 0 and tx.category == category
                and tx.posted.year == today.year and tx.posted.month == today.month
            )
            for budget in self._budgets:
                if budget.category.casefold() == category.casefold():
                    budget.category=category
                    budget.spent=round(spent,2)
                    budget.limit=round(limit,2)
                    self._version += 1
                    return budget
            budget=Budget(category,round(spent,2),round(limit,2))
            self._budgets.append(budget)
            self._version += 1
            return budget

    def goals(self):
        with self._lock:
            return list(self._goals)

    def add_goal(self, goal: Goal):
        with self._lock:
            self._goals.append(goal)
            self._version += 1
            return goal

    def delete_goal(self, goal_id: str):
        with self._lock:
            before=len(self._goals)
            self._goals=[goal for goal in self._goals if goal.id != goal_id]
            if len(self._goals) != before:
                self._version += 1
                return True
            return False

    @staticmethod
    def _subtract_months(day: date, months: int) -> date:
        month=day.month-1-int(months)
        year=day.year+month//12
        month=month%12+1
        lengths=(31,29 if year%4==0 and (year%100!=0 or year%400==0) else 28,31,30,31,30,31,31,30,31,30,31)
        return date(year,month,min(day.day,lengths[month-1]))

    def goal_status(self, goal: Goal):
        today=date.today()
        count=max(1,int(goal.period_count or 1))
        if goal.period_unit == "day":
            start=today-timedelta(days=count-1)
        elif goal.period_unit == "week":
            start=today-timedelta(days=7*count-1)
        elif goal.period_unit == "year":
            try:
                start=today.replace(year=today.year-count)
            except ValueError:
                start=today.replace(year=today.year-count,day=28)
        else:
            start=self._subtract_months(today,count)

        value_key=goal.scope_value.casefold()
        with self._lock:
            accounts={a.name:((a.nickname or "").strip() or a.name) for a in self._accounts}
            rows=[]
            for tx in self._transactions:
                if tx.posted < start or tx.posted > today or tx.pending:
                    continue
                if goal.direction == "spent" and tx.amount >= 0:
                    continue
                if goal.direction == "received" and tx.amount <= 0:
                    continue
                if goal.scope_type == "merchant":
                    matches=tx.merchant.casefold() == value_key
                elif goal.scope_type == "category":
                    matches=tx.category.casefold() == value_key
                else:
                    display=accounts.get(tx.account,tx.account)
                    matches=tx.account.casefold() == value_key or display.casefold() == value_key
                if matches:
                    rows.append(tx)

        actual=round(sum((-tx.amount if goal.direction=="spent" else tx.amount) for tx in rows),2)
        target=round(float(goal.target),2)
        if goal.operator == "less than":
            met=actual < target
        elif goal.operator == "greater than":
            met=actual > target
        else:
            met=round(actual,2) == round(target,2)
        return {
            "actual":actual,
            "target":target,
            "met":met,
            "start":start,
            "end":today,
            "transaction_count":len(rows),
        }

    def recurring(self):
        with self._lock:
            return list(self._recurring)

    def recurring_details(self):
        with self._lock:
            transactions=list(self._transactions)
            charges=list(self._recurring)

        groups=defaultdict(list)
        for tx in transactions:
            if tx.pending or tx.amount == 0:
                continue
            direction="income" if tx.amount > 0 else "spending"
            key=self._recurring_merchant_key(tx.merchant)
            if key:
                groups[(direction,key)].append(tx)

        details=[]
        today=date.today()
        for charge in charges:
            key=self._recurring_merchant_key(charge.merchant)
            rows=sorted(groups.get((charge.direction,key),[]),key=lambda tx:tx.posted)
            if rows:
                first_seen=rows[0].posted
                total_amount=round(sum(abs(tx.amount) for tx in rows),2)
                occurrences=len(rows)
            else:
                first_seen=charge.next_date
                total_amount=round(charge.amount,2)
                occurrences=1
            cadence_days={
                "Weekly":7,
                "Every 2 weeks":14,
                "Monthly":30,
                "Quarterly":91,
                "Yearly":365,
            }.get(charge.cadence,9999)
            details.append({
                "charge":charge,
                "first_seen":first_seen,
                "age_days":max(0,(today-first_seen).days),
                "total_spent":total_amount,
                "total_amount":total_amount,
                "occurrences":occurrences,
                "frequency_days":cadence_days,
            })
        return details

    def net_worth(self):
        with self._lock:
            return self._derive_net_worth(self._accounts, self._transactions)

    def spending(self):
        with self._lock:
            return list(self._spending)

    def spending_last_month(self):
        with self._lock:
            today = date.today()
            year = today.year if today.month > 1 else today.year - 1
            month = today.month - 1 if today.month > 1 else 12
            return self._derive_spending_for_month(self._transactions, year, month)

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
            previous_year = today.year if today.month > 1 else today.year - 1
            previous_month = today.month - 1 if today.month > 1 else 12
            previous_month_spending = sum(
                -t.amount for t in txs
                if t.amount < 0
                and t.posted.year == previous_year
                and t.posted.month == previous_month
            )
            spending_variance = month_spend - previous_month_spending
            upcoming = sum(r.amount for r in self._recurring if r.direction == "spending")
            return {
                "source": self._source,
                "net_worth": round(net, 2),
                "cash_available": round(cash, 2),
                "month_spending": round(month_spend, 2),
                "month_income": round(month_income, 2),
                "previous_month_spending": round(previous_month_spending, 2),
                "spending_variance": round(spending_variance, 2),
                "upcoming_recurring": round(upcoming, 2),
                "recurring_count": len(self._recurring),
                "account_count": len(self._accounts),
                "transaction_count": len(txs),
            }

    DEFAULT_CATEGORIES = (
        "Bills", "Dining", "Entertainment", "Groceries", "Healthcare",
        "Income", "Other", "Shopping", "Subscriptions", "Transfer",
        "Transportation", "Travel",
    )

    def categories(self):
        with self._lock:
            values = set(self.DEFAULT_CATEGORIES)
            values.update(t.category for t in self._transactions if t.category)
            return sorted(values, key=str.casefold)

    def transactions_for_category(self, category: str | None):
        with self._lock:
            if not category:
                return list(self._transactions)
            return [t for t in self._transactions if t.category == category]

    def bulk_set_merchant_category(self, merchant: str, category: str):
        merchant_key = merchant.strip().casefold()
        category = category.strip() or "Other"
        if not merchant_key:
            return 0
        with self._lock:
            changed = 0
            for tx in self._transactions:
                if tx.merchant.strip().casefold() != merchant_key:
                    continue
                if tx.category == category:
                    continue
                tx.category = category
                changed += 1
            if changed:
                self._spending = self._derive_spending(self._transactions)
                self._recurring = self._derive_recurring(self._transactions)
                self._version += 1
            return changed

    def set_transaction_category(self, transaction: Transaction, category: str):
        category = category.strip() or "Other"
        with self._lock:
            target = None
            for tx in self._transactions:
                if tx is transaction:
                    target = tx
                    break
                if transaction.external_id and tx.external_id == transaction.external_id:
                    target = tx
                    break
            if target is None or target.category == category:
                return False
            target.category = category
            self._spending = self._derive_spending(self._transactions)
            self._recurring = self._derive_recurring(self._transactions)
            self._version += 1
            return True

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
            self._recurring = self._derive_recurring(self._transactions)
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
            self._goals = list(snapshot.get("goals") or [])
            saved_recurring = list(snapshot.get("recurring") or [])
            self._recurring = (
                self._derive_recurring(self._transactions)
                if self._transactions
                else saved_recurring
            )
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

            existing_categories = {
                t.external_id: t.category
                for t in self._transactions
                if t.external_id and t.category
            }
            existing_nicknames = {
                a.id: a.nickname
                for a in self._accounts
                if a.nickname
            }

            account_map = {a.id: a for a in local_accounts}
            for account in accounts:
                if account.id in existing_nicknames:
                    account.nickname = existing_nicknames[account.id]
                account_map[account.id] = account

            tx_map = {}
            for tx in local_transactions:
                key = tx.external_id or (
                    f"local:{tx.posted}:{tx.merchant}:{tx.amount}:{tx.account}"
                )
                tx_map[key] = tx
            for tx in transactions:
                if tx.external_id and tx.external_id in existing_categories:
                    tx.category = existing_categories[tx.external_id]
                key = tx.external_id or (
                    f"plaid:{tx.posted}:{tx.merchant}:{tx.amount}:{tx.account}"
                )
                tx_map[key] = tx

            self._source = "plaid"
            self._accounts = list(account_map.values())
            self._transactions = sorted(
                tx_map.values(), key=lambda x: x.posted, reverse=True
            )
            self._recurring = self._derive_recurring(self._transactions)
            self._net_worth = [(
                "Now",
                round(sum(a.current_balance for a in self._accounts), 2),
            )]
            self._spending = self._derive_spending(self._transactions)
            self._cashflow = self._derive_cashflow(self._transactions)
            self._version += 1

    @staticmethod
    def _derive_net_worth(accounts: list[Account], transactions: list[Transaction]):
        if not accounts:
            return []

        current = round(sum(a.current_balance for a in accounts), 2)
        if not transactions:
            return [(date.today().isoformat(), current)]

        changes = defaultdict(float)
        for tx in transactions:
            changes[tx.posted] += tx.amount

        working = current
        by_date = {}
        for posted in sorted(changes, reverse=True):
            by_date[posted] = round(working, 2)
            working -= changes[posted]

        return [
            (posted.isoformat(), by_date[posted])
            for posted in sorted(by_date)
        ]

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
    def _derive_spending_for_month(
        transactions: list[Transaction],
        year: int,
        month: int,
    ):
        totals = defaultdict(float)
        for tx in transactions:
            if (
                tx.amount < 0
                and tx.posted.year == year
                and tx.posted.month == month
            ):
                totals[tx.category or "Other"] += -tx.amount
        return sorted(
            ((category, round(value, 2)) for category, value in totals.items()),
            key=lambda item: item[1],
            reverse=True,
        )[:8]

    @staticmethod
    def _recurring_merchant_key(value: str) -> str:
        text = value.casefold()
        text = re.sub(
            r"\b(pos|purchase|debit|card|payment|pmt|online|ach|recurring)\b",
            " ",
            text,
        )
        text = re.sub(r"\b\d{4,}\b", " ", text)
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return " ".join(text.split())

    @classmethod
    def _derive_recurring(cls, transactions: list[Transaction]):
        groups = defaultdict(list)
        for tx in transactions:
            if tx.pending or tx.amount == 0:
                continue
            key = cls._recurring_merchant_key(tx.merchant)
            if not key:
                continue
            direction = "income" if tx.amount > 0 else "spending"
            groups[(direction,key)].append(tx)

        patterns = []
        cadence_rules = (
            ("Weekly", 7, 5, 9, 4, 2),
            ("Every 2 weeks", 14, 11, 17, 4, 3),
            ("Monthly", 30, 25, 35, 3, 5),
            ("Quarterly", 91, 75, 105, 3, 12),
            ("Yearly", 365, 330, 400, 2, 25),
        )

        for (direction,_), rows in groups.items():
            rows = sorted(rows, key=lambda tx: tx.posted)
            unique_dates = []
            for tx in rows:
                if not unique_dates or unique_dates[-1].posted != tx.posted:
                    unique_dates.append(tx)
            if len(unique_dates) < 2:
                continue

            intervals = [
                (right.posted - left.posted).days
                for left, right in zip(unique_dates, unique_dates[1:])
                if right.posted > left.posted
            ]
            if not intervals:
                continue

            typical_gap = median(intervals)
            cadence = None
            cadence_days = None
            tolerance = None
            minimum_occurrences = None
            for label, expected, low, high, minimum, allowed_error in cadence_rules:
                if low <= typical_gap <= high:
                    cadence = label
                    cadence_days = int(round(typical_gap or expected))
                    tolerance = allowed_error
                    minimum_occurrences = minimum
                    break
            if cadence is None or len(unique_dates) < minimum_occurrences:
                continue

            if max(abs(gap - typical_gap) for gap in intervals) > tolerance:
                continue

            charges = [abs(tx.amount) for tx in unique_dates[-6:]]
            typical_amount = float(median(charges))
            if typical_amount <= 0:
                continue

            max_deviation = max(abs(amount - typical_amount) for amount in charges)
            allowed_amount_deviation = max(5.0, typical_amount * 0.35)
            if max_deviation > allowed_amount_deviation and cadence in {"Weekly","Every 2 weeks"}:
                continue

            latest = unique_dates[-1]
            next_date = latest.posted + timedelta(days=cadence_days)
            while next_date < date.today():
                next_date += timedelta(days=cadence_days)

            patterns.append(
                RecurringCharge(
                    merchant=latest.merchant,
                    amount=round(typical_amount, 2),
                    cadence=cadence,
                    next_date=next_date,
                    category=latest.category or "Other",
                    direction=direction,
                )
            )

        return sorted(patterns, key=lambda charge: charge.next_date)

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
