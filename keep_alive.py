import logging
import os
import sys
from datetime import datetime, timezone
import requests

APP_URL         = os.environ.get("APP_URL", "https://your-app.streamlit.app")
REQUEST_TIMEOUT = 30   

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
log = logging.getLogger("keep_alive")

def ping() -> bool:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log.info("Pinging %s  [%s]", APP_URL, timestamp)

    try:
        resp = requests.get(APP_URL, timeout=REQUEST_TIMEOUT)
        if resp.ok:
            log.info("✅  %s — HTTP %d", APP_URL, resp.status_code)
        else:
            log.warning("⚠️   %s — HTTP %d", APP_URL, resp.status_code)
        return resp.ok

    except requests.exceptions.RequestException as exc:
        log.error("❌  Request failed: %s", exc)

    return False

if __name__ == "__main__":
    success = ping()
    sys.exit(0 if success else 1)
