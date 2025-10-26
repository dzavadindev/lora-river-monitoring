import os, time
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from dotenv import load_dotenv, find_dotenv
from paho.mqtt import client as mqtt
from streamlit_autorefresh import st_autorefresh

from data_table import init_table, add_ttn_message, get_table
from mqtt import create_client, start, stop  # <-- use the new mqtt.py

# ---------- config ----------
load_dotenv(find_dotenv(usecwd=True))
HOST     = os.getenv("MQTT_HOST", "localhost")
PORT     = int(os.getenv("MQTT_PORT", "8883"))      # 1883 no TLS, 8883 TLS
USER     = os.getenv("MQTT_USERNAME", "")
PASS     = os.getenv("MQTT_PASSWORD", "")
TOPIC    = os.getenv("MQTT_TOPIC", "test/topic")
QOS      = int(os.getenv("MQTT_QOS", "0"))
CSV_PATH = os.getenv("MSG_CSV_PATH", "ttn_messages.csv")  # CSV used for bootstrap on connect

# ---------- streamlit setup ----------
st.set_page_config(page_title="MQTT Viewer", layout="wide")
interval = st.sidebar.slider("Refresh (ms)", 500, 5000, 1500, step=250)
tick = st_autorefresh(interval=interval, key="mqtt-refresh")
st.caption(f"Tick: {tick} • {datetime.now().strftime('%H:%M:%S')}")

st.title(f"Live messages: `{TOPIC}`")

# Initialize the in-memory table once per session
if "tbl_inited" not in st.session_state:
    init_table(max_rows=5000)
    st.session_state.tbl_inited = True

def on_message(client: mqtt.Client, userdata, msg):
    # lightweight status
    client.msg_count  = getattr(client, "msg_count", 0) + 1
    client.last_topic = msg.topic
    client.last_seen  = time.time()
    # push payload into the shared in-memory DF (data_table)
    add_ttn_message(msg.payload)

# ---------- create+start MQTT client once ----------
@st.cache_resource(show_spinner=False)
def get_client_started() -> mqtt.Client:
    c = create_client(
        host=HOST,
        port=PORT,
        username=USER or None,
        password=PASS or None,
        use_tls=(PORT == 8883),
        client_id="streamlit-mqtt",
        keepalive=30,
        subscribe_topics=[(TOPIC, QOS)],     # subscribe handled in mqtt.py on_connect
        csv_bootstrap_path=CSV_PATH,         # CSV->DF bootstrap handled in mqtt.py on_connect
        on_message=on_message,               # your message handler
    )
    # Start non-blocking network loop
    start(c)
    return c

client = get_client_started()

# ---------- status ----------
st.subheader("Connection")
st.write(f"**Broker**: `{HOST}:{PORT}`")
st.write(f"**Topic**:  `{TOPIC}`")
st.metric("Connected", "Yes" if getattr(client, "connected_flag", False) else "No")

st.metric("Messages", getattr(client, "msg_count", 0))
st.metric(
    "Last seen",
    datetime.fromtimestamp(getattr(client, "last_seen", 0), tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    if getattr(client, "last_seen", None) else "—"
)
st.write("Last topic:", getattr(client, "last_topic", "—"))

# Show CSV bootstrap notes/errors (set by mqtt.py on_connect)
if getattr(client, "last_note", None):
    st.sidebar.success(client.last_note)
if getattr(client, "last_error", None):
    st.sidebar.warning(client.last_error)

# ---------- table ----------
df = get_table()
if df.empty:
    st.info("Waiting for messages…")
else:
    df = df.copy()

    # Ensure base schema types (data_table already enforces columns)
    # 1) Parse UTC ts and make local display column
    df["ts"] = pd.to_datetime(df.get("ts"), utc=True, errors="coerce")
    df["ts_local"] = df["ts"].dt.tz_convert("Europe/Amsterdam")



    # 2) Derived numeric columns for convenience
    df["temp_c"]        = pd.to_numeric(df.get("water_temp_c"), errors="coerce")
    df["water_mm"]      = pd.to_numeric(df.get("water_level_mm"), errors="coerce")
    df["direction_deg"] = pd.to_numeric(df.get("flow_deg"), errors="coerce")
    df["lat"]           = pd.to_numeric(df.get("latitude"), errors="coerce")
    df["lon"]           = pd.to_numeric(df.get("longitude"), errors="coerce")

    # Optional: hide rows missing payload ts (NaT)
    if st.sidebar.toggle("Hide rows with missing payload timestamp", value=True):
        df = df[df["ts"].notna()]

    # Only select columns that actually exist (prevents KeyError)
    wanted = ["ts_local", "device_id", "temp_c", "water_mm", "direction_deg", "lat", "lon"]
    have   = [c for c in wanted if c in df.columns]

    st.dataframe(
        df.sort_values("ts", ascending=False).head(200)[have],
        height=420,
        width="stretch",   # <-- replaced use_container_width=True
    )

# Optional manual disconnect
if st.sidebar.button("Disconnect"):
    try:
        stop(client)
        st.success("Disconnected. Reload to reconnect.")
    except Exception as e:
        st.error(f"Disconnect error: {e}")
