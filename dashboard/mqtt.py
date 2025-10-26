# mqtt.py — small helper around paho-mqtt with on_connect that:
# - subscribes given topics
# - ingests CSV once into your data_table on first connect

from __future__ import annotations
import ssl, json, time
from typing import Iterable, Optional, Tuple, Callable
from paho.mqtt import client as mqtt

# these two are your own modules
from csv_store import load_csv
from data_table import add_normalized_many


_csv_ingested_once = False

def create_client(
    host: str,
    port: int,
    *,
    username: str | None = None,
    password: str | None = None,
    use_tls: bool = False,
    client_id: str | None = None,
    keepalive: int = 30,
    subscribe_topics: Iterable[Tuple[str, int]] = (),
    csv_bootstrap_path: str | None = None,
    on_message: Optional[Callable[[mqtt.Client, object, mqtt.MQTTMessage], None]] = None,
) -> mqtt.Client:
    """
    Returns a configured mqtt.Client with:
      - default on_connect that subscribes topics and (optionally) ingests CSV -> data_table once
      - default on_disconnect that updates flags
      - your provided on_message (required for per-message handling)
    """
    c = mqtt.Client(client_id=client_id or "streamlit-mqtt", clean_session=True)
    if username:
        c.username_pw_set(username, password or "")
    if use_tls or port == 8883:
        c.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)

    # status attrs your UI reads
    c.connected_flag = False
    c.last_rc = None
    c.msg_count = 0
    c.last_topic = None
    c.last_seen = None
    c.csv_ingested = False
    c.last_note = None
    c.last_error = None

    topics = list(subscribe_topics)

    def _on_connect(client, userdata, flags, rc):
        nonlocal topics
        client.connected_flag = (rc == 0)
        client.last_rc = rc
        if rc != 0:
            return
        # subscribe configured topics
        for t, q in topics:
            try:
                client.subscribe(t, qos=q)
            except Exception:
                pass

        # CSV -> in-memory DF once per process
        global _csv_ingested_once
        if csv_bootstrap_path and not _csv_ingested_once and not client.csv_ingested:
            try:
                df = load_csv(csv_bootstrap_path, limit=None)
                if not df.empty:
                    added = add_normalized_many(df.to_dict(orient="records"))
                    client.last_note = f"Ingested {added} rows from CSV"
                _csv_ingested_once = True
                client.csv_ingested = True
            except Exception as e:
                client.last_error = f"CSV ingest failed: {e}"
                client.csv_ingested = True  # don't retry endlessly

    def _on_disconnect(client, userdata, rc):
        client.connected_flag = False
        client.last_rc = rc

    c.on_connect = _on_connect
    c.on_disconnect = _on_disconnect

    if on_message is not None:
        c.on_message = on_message
    else:
        # no-op default
        def _noop_on_message(client, userdata, msg):  # pragma: no cover
            client.msg_count += 1
            client.last_topic = msg.topic
            client.last_seen = time.time()
        c.on_message = _noop_on_message

    # stash target so caller can start loop/connect
    c._host, c._port, c._keepalive = host, port, keepalive
    return c

def start(client: mqtt.Client) -> None:
    client.connect_async(client._host, client._port, keepalive=client._keepalive)
    client.loop_start()

def stop(client: mqtt.Client) -> None:
    try:
        client.loop_stop()
        client.disconnect()
    except Exception:
        pass
