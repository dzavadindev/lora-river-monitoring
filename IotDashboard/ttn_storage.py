# ttn_storage.py
from __future__ import annotations
import json
import requests
from typing import Iterable, Dict, Any, Optional

class TTNStorageError(RuntimeError):
    pass

def fetch_storage_uplinks(
    app_id: str,
    api_key: str,
    cluster: str = "eu1",
    *,
    after_iso: Optional[str] = None,   # e.g. "2025-10-13T00:00:00Z"
    until_iso: Optional[str] = None,   # e.g. "2025-10-13T23:59:59Z"
    limit: int = 1000,
    order: str = "desc",               # "asc"|"desc"
    session: Optional[requests.Session] = None,
) -> Iterable[Dict[str, Any]]:
    if not app_id or not api_key:
        raise TTNStorageError("Missing app_id or api_key")

    base = f"https://{cluster}.cloud.thethings.network"
    url  = f"{base}/api/v3/as/applications/{app_id}/packages/storage/uplink"

    params = {"limit": str(int(limit)), "order": order}
    if after_iso: params["after"] = after_iso
    if until_iso: params["until"] = until_iso

    headers = {
        "Authorization": f"Bearer {api_key}",
        # NDJSON is sometimes served as x-ndjson; both work in practice:
        "Accept": "application/x-ndjson, application/json",
    }

    s = session or requests.Session()

    try:
        r = s.get(url, headers=headers, params=params, stream=True, timeout=30)
    except requests.RequestException as e:
        raise TTNStorageError(f"HTTP error contacting TTS: {e}") from e

    # Helpful diagnostics on auth / app / cluster issues
    if r.status_code == 401:
        raise TTNStorageError("401 Unauthorized — is the API key correct?")
    if r.status_code == 403:
        raise TTNStorageError("403 Forbidden — API key likely missing 'Read application traffic' rights.")
    if r.status_code == 404:
        raise TTNStorageError("404 Not found — check app_id and cluster (eu1/nam1/au1).")
    if r.status_code >= 300:
        raise TTNStorageError(f"{r.status_code} {r.reason}: {r.text[:300]}")

    # Some deployments send content-type as application/json even for NDJSON.
    # We read line-by-line; skip empty keepalive lines.
    for raw in r.iter_lines():
        if not raw:
            continue
        try:
            yield json.loads(raw.decode("utf-8", "ignore"))
        except json.JSONDecodeError:
            # If you see this, print the line to inspect:
            # print("NDJSON decode error; line was:", raw[:200])
            continue
