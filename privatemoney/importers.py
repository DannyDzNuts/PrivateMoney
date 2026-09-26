from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(slots=True)
class ImportedTransaction:
    posted: date
    merchant: str
    amount_cents: int
    fingerprint: str
    source: str = "csv"
    source_id: str | None = None
    account_hint: str | None = None
    balance_cents: int | None = None


DATE_CANDIDATES = (
    "date", "posted date", "post date", "transaction date", "posting date",
)
DESCRIPTION_CANDIDATES = (
    "description", "merchant", "name", "payee", "memo", "details",
)
AMOUNT_CANDIDATES = (
    "amount", "transaction amount", "value", "debit/credit",
)
DEBIT_CANDIDATES = (
    "debit", "withdrawal", "withdrawals", "charge", "charges", "money out",
)
CREDIT_CANDIDATES = (
    "credit", "deposit", "deposits", "money in",
)
ACCOUNT_CANDIDATES = (
    "account", "account number", "acct", "acct number",
)
BALANCE_CANDIDATES = (
    "balance", "running balance", "current balance",
)


def read_csv_headers(path: str | Path) -> list[str]:
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            return [str(x).strip() for x in next(reader)]
        except StopIteration:
            return []


def csv_header_signature(headers: list[str]) -> str:
    normalized = sorted(h.strip().casefold() for h in headers if h.strip())
    return hashlib.sha256("\x1f".join(normalized).encode("utf-8")).hexdigest()


def guess_column(headers: list[str], candidates: tuple[str, ...]) -> str | None:
    normalized = {header.strip().casefold(): header for header in headers}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    for header in headers:
        lowered = header.strip().casefold()
        if any(candidate in lowered for candidate in candidates):
            return header
    return None


def parse_date(value: str) -> date:
    raw = value.strip()
    if not raw:
        raise ValueError("empty date")
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        pass
    for fmt in (
        "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y",
        "%Y/%m/%d", "%b %d, %Y", "%B %d, %Y", "%d %b %Y",
    ):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date: {value}")


def parse_amount(value: str) -> int:
    raw = value.strip()
    if not raw:
        raise ValueError("empty amount")
    negative_parentheses = raw.startswith("(") and raw.endswith(")")
    if negative_parentheses:
        raw = raw[1:-1]
    raw = (
        raw.replace("$", "")
        .replace(",", "")
        .replace("USD", "")
        .replace("usd", "")
        .strip()
    )
    if not raw:
        raise ValueError("empty amount")
    cents = int(round(float(raw) * 100))
    if negative_parentheses:
        cents = -abs(cents)
    return cents


def parse_optional_amount(value: str) -> int | None:
    raw = (value or "").strip()
    if not raw:
        return None
    return parse_amount(raw)


def transaction_fingerprint(posted: date, merchant: str, amount_cents: int) -> str:
    payload = f"{posted.isoformat()}|{merchant.strip().casefold()}|{amount_cents}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def external_id_for(account_name: str, imported: ImportedTransaction) -> str:
    identity = imported.source_id or imported.fingerprint
    payload = f"{account_name.strip().casefold()}|{imported.source}|{identity}".encode("utf-8")
    return f"{imported.source}:" + hashlib.sha256(payload).hexdigest()


def parse_csv(
    path: str | Path,
    *,
    date_col: str,
    description_col: str,
    amount_mode: str = "single",
    amount_col: str | None = None,
    debit_col: str | None = None,
    credit_col: str | None = None,
    account_col: str | None = None,
    balance_col: str | None = None,
    invert_amounts: bool = False,
) -> tuple[list[ImportedTransaction], int]:
    """Parse a user-mapped CSV with either one Amount or separate Debit/Credit columns."""
    if amount_mode not in {"single", "split"}:
        raise ValueError("Unknown amount format.")
    if not date_col or not description_col:
        raise ValueError("Date and Description must be mapped.")
    if amount_mode == "single" and not amount_col:
        raise ValueError("Choose an Amount column.")
    if amount_mode == "split" and not (debit_col or credit_col):
        raise ValueError("Choose at least a Debit or Credit column.")

    out: list[ImportedTransaction] = []
    skipped = 0

    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        mapped = [date_col, description_col, amount_col, debit_col, credit_col, account_col, balance_col]
        required = {x for x in mapped if x}
        if not required.issubset(set(fieldnames)):
            missing = ", ".join(sorted(required - set(fieldnames)))
            raise ValueError(f"CSV is missing mapped columns: {missing}")

        for row in reader:
            try:
                posted = parse_date(str(row.get(date_col) or ""))
                merchant = str(row.get(description_col) or "").strip()
                if not merchant:
                    raise ValueError("empty description")

                if amount_mode == "single":
                    amount_cents = parse_amount(str(row.get(amount_col) or ""))
                    if invert_amounts:
                        amount_cents *= -1
                else:
                    debit = parse_optional_amount(str(row.get(debit_col) or "")) if debit_col else None
                    credit = parse_optional_amount(str(row.get(credit_col) or "")) if credit_col else None
                    if debit is None and credit is None:
                        raise ValueError("empty debit and credit")
                    # Bank exports commonly store both as positive magnitudes.
                    amount_cents = (abs(credit) if credit is not None else 0) - (
                        abs(debit) if debit is not None else 0
                    )

                account_hint = str(row.get(account_col) or "").strip() if account_col else None
                balance_cents = (
                    parse_optional_amount(str(row.get(balance_col) or ""))
                    if balance_col else None
                )
                fingerprint = transaction_fingerprint(posted, merchant, amount_cents)
                out.append(
                    ImportedTransaction(
                        posted=posted,
                        merchant=merchant,
                        amount_cents=amount_cents,
                        fingerprint=fingerprint,
                        account_hint=account_hint or None,
                        balance_cents=balance_cents,
                    )
                )
            except (TypeError, ValueError):
                skipped += 1

    return out, skipped


def parse_ofx(path: str | Path) -> tuple[list[ImportedTransaction], int]:
    try:
        from ofxparse import OfxParser
    except Exception as exc:
        raise RuntimeError("OFX/QFX support is not installed.") from exc

    out: list[ImportedTransaction] = []
    skipped = 0
    try:
        with open(path, "rb") as handle:
            ofx = OfxParser.parse(handle)
    except Exception as exc:
        raise ValueError(f"Could not read this OFX/QFX statement: {exc}") from exc

    for account in getattr(ofx, "accounts", []) or []:
        statement = getattr(account, "statement", None)
        transactions = getattr(statement, "transactions", []) if statement else []
        for tx in transactions or []:
            try:
                raw_date = getattr(tx, "date", None)
                if raw_date is None:
                    raise ValueError("missing date")
                posted = raw_date.date() if hasattr(raw_date, "date") else raw_date
                if not isinstance(posted, date):
                    raise ValueError("invalid date")
                merchant = (
                    str(getattr(tx, "payee", "") or "").strip()
                    or str(getattr(tx, "memo", "") or "").strip()
                    or str(getattr(tx, "type", "") or "").strip()
                    or "Transaction"
                )
                amount_cents = int(round(float(getattr(tx, "amount")) * 100))
                source_id = str(getattr(tx, "id", "") or "").strip() or None
                fingerprint = transaction_fingerprint(posted, merchant, amount_cents)
                out.append(
                    ImportedTransaction(
                        posted=posted,
                        merchant=merchant,
                        amount_cents=amount_cents,
                        fingerprint=fingerprint,
                        source="ofx",
                        source_id=source_id,
                    )
                )
            except (TypeError, ValueError, AttributeError):
                skipped += 1
    return out, skipped


def parse_simple_csv(path: str | Path, date_col="date", description_col="description", amount_col="amount"):
    rows, _ = parse_csv(
        path,
        date_col=date_col,
        description_col=description_col,
        amount_mode="single",
        amount_col=amount_col,
    )
    return rows
