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


DATE_CANDIDATES = (
    "date",
    "posted date",
    "post date",
    "transaction date",
    "posting date",
)
DESCRIPTION_CANDIDATES = (
    "description",
    "merchant",
    "name",
    "payee",
    "memo",
    "details",
)
AMOUNT_CANDIDATES = (
    "amount",
    "transaction amount",
    "value",
    "debit/credit",
)


def read_csv_headers(path: str | Path) -> list[str]:
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            return [str(x).strip() for x in next(reader)]
        except StopIteration:
            return []


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
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m-%d-%Y",
        "%m-%d-%y",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
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


def transaction_fingerprint(posted: date, merchant: str, amount_cents: int) -> str:
    payload = (
        f"{posted.isoformat()}|{merchant.strip().casefold()}|{amount_cents}"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def external_id_for(account_name: str, imported: ImportedTransaction) -> str:
    identity = imported.source_id or imported.fingerprint
    payload = (
        f"{account_name.strip().casefold()}|{imported.source}|{identity}"
    ).encode("utf-8")
    return f"{imported.source}:" + hashlib.sha256(payload).hexdigest()


def parse_csv(
    path: str | Path,
    *,
    date_col: str,
    description_col: str,
    amount_col: str,
    invert_amounts: bool = False,
) -> tuple[list[ImportedTransaction], int]:
    """Parse a mapped CSV.

    Returns (transactions, skipped_rows). Invalid or incomplete rows are skipped so
    the preview can show the user exactly what will be imported.
    """
    out: list[ImportedTransaction] = []
    skipped = 0

    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        required = {date_col, description_col, amount_col}
        if not required.issubset(set(fieldnames)):
            missing = ", ".join(sorted(required - set(fieldnames)))
            raise ValueError(f"CSV is missing mapped columns: {missing}")

        for row in reader:
            try:
                posted = parse_date(str(row.get(date_col) or ""))
                merchant = str(row.get(description_col) or "").strip()
                if not merchant:
                    raise ValueError("empty description")
                amount_cents = parse_amount(str(row.get(amount_col) or ""))
                if invert_amounts:
                    amount_cents *= -1
                fingerprint = transaction_fingerprint(posted, merchant, amount_cents)
                out.append(
                    ImportedTransaction(
                        posted=posted,
                        merchant=merchant,
                        amount_cents=amount_cents,
                        fingerprint=fingerprint,
                    )
                )
            except (TypeError, ValueError):
                skipped += 1

    return out, skipped


def parse_ofx(path: str | Path) -> tuple[list[ImportedTransaction], int]:
    """Parse OFX/QFX statements into the same normalized import rows as CSV."""
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


# Backward-compatible helper for older callers/tests.
def parse_simple_csv(
    path: str | Path,
    date_col: str = "date",
    description_col: str = "description",
    amount_col: str = "amount",
):
    rows, _ = parse_csv(
        path,
        date_col=date_col,
        description_col=description_col,
        amount_col=amount_col,
    )
    return rows
