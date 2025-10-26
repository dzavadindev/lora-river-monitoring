# csv_store.py
from __future__ import annotations
import os, csv
from typing import Dict, Any, Optional
import pandas as pd

# Canonical (new) schema
COLUMNS = [
    "ts",
    "device_id",
    "water_temp_c",
    "water_level_mm",
    "flow_deg",
    "latitude",
    "longitude",
]

def _ensure_iso_utc(ts: Any) -> str:
    t = pd.to_datetime(ts, utc=True, errors="coerce")
    if pd.isna(t):
        t = pd.Timestamp.utcnow().tz_localize("UTC")
    return t.isoformat()

def append_row_csv(path: str, row: Dict[str, Any]) -> None:
    """
    Append one normalized row to CSV. Writes header if file doesn't exist.
    `row` must contain keys = COLUMNS; ts can be Timestamp/str/float/epoch seconds.
    """
    write_header = not os.path.exists(path)
    r = dict(row)
    r["ts"] = _ensure_iso_utc(r.get("ts"))
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if write_header:
            w.writeheader()
        w.writerow({k: r.get(k, None) for k in COLUMNS})

def _coerce_and_align(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enforce schema order/dtypes and map legacy columns to the new schema.
    - temp_c           -> water_temp_c
    - water_mm         -> water_level_mm
    - direction_deg    -> flow_deg
    - lat/lon          -> latitude/longitude
    - water_m * 1000   -> water_level_mm (if water_mm missing)
    """
    # Add any missing new columns
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None

    # Map legacy columns if present
    if "temp_c" in df.columns and "water_temp_c" in df.columns:
        df["water_temp_c"] = df["water_temp_c"].fillna(df["temp_c"])

    if "water_mm" in df.columns and "water_level_mm" in df.columns:
        df["water_level_mm"] = df["water_level_mm"].fillna(df["water_mm"])

    if "direction_deg" in df.columns and "flow_deg" in df.columns:
        df["flow_deg"] = df["flow_deg"].fillna(df["direction_deg"])

    if "lat" in df.columns and "latitude" in df.columns:
        df["latitude"] = df["latitude"].fillna(df["lat"])
    if "lon" in df.columns and "longitude" in df.columns:
        df["longitude"] = df["longitude"].fillna(df["lon"])

    # If only meters exist, convert to mm
    if "water_m" in df.columns and df["water_level_mm"].isna().any():
        try:
            df["water_level_mm"] = df["water_level_mm"].astype(float)
        except Exception:
            pass
        df.loc[df["water_level_mm"].isna(), "water_level_mm"] = (
            pd.to_numeric(df.get("water_m"), errors="coerce") * 1000.0
        )

    # Dtypes
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    for col in ["water_temp_c", "water_level_mm", "flow_deg", "latitude", "longitude"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Final order
    return df[COLUMNS]

def load_csv(path: str, limit: Optional[int] = None) -> pd.DataFrame:
    """
    Load CSV into a DataFrame with correct dtypes (UTC ts, numerics as floats).
    Backward compatible with old schema.
    Returns empty DF if file absent.
    """
    if not os.path.exists(path):
        return pd.DataFrame(columns=COLUMNS)

    df = pd.read_csv(path)
    df = _coerce_and_align(df)

    if limit:
        df = df.tail(limit)
    return df
