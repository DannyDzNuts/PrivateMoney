from __future__ import annotations
from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class Account:
    id: str
    name: str
    kind: str
    institution: str
    current_balance: float
    available_balance: float | None = None
    mask: str | None = None
    nickname: str | None = None


@dataclass(slots=True)
class Transaction:
    posted: date
    merchant: str
    category: str
    account: str
    amount: float
    pending: bool = False
    external_id: str | None = None


@dataclass(slots=True)
class Budget:
    category: str
    spent: float
    limit: float


@dataclass(slots=True)
class Goal:
    id: str
    direction: str
    scope_type: str
    scope_value: str
    period_count: int
    period_unit: str
    operator: str
    target: float


@dataclass(slots=True)
class RecurringCharge:
    merchant: str
    amount: float
    cadence: str
    next_date: date
    category: str
    direction: str = "spending"
