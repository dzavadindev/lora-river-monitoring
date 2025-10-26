# data_table.py
from __future__ import annotations
from typing import Any, Dict, Optional, Iterable, List, Tuple
import threading, json
import pandas as pd
from csv_store import append_row_csv

# ----------------- globals / schema -----------------
_df: Optional[pd.DataFrame] = None
_lock = threading.Lock()
_max_rows = 5000

# NEW canonical schema (renamed columns)
COLUMNS = [
    "ts",
    "device_id",
    "water_temp_c",
    "water_level_mm",
    "flow_deg",
    "latitude",
    "longitude",
]

VERBOSE_LOG = True  # flip to False to silence prints

def _log(*args):
    if VERBOSE_LOG:
        print(*args, flush=True)

def _preview_bytes(b, limit=2000):
    try:
        s = b.decode("utf-8", "replace")
    except Exception:
        s = str(b)
    if len(s) > limit:
        s = s[:limit] + f"... <+{len(s)-limit} chars>"
    return s


# ----------------- helpers -----------------
def _get(d: Dict, path: str, default=None):
    cur = d
    for key in path.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur

def _fill_row(row: dict) -> dict:
    """Ensure the dict has exactly the expected columns."""
    return {k: row.get(k, None) for k in COLUMNS}

def _coerce_ts(ts: Any) -> pd.Timestamp:
    if ts is None:
        return pd.Timestamp.now(tz="UTC")
    if isinstance(ts, (float, int)):
        return pd.to_datetime(ts, unit="s", utc=True)
    out = pd.to_datetime(ts, utc=True, errors="coerce")
    return out if pd.notna(out) else pd.Timestamp.now(tz="UTC")

def _first(*vals):
    for v in vals:
        if v is not None:
            return v
    return None

def _root(msg: dict) -> dict:
    """
    Return the object that contains 'uplink_message' and 'end_device_ids'.
    Supports both:
      - inner: { "uplink_message": ..., "end_device_ids": ... }
      - outer: { "data": { "uplink_message": ..., "end_device_ids": ... }, ... }
    """
    if not isinstance(msg, dict):
        return {}
    if "uplink_message" in msg and "end_device_ids" in msg:
        return msg  # inner ApplicationUp
    data = msg.get("data")
    if isinstance(data, dict) and "uplink_message" in data:
        return data  # outer envelope
    return msg  # fallback

def _extract_latlon(msg: dict) -> tuple[Optional[float], Optional[float]]:
    r = _root(msg)
    # locations block (TTN may place GPS here)
    locs = r.get("uplink_message", {}).get("locations", {}) or {}
    fp = locs.get("frm-payload")
    if isinstance(fp, dict):
        lat = fp.get("latitude"); lon = fp.get("longitude")
        try:
            if lat is not None and lon is not None:
                return float(lat), float(lon)
        except Exception:
            pass
    # fallback to decoded_payload variants
    dp = r.get("uplink_message", {}).get("decoded_payload", {}) or {}
    lat = _first(dp.get("latitude"), dp.get("lat"))
    lon = _first(dp.get("longitude"), dp.get("lon"))
    try:
        if lat is not None and lon is not None:
            return float(lat), float(lon)
    except Exception:
        pass
    return None, None

def _normalize_row(msg: dict) -> dict:
    """Return normalized fields (new schema), robust to inner/outer TTN shapes + old/new key names."""
    r = _root(msg)

    # Timestamp preference
    ts_pref = _first(
        r.get("uplink_message", {}).get("received_at"),
        
    )
    ts = _coerce_ts(ts_pref)

    # Device id
    device_id = _first(
        r.get("end_device_ids", {}).get("device_id"),
        _get(msg, "identifiers.0.device_ids.device_id"),
    )


    dp = r.get("uplink_message", {}).get("decoded_payload", {}) or {}

    # temperature (°C)
    water_temp_c = _first(
        dp.get("water_temp_c"),
        dp.get("temp_c"),
        dp.get("temperature_c"),
    )


    water_level_mm = _first(
        dp.get("water_level_mm"),
        dp.get("water_mm"),
    )
    water_m = _first(dp.get("water_m"), dp.get("level_m"))
    if water_level_mm is None and isinstance(water_m, (int, float)):
        water_level_mm = water_m * 1000.0

    # direction in degrees
    flow_deg = _first(
        dp.get("flow_deg"),
        dp.get("direction_deg"),
        dp.get("flow"),
    )

    # location
    latitude, longitude = _extract_latlon(msg)

    return {
        "ts": ts,
        "device_id": device_id,
        "water_temp_c": water_temp_c,
        "water_level_mm": water_level_mm,
        "flow_deg": flow_deg,
        "latitude": latitude,
        "longitude": longitude,
    }

# ----------------- core table API -----------------
def init_table(max_rows: int = 5000) -> None:
    global _df, _max_rows
    with _lock:
        _max_rows = int(max_rows)
        if _df is None:
            _df = pd.DataFrame(columns=COLUMNS)
            _df["ts"] = pd.to_datetime(_df["ts"], utc=True)

def _append_row(row: dict) -> None:
    """Internal: append a single row without using concat (avoids FutureWarning)."""
    global _df
    row = _fill_row(row)
    # ensure ts is Timestamp[UTC]
    if not isinstance(row["ts"], pd.Timestamp):
        row["ts"] = _coerce_ts(row["ts"])
    with _lock:
        if _df is None:
            init_table()
        _df.loc[len(_df)] = row
        if len(_df) > _max_rows:
            _df = _df.tail(_max_rows).reset_index(drop=True)

def add_ttn_message(msg: Any, ts: Any = None) -> None:
    """Append one TTN message (dict / JSON str / bytes). Optional ts overrides message ts."""
    # Decode payload to dict if needed
    if isinstance(msg, (bytes, bytearray)):
        try:
            msg = json.loads(msg.decode("utf-8", "ignore"))
        except Exception:
            row = _fill_row({
                "ts": _coerce_ts(ts),
                "device_id": None,
                "water_temp_c": None,
                "water_level_mm": None,
                "flow_deg": None,
                "latitude": None,
                "longitude": None,
            })
            _append_row(row)
            return
    elif isinstance(msg, str):
        try:
            msg = json.loads(msg)
        except Exception:
            row = _fill_row({
                "ts": _coerce_ts(ts),
                "device_id": None,
                "water_temp_c": None,
                "water_level_mm": None,
                "flow_deg": None,
                "latitude": None,
                "longitude": None,
            })
            _append_row(row)
            return

    # normalize and append
    row = _normalize_row(msg if isinstance(msg, dict) else {})
    if ts is not None:
        row["ts"] = _coerce_ts(ts)

    append_row_csv("./ttn_messages.csv", row)
    _append_row(row)



def add_many_ttn(msgs: Iterable[Any]) -> int:
    """Append many TTN messages efficiently with one concat (columns fixed)."""
    rows: List[Dict[str, Any]] = []
    for m in msgs:
        if isinstance(m, (bytes, bytearray)):
            try:
                m = json.loads(m.decode("utf-8", "ignore"))
            except Exception:
                continue
        elif isinstance(m, str):
            try:
                m = json.loads(m)
            except Exception:
                continue
        if isinstance(m, dict):
            rows.append(_fill_row(_normalize_row(m)))
    if not rows:
        return 0

    df_new = pd.DataFrame(rows, columns=COLUMNS)
    df_new["ts"] = pd.to_datetime(df_new["ts"], utc=True, errors="coerce")

    global _df
    with _lock:
        if _df is None:
            init_table()
        # concat with fixed columns (no warning)
        _df = pd.concat([_df, df_new], ignore_index=True)
        if len(_df) > _max_rows:
            _df = _df.tail(_max_rows).reset_index(drop=True)
    return len(df_new)

def get_table(copy: bool = True) -> pd.DataFrame:
    with _lock:
        if _df is None:
            init_table()
        return _df.copy() if copy else _df

def get_latest(n: int = 100) -> pd.DataFrame:
    with _lock:
        if _df is None:
            init_table()
        return _df.sort_values("ts", ascending=False).head(n).copy()

def get_between(start: Any, end: Any) -> pd.DataFrame:
    """Return rows where ts ∈ [start, end]. Accepts ISO strings or datetimes."""
    s = _coerce_ts(start); e = _coerce_ts(end)
    with _lock:
        if _df is None:
            init_table()
        mask = (_df["ts"] >= s) & (_df["ts"] <= e)
        return _df.loc[mask].sort_values("ts").copy()

def clear_table() -> None:
    global _df
    with _lock:
        if _df is None:
            init_table()
        else:
            _df = _df.iloc[0:0].copy()

# -------- optional persistence --------
def save_table(path: str) -> None:
    with _lock:
        if _df is None:
            return
        if path.lower().endswith(".parquet"):
            _df.to_parquet(path, index=False)
        else:
            _df.to_csv(path, index=False)

def add_normalized_many(rows: Iterable[dict]) -> int:
    """Append many already-normalized rows (keys match COLUMNS)."""
    global _df
    df_new = pd.DataFrame(rows, columns=COLUMNS)
    df_new["ts"] = pd.to_datetime(df_new["ts"], utc=True, errors="coerce")
    # numeric coercions for new schema
    for col in ["water_temp_c", "water_level_mm", "flow_deg", "latitude", "longitude"]:
        if col in df_new.columns:
            df_new[col] = pd.to_numeric(df_new[col], errors="coerce")
    with _lock:
        if _df is None:
            init_table()
        _df = pd.concat([_df, df_new], ignore_index=True)
        if len(_df) > _max_rows:
            _df = _df.tail(_max_rows).reset_index(drop=True)
    return len(df_new)

def load_table(path: str, max_rows: int = 5000) -> None:
    global _df, _max_rows
    with _lock:
        _max_rows = int(max_rows)
        if path.lower().endswith(".parquet"):
            _df = pd.read_parquet(path)
        else:
            _df = pd.read_csv(path)
        # enforce schema and dtypes
        for col in COLUMNS:
            if col not in _df.columns:
                _df[col] = None
        _df = _df[COLUMNS]
        _df["ts"] = pd.to_datetime(_df["ts"], utc=True, errors="coerce")
        if len(_df) > _max_rows:
            _df = _df.tail(_max_rows).reset_index(drop=True)
