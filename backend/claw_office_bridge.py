#!/usr/bin/env python3
"""Bridge: push Claw agent status to Star Office UI (Pixel Office)."""

import atexit
import signal
import sys
import time
import urllib.request
import urllib.error
import json
import os

OFFICE_URL = os.environ.get("STAR_OFFICE_URL", "http://127.0.0.1:19000")
AGENT_NAME = os.environ.get("CLAW_AGENT_NAME", "Claw Main")
JOIN_KEY = os.environ.get("CLAW_JOIN_KEY", "claw-main-2026")
PUSH_INTERVAL = int(os.environ.get("CLAW_PUSH_INTERVAL", "30"))

_agent_id = None
_running = True


def _post(path, payload):
    url = f"{OFFICE_URL}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return json.loads(body)
        except Exception:
            return {"ok": False, "msg": body}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


def join():
    global _agent_id
    resp = _post(
        "/join-agent",
        {
            "name": AGENT_NAME,
            "state": "idle",
            "detail": "Подключён к Пиксельному офису",
            "joinKey": JOIN_KEY,
        },
    )
    if resp.get("ok"):
        _agent_id = resp.get("agentId")
        print(f"[Claw Bridge] Joined as {_agent_id}")
    else:
        print(f"[Claw Bridge] Join failed: {resp.get('msg')}")
    return resp


def leave():
    if not _agent_id:
        return
    resp = _post("/leave-agent", {"agentId": _agent_id})
    print(f"[Claw Bridge] Left: {resp.get('ok', False)}")


def push(state="idle", detail=""):
    if not _agent_id:
        return
    resp = _post(
        "/agent-push",
        {
            "agentId": _agent_id,
            "joinKey": JOIN_KEY,
            "state": state,
            "detail": detail or "Работаю в изолированном контуре",
        },
    )
    if not resp.get("ok"):
        print(f"[Claw Bridge] Push failed: {resp.get('msg')}")


def _signal_handler(signum, frame):
    global _running
    _running = False


def main():
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    atexit.register(leave)

    # Retry join a few times in case office is still starting
    for attempt in range(1, 6):
        resp = join()
        if resp.get("ok"):
            break
        print(f"[Claw Bridge] Retry join ({attempt}/5)...")
        time.sleep(3)

    if not _agent_id:
        print("[Claw Bridge] Could not join, exiting.")
        sys.exit(1)

    print("[Claw Bridge] Running push loop...")
    while _running:
        push("idle", "Ожидаю команд в изолированном контуре")
        for _ in range(PUSH_INTERVAL):
            if not _running:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
