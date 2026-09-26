from __future__ import annotations
import csv
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

@dataclass(slots=True)
class ImportedTransaction:
    posted_date: str
    merchant: str
    amount_cents: int
    fingerprint: str


def parse_simple_csv(path: str | Path, date_col="date", description_col="description", amount_col="amount"):
    """Parse a simple CSV after the user maps columns. This does not persist anything."""
    out=[]
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader=csv.DictReader(f)
        for row in reader:
            raw_date=(row.get(date_col) or "").strip()
            merchant=(row.get(description_col) or "").strip()
            raw_amount=(row.get(amount_col) or "").strip().replace("$","").replace(",","")
            if not raw_date or not merchant or not raw_amount:
                continue
            dt=None
            for fmt in ("%Y-%m-%d","%m/%d/%Y","%m/%d/%y"):
                try:
                    dt=datetime.strptime(raw_date,fmt).date(); break
                except ValueError:
                    pass
            if dt is None:
                continue
            cents=round(float(raw_amount)*100)
            payload=f"{dt.isoformat()}|{merchant.lower()}|{cents}".encode()
            fp=hashlib.sha256(payload).hexdigest()
            out.append(ImportedTransaction(dt.isoformat(),merchant,cents,fp))
    return out
