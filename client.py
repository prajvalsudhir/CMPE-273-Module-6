import json
import os
import time
import urllib.request

URL = os.environ.get("INVENTORY_URL", "http://inventory")
n = 0
while True:
    n += 1
    try:
        with urllib.request.urlopen(URL, timeout=5) as r:
            body = json.loads(r.read().decode())
        print(f"[client] request {n} -> served by {body.get('pod')}", flush=True)
    except Exception as e:
        print(f"[client] request {n} -> error: {e}", flush=True)
    time.sleep(1)
