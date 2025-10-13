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

# Prep
df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
df["ts_local"] = df["ts"].dt.tz_convert("Europe/Amsterdam")
pts = df.dropna(subset=["lat", "lon"])

if pts.empty:
    st.info("No rows with lat/lon yet.")
    st.stop()

# Latest position per device
latest = (
    pts.sort_values("ts")               # oldest->newest
       .drop_duplicates("device_id", keep="last")
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
    dev = r.get("device_id") or "—"
    col = color_for_device(dev)
    ts = r["ts_local"].strftime("%Y-%m-%d %H:%M:%S") if pd.notna(r["ts_local"]) else "—"
    temp = "—" if pd.isna(r.get("temp_c")) else f"{r['temp_c']} °C"
    water_m = "—" if pd.isna(r.get("water_m")) else f"{r['water_m']} m"
    water_mm = "—" if pd.isna(r.get("water_mm")) else f"{int(r['water_mm'])} mm"
    dirdeg = "—" if pd.isna(r.get("direction_deg")) else f"{int(r['direction_deg'])}°"

    popup_html = f"""
    <b>Device:</b> {dev}<br/>
    <b>Time:</b> {ts}<br/>
    <b>Temp:</b> {temp}<br/>
    <b>Water:</b> {water_m} ({water_mm})<br/>
    <b>Direction:</b> {dirdeg}<br/>
    <b>Lat/Lon:</b> {r['lat']:.6f}, {r['lon']:.6f}
    """
    folium.Marker(
        location=[r["lat"], r["lon"]],
        tooltip=dev,  # shows on hover
        popup=folium.Popup(popup_html, max_width=280),
        icon=folium.Icon(color=col, icon="info-sign"),
    ).add_to(cluster)

st_folium(m, width=1100, height=620)

# Small legend + table
st.caption(f"Devices on map: {len(latest)}")
cols = ["ts_local","device_id","temp_c","water_m","water_mm","direction_deg","lat","lon"]
st.dataframe(latest[cols].sort_values("ts_local", ascending=False), height=300)
