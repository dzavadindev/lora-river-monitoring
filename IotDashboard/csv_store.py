# csv_store.py
from __future__ import annotations
import os, csv
from typing import Dict, Any, Optional, Iterable
import pandas as pd

COLUMNS = ["ts","device_id","temp_c","water_m","water_mm","direction_deg","lat","lon"]

def _ensure_iso_utc(ts: Any) -> str:
    t = pd.to_datetime(ts, utc=True, errors="coerce")
    if pd.isna(t): t = pd.Timestamp.utcnow().tz_localize("UTC")
    return t.isoformat()

def append_row_csv(path: str, row: Dict[str, Any]) -> None:
    """
    Append one normalized row to CSV. Writes header if file doesn't exist.
    `row` must contain keys = COLUMNS; ts can be Timestamp/str/float.
    """
    write_header = not os.path.exists(path)
    r = dict(row)
    r["ts"] = _ensure_iso_utc(r.get("ts"))
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if write_header:
            w.writeheader()
        w.writerow({k: r.get(k, None) for k in COLUMNS})

def load_csv(path: str, limit: Optional[int] = None) -> pd.DataFrame:
    """
    Load CSV into a DataFrame with correct dtypes (UTC ts, numerics as floats).
    Returns empty DF if file absent.
    """
    if not os.path.exists(path):
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path)
    # enforce schema order
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[COLUMNS]
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    for col in ["temp_c","water_m","water_mm","direction_deg","lat","lon"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if limit:
        df = df.tail(limit)
    return df
