# pages/02_Map.py
import hashlib
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from data_table import get_table

import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

st.set_page_config(page_title="Device Map", layout="wide")
st.title("Device locations")

# Auto-refresh just this page
interval = st.sidebar.slider("Refresh (ms)", 500, 5000, 2000, 500)
st_autorefresh(interval=interval, key="map-refresh")

df = get_table().copy()
if df.empty:
    st.info("No data yet — check the main page is connected to MQTT.")
    st.stop()

# --- map NEW schema -> convenience columns used below ---
# New schema fields: water_temp_c, water_level_mm, flow_deg, latitude, longitude
df["temp_c"]        = pd.to_numeric(df.get("water_temp_c"), errors="coerce")
df["water_mm"]      = pd.to_numeric(df.get("water_level_mm"), errors="coerce")
df["water_m"]       = df["water_mm"] / 1000.0
df["direction_deg"] = pd.to_numeric(df.get("flow_deg"), errors="coerce")
df["lat"]           = pd.to_numeric(df.get("latitude"), errors="coerce")
df["lon"]           = pd.to_numeric(df.get("longitude"), errors="coerce")

# Timestamps (UTC -> local tz column)
df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
df = df.dropna(subset=["ts"])
df["ts_local"] = df["ts"].dt.tz_convert("Europe/Amsterdam")

# Only rows with coordinates
pts = df.dropna(subset=["lat", "lon"])
if pts.empty:
    st.info("No rows with lat/lon yet.")
    st.stop()

# Latest position per device
latest = (
    pts.sort_values("ts")               # oldest->newest
       .drop_duplicates("device_id", keep="last")
       .copy()
)

# Map center
if len(latest) > 1:
    center = [latest["lat"].mean(), latest["lon"].mean()]
else:
    center = [latest.iloc[0]["lat"], latest.iloc[0]["lon"]]

m = folium.Map(location=center, zoom_start=7, tiles="OpenStreetMap")
cluster = MarkerCluster().add_to(m)

# Deterministic color per device (nice for many devices)
def color_for_device(dev_id: str) -> str:
    palette = ["blue","green","red","purple","orange","darkred","lightred","beige",
               "darkblue","darkgreen","cadetblue","darkpurple","white","pink","lightblue",
               "lightgreen","gray","black","lightgray"]
    h = int(hashlib.sha1((dev_id or '').encode()).hexdigest(), 16)
    return palette[h % len(palette)]

for _, r in latest.iterrows():
    dev = (r.get("device_id") or "—")
    col = color_for_device(str(dev))
    ts  = r["ts_local"].strftime("%Y-%m-%d %H:%M:%S") if pd.notna(r["ts_local"]) else "—"

    temp     = None if pd.isna(r.get("temp_c"))        else f"{r['temp_c']:.1f} °C"
    water_m  = None if pd.isna(r.get("water_m"))       else f"{r['water_m']:.3f} m"
    water_mm = None if pd.isna(r.get("water_mm"))      else f"{int(round(r['water_mm']))} mm"
    dirdeg   = None if pd.isna(r.get("direction_deg")) else f"{int(round(r['direction_deg']))}°"
    latlon   = f"{r['lat']:.6f}, {r['lon']:.6f}" if pd.notna(r["lat"]) and pd.notna(r["lon"]) else "—"

    # Build popup with only available lines
    lines = [
        f"<b>Device:</b> {dev}",
        f"<b>Time:</b> {ts}",
    ]
    if temp is not None:     lines.append(f"<b>Temp:</b> {temp}")
    if water_m is not None or water_mm is not None:
        wm = water_m or "—"
        wmm = f" ({water_mm})" if water_mm is not None else ""
        lines.append(f"<b>Water:</b> {wm}{wmm}")
    if dirdeg is not None:   lines.append(f"<b>Direction:</b> {dirdeg}")
    lines.append(f"<b>Lat/Lon:</b> {latlon}")

    popup_html = "<br/>".join(lines)

    folium.Marker(
        location=[float(r["lat"]), float(r["lon"])],
        tooltip=str(dev),  # shows on hover
        popup=folium.Popup(popup_html, max_width=320),
        icon=folium.Icon(color=col, icon="info-sign"),
    ).add_to(cluster)

st_folium(m, width=1100, height=620)

# Small legend + table (safe subset of columns that exist)
st.caption(f"Devices on map: {len(latest)}")
cols_wanted = ["ts_local","device_id","temp_c","water_m","water_mm","direction_deg","lat","lon"]
cols_have   = [c for c in cols_wanted if c in latest.columns]
st.dataframe(latest[cols_have].sort_values("ts_local", ascending=False), height=300)
