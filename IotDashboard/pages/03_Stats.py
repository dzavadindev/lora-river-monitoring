# pages/03_Stats.py
import pandas as pd
import numpy as np
import streamlit as st
import altair as alt
from datetime import datetime, time as dtime
from streamlit_autorefresh import st_autorefresh
from data_table import get_table

# ---- Streamlit page ----
st.set_page_config(page_title="Device Statistics", layout="wide")
st.title("📊 Device statistics")

# Auto-refresh (optional)
interval = st.sidebar.slider("Refresh (ms)", 1000, 10000, 3000, 500)
st_autorefresh(interval=interval, key="stats-refresh")

# Altair safety: allow large dataframes
alt.data_transformers.disable_max_rows()

# === chart overlays ===
st.sidebar.markdown("### Chart overlays")
show_overall_series   = st.sidebar.checkbox("Show overall mean series (per timestamp)", value=True)
show_device_mean_line = st.sidebar.checkbox("Show per-device mean line (horizontal)", value=True)
show_combined_mean    = st.sidebar.checkbox("Show combined mean line (horizontal)", value=False)

# --- load + prepare data ---
df = get_table().copy()
if df.empty:
    st.info("No data yet.")
    st.stop()

# Map NEW schema -> convenience names used by plots
df["temp_c"]        = pd.to_numeric(df.get("water_temp_c"), errors="coerce")
df["water_mm"]      = pd.to_numeric(df.get("water_level_mm"), errors="coerce")
df["direction_deg"] = pd.to_numeric(df.get("flow_deg"), errors="coerce")
df["lat"]           = pd.to_numeric(df.get("latitude"), errors="coerce")
df["lon"]           = pd.to_numeric(df.get("longitude"), errors="coerce")

# timestamps (UTC -> local tz column)
df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
df = df.dropna(subset=["ts"])
df["ts_local"] = df["ts"].dt.tz_convert("Europe/Amsterdam")

# --- filters ---
min_t = df["ts_local"].min()
max_t = df["ts_local"].max()
if pd.isna(min_t) or pd.isna(max_t):
    st.info("No valid timestamps.")
    st.stop()

default_start = (max_t - pd.Timedelta(hours=6)).date()
default_end   = max_t.date()

st.sidebar.subheader("Filters")
res = st.sidebar.date_input(
    "Date range",
    value=(default_start, default_end),
    min_value=min_t.date(),
    max_value=max_t.date(),
    key="stats_date_range",
)
# Handle single date or range
if isinstance(res, tuple):
    start_date, end_date = res
else:
    start_date = end_date = res
if start_date > end_date:
    start_date, end_date = end_date, start_date

# Build local tz-aware bounds
local_tz = df["ts_local"].iloc[0].tz  # tzinfo
start_dt = pd.Timestamp(datetime.combine(start_date, dtime.min)).tz_localize(local_tz)
end_dt   = pd.Timestamp(datetime.combine(end_date, dtime.max)).tz_localize(local_tz)

sub = df[(df["ts_local"] >= start_dt) & (df["ts_local"] <= end_dt)].copy()
if sub.empty:
    st.warning("No data in selected date range.")
    st.stop()

# device select
sub["device_id"] = sub["device_id"].astype(str)
devices = sorted(sub["device_id"].dropna().unique().tolist())
picked = st.sidebar.multiselect("Devices", options=devices, default=devices)
if picked:
    sub = sub[sub["device_id"].isin(picked)]
if sub.empty:
    st.warning("No data for selected devices.")
    st.stop()

# quick counters (debug)
st.sidebar.caption(
    f"Rows: {len(sub)} • temp: {sub['temp_c'].notna().sum()} • "
    f"water_mm: {sub['water_mm'].notna().sum()} • dir: {sub['direction_deg'].notna().sum()}"
)

# --- resample options (codes + window delta) ---
FREQS = {
    "No aggregation (raw)": (None, "0min"),
    "5 min":  ("5min", "5min"),
    "15 min": ("15min","15min"),
    "30 min": ("30min","30min"),
    "1 hour": ("1h",   "1h"),
    "6 hours":("6h",   "6h"),
    "1 day":  ("1D",   "1D"),
}
# default to a finer view so lines appear
freq_label = st.sidebar.selectbox("Time aggregation", list(FREQS.keys()), index=1)  # "5 min"
resample_code, window_delta = FREQS[freq_label]

# Altair likes tz-naive timestamps
sub["ts_plot"] = sub["ts_local"].dt.tz_convert(local_tz).dt.tz_localize(None)

# --- helpers ---
def circular_mean_deg(series: pd.Series) -> float | None:
    vals = pd.to_numeric(series, errors="coerce").dropna().astype(float)
    if vals.empty:
        return None
    rad = np.deg2rad(vals.to_numpy())
    C = np.cos(rad).mean()
    S = np.sin(rad).mean()
    return float((np.degrees(np.arctan2(S, C)) + 360.0) % 360.0)

def summarize_numeric(s: pd.Series) -> dict:
    x = pd.to_numeric(s, errors="coerce").dropna()
    if x.empty:
        return {"mean": None, "min": None, "max": None, "count": 0}
    return {"mean": float(x.mean()), "min": float(x.min()), "max": float(x.max()), "count": int(x.size)}

# --- resample per device + overall mean ---
sub_idx = sub.set_index("ts_plot").sort_index()
agg_num = {"temp_c": "mean", "water_mm": "mean"}

if resample_code is None:
    # raw points, no resample
    per_dev = sub[["ts_plot","device_id","temp_c","water_mm","direction_deg"]].copy()
else:
    per_dev = (
        sub_idx.groupby("device_id")
               .resample(resample_code)
               .agg(agg_num | {"direction_deg": circular_mean_deg})
               .reset_index()
    )
    # If resample produced all-NaNs (very sparse), fall back to raw points
    if per_dev[["temp_c","water_mm","direction_deg"]].notna().sum().sum() == 0:
        per_dev = sub[["ts_plot","device_id","temp_c","water_mm","direction_deg"]].copy()

overall = (
    per_dev.groupby("ts_plot")
           .agg({
               "temp_c": "mean",
               "water_mm": "mean",
               "direction_deg": circular_mean_deg
           })
           .reset_index()
)
overall["device_id"] = "__MEAN__"

plot_df = pd.concat([per_dev, overall], ignore_index=True)

# --- summary cards (latest window) ---
idx_max = sub_idx.index.max()
if pd.isna(idx_max):
    latest_slice = sub_idx.iloc[0:0].reset_index()
else:
    latest_slice = sub_idx.loc[idx_max - pd.to_timedelta(window_delta):].reset_index()

t_stats  = summarize_numeric(latest_slice.get("temp_c", pd.Series(dtype=float)))
mm_stats = summarize_numeric(latest_slice.get("water_mm", pd.Series(dtype=float)))
dir_mean = circular_mean_deg(latest_slice.get("direction_deg", pd.Series(dtype=float)))

c1, c2, c3 = st.columns(3)
c1.metric("Temp mean (°C)", f"{t_stats['mean']:.2f}" if t_stats["mean"] is not None else "—",
          f"min {t_stats['min']:.2f} • max {t_stats['max']:.2f}" if t_stats["count"] else "")
c2.metric("Water mean (mm)", f"{mm_stats['mean']:.0f}" if mm_stats["mean"] is not None else "—",
          f"min {mm_stats['min']:.0f} • max {mm_stats['max']:.0f}" if mm_stats["count"] else "")
c3.metric("Direction mean (°)", f"{dir_mean:.1f}" if dir_mean is not None else "—")

st.markdown("---")

def make_line_chart(field: str, title: str, y_format: str = ""):
    dfp = plot_df[["ts_plot","device_id",field]].dropna().copy()

    # include/exclude the overall time-varying mean series
    if not show_overall_series:
        dfp = dfp[dfp["device_id"] != "__MEAN__"]
    else:
        # pretty legend label for overall series
        dfp.loc[dfp["device_id"] == "__MEAN__", "device_id"] = "All devices (mean)"

    if dfp.empty:
        st.info(f"No data for {title.lower()}.")
        return

    x_min = dfp["ts_plot"].min()
    x_max = dfp["ts_plot"].max()

    base = (
        alt.Chart(dfp)
        .encode(
            x=alt.X("ts_plot:T", title="Time"),
            y=alt.Y(f"{field}:Q", title=title,
                    axis=alt.Axis(format=y_format) if y_format else alt.Axis()),
            color=alt.Color(
                "device_id:N",
                title="Device",
                legend=alt.Legend(orient="bottom", columns=3, labelLimit=500),  # Extended labelLimit and placed labels under the graph
            ),
            tooltip=[
                alt.Tooltip("ts_plot:T", title="Time"),
                alt.Tooltip("device_id:N", title="Device"),
                alt.Tooltip(f"{field}:Q", title=title, format=y_format or "")
            ],
        )
    )

    layers = [
        alt.layer(
            base.mark_line(),
            base.mark_point(size=45)  # ensures single points are visible
        )
    ]

    # helper: build 2-point horizontal mean lines (robust on time scales)
    def mean_lines_for(df_means: pd.DataFrame, label_col: str = "device_id"):
        if df_means.empty:
            return None
        rows = []
        for _, r in df_means.iterrows():
            rows.append({"ts_plot": x_min, label_col: r[label_col], "ybar": r["ybar"]})
            rows.append({"ts_plot": x_max, label_col: r[label_col], "ybar": r["ybar"]})
        df2 = pd.DataFrame(rows)
        return (
            alt.Chart(df2)
            .mark_line(strokeDash=[4,4], opacity=0.6)
            .encode(
                x=alt.X("ts_plot:T", title="Time"),
                y=alt.Y("ybar:Q", title=title),
                color=alt.Color(f"{label_col}:N", title="Device"),
                tooltip=[alt.Tooltip(f"{label_col}:N", title="Device"),
                         alt.Tooltip("ybar:Q", title="Mean", format=y_format or "")]
            )
        )

    # per-device horizontal mean lines
    if show_device_mean_line:
        df_device = dfp[dfp["device_id"] != "All devices (mean)"].copy()
        if not df_device.empty:
            if field == "direction_deg":
                perdev = (
                    df_device.groupby("device_id")[field]
                    .apply(circular_mean_deg).dropna().reset_index()
                    .rename(columns={field: "ybar"})
                )
            else:
                perdev = (
                    df_device.groupby("device_id", as_index=False)[field]
                    .mean().rename(columns={field: "ybar"})
                )
            dev_lines = mean_lines_for(perdev, "device_id")
            if dev_lines is not None:
                layers.append(dev_lines)

    # one combined horizontal mean across all selected devices (not the overall series)
    if show_combined_mean:
        df_comb = dfp[dfp["device_id"] != "All devices (mean)"].copy()
        if not df_comb.empty:
            if field == "direction_deg":
                ybar = circular_mean_deg(df_comb[field])
            else:
                ybar = float(df_comb[field].mean())
            if ybar is not None and not np.isnan(ybar):
                comb2 = pd.DataFrame([
                    {"ts_plot": x_min, "label": "Combined mean", "ybar": ybar},
                    {"ts_plot": x_max, "label": "Combined mean", "ybar": ybar},
                ])
                rule_comb = (
                    alt.Chart(comb2)
                    .mark_line(strokeWidth=2, opacity=0.7)
                    .encode(x="ts_plot:T", y="ybar:Q", color=alt.value("black"))
                )
                text_comb = (
                    alt.Chart(pd.DataFrame([{"ts_plot": x_max, "ybar": ybar, "label": "Combined mean"}]))
                    .mark_text(align="left", dx=6, dy=-6)
                    .encode(x="ts_plot:T", y="ybar:Q", text="label:N", color=alt.value("black"))
                )
                layers.extend([rule_comb, text_comb])

    chart = alt.layer(*layers).properties(height=260).interactive()

    # hint if only one timestamp -> no connecting lines
    if dfp["ts_plot"].nunique() <= 1:
        st.caption("Only one timestamp in view — showing points; choose a finer aggregation or a wider date range to see lines.")

    st.altair_chart(chart, use_container_width=True)

# ---- CHARTS ----
st.subheader("Temperature (°C)")
make_line_chart("temp_c", "Temperature (°C)")

st.subheader("Water level (mm)")
make_line_chart("water_mm", "Water level (mm)")

st.subheader("Direction (°)")
make_line_chart("direction_deg", "Direction (°)")

st.markdown("---")

# export (show what you plotted)
export_df = (plot_df
             .sort_values(["ts_plot","device_id"])
             .reset_index(drop=True))
st.dataframe(export_df.head(500), height=280)
st.download_button(
    "Download CSV",
    data=export_df.to_csv(index=False).encode("utf-8"),
    file_name="stats_export.csv",
    mime="text/csv",
)
