#!/usr/bin/env python3
"""Locks NapCat's OneBot API to this machine (127.0.0.1) when it has no access token.

The bot talks to NapCat on the same computer, so an API without a token must not listen
on every network interface (0.0.0.0 / ::); otherwise anyone on the same network could send
messages as the bot and read its chats. Servers that have a token are left alone, and so
are setups where config.json points the bot at NapCat on another machine.

Used by setup_windows.bat and start.bat. Safe to run any number of times.
"""
import glob
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCKED_PORTS = {3000, 3001}   # AI2QQ's HTTP and WebSocket servers


def api_is_local() -> bool:
    try:
        with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8-sig") as f:
            api = str(json.load(f).get("onebot_http_api") or "http://127.0.0.1:3000")
    except Exception:
        api = "http://127.0.0.1:3000"
    return "127.0.0.1" in api or "localhost" in api


def config_files() -> list:
    patterns = [
        os.path.join(BASE_DIR, "NapCat", "**", "onebot11*.json"),          # Windows OneKey package
        os.path.join(os.path.expanduser("~"), ".napcat", "config", "onebot11*.json"),
    ]
    found = []
    for pattern in patterns:
        for path in glob.glob(pattern, recursive=True):
            if path not in found:
                found.append(path)
    return found


def lock(path: str) -> str:
    """Returns 'locked', 'ok', 'denied' or 'skipped'."""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception:
        return "skipped"
    network = data.get("network") if isinstance(data, dict) else None
    if not isinstance(network, dict):
        return "ok"
    changed = False
    for kind in ("httpServers", "websocketServers"):
        for server in network.get(kind) or []:
            if (isinstance(server, dict) and server.get("port") in LOCKED_PORTS
                    and not str(server.get("token") or "")
                    and str(server.get("host") or "").strip() in ("", "0.0.0.0", "::")):
                server["host"] = "127.0.0.1"
                changed = True
    if not changed:
        return "ok"
    try:
        tmp = path + ".tmp-secure"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return "locked"
    except PermissionError:
        return "denied"
    except Exception:
        return "skipped"


def main():
    if not api_is_local():
        return  # NapCat runs on another machine; protect it there with a token instead
    for path in config_files():
        result = lock(path)
        if result == "locked":
            print(f"[security] OneBot API now listens on 127.0.0.1 only: {path}")
            print("           Restart NapCat for this to take effect.")
        elif result == "denied":
            print(f"[!] Security: could not update {path} (no permission).")
            print('    Open it as administrator and set "host" to "127.0.0.1" for port 3000.')


if __name__ == "__main__":
    main()
