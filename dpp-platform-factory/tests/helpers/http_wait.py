import time
import httpx
import structlog

logger = structlog.get_logger()

def wait_for_200(url: str, timeout: int = 30) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=2.0)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

def wait_for_unavailable(url: str, timeout: int = 10) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(url, timeout=1.0)
        except Exception:
            return True
        time.sleep(1)
    return False
