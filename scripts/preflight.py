#!/usr/bin/env python3
"""Read-only preflight for the Hakken agent template.

Checks local tooling, env-var presence (names only, never values), the Zetaris
REST data layer and the Meterless Nightshift provider. Standard library only,
so it runs before any dependency is installed.

Usage:
    python3 scripts/preflight.py            # all checks
    python3 scripts/preflight.py --no-chat  # skip the live chat completion

Secrets are read from the environment / .env and are never printed or logged.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import platform
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

# Nightshift Auto Detect contract: these ports, on these hosts.
DETECT_PORTS = (8088, 8090, 8787, 11434)
DETECT_HOSTS = ("127.0.0.1", "localhost", "[::1]")

PLACEHOLDER_TOKENS = {"rt-local", "your-nightshift-runtime-token", "your-zetaris-api-key"}

REQUIRED_ENV = [
    "ZETARIS_REST_URL",
    "ZETARIS_ORG_ID",
    "ZETARIS_API_KEY",
    "METERLESS_BASE_URL",
    "METERLESS_RUNTIME_TOKEN",
    "METERLESS_APP_ID",
    "METERLESS_MODEL",
]
OPTIONAL_ENV = [
    "METERLESS_MODEL_FAST",
    "METERLESS_MODEL_DEEP",
    "METERLESS_TIMEOUT_S",
    "ZETARIS_TIMEOUT_S",
    "ZETARIS_QUERY_LIMIT",
    "SAMPLE_MODE",
    "DOMAIN_PACK",
    "STATE_DIR",
    "DATASVC_PUBLIC_URL",
    "PORT",
]

rows: list[tuple[str, str, str, str]] = []  # (group, check, status, detail)


def add(group: str, check: str, ok: bool | None, detail: str = "") -> None:
    status = {True: "PASS", False: "FAIL", None: "WARN"}[ok]
    rows.append((group, check, status, detail))


# --- env ------------------------------------------------------------------


def load_env() -> bool:
    """Load .env into os.environ without overriding what is already set."""
    if not ENV_FILE.is_file():
        return False
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        # strip trailing inline comment, then surrounding quotes
        value = re.sub(r"\s+#.*$", "", value).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)
    return True


def check_env() -> None:
    found = load_env()
    add("env", ".env present", found, str(ENV_FILE) if found else "create it from .env.example")

    missing, placeholder, present = [], [], []
    for name in REQUIRED_ENV:
        value = os.environ.get(name, "").strip()
        if not value:
            missing.append(name)
        elif value in PLACEHOLDER_TOKENS:
            placeholder.append(name)
        else:
            present.append(name)
    add("env", "required names set", not missing and not placeholder,
        f"set: {len(present)}/{len(REQUIRED_ENV)}"
        + (f" · MISSING: {', '.join(missing)}" if missing else "")
        + (f" · PLACEHOLDER: {', '.join(placeholder)}" if placeholder else ""))

    opt_missing = [n for n in OPTIONAL_ENV if not os.environ.get(n, "").strip()]
    add("env", "optional names set", None if opt_missing else True,
        f"unset (defaults apply): {', '.join(opt_missing)}" if opt_missing else "all set")

    # Secret hygiene: .env must never be tracked by git.
    tracked = _git(["ls-files", "--error-unmatch", ".env"])
    add("env", ".env not tracked by git", tracked is None, "gitignored" if tracked is None else "TRACKED - remove it")


# --- tools ----------------------------------------------------------------


def _run(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() or out.stderr.strip() if out.returncode == 0 else None


def _git(args: list[str]) -> str | None:
    return _run(["git", "-C", str(ROOT), *args])


def check_tools() -> None:
    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    add("tools", "python3 >= 3.11", sys.version_info >= (3, 11), py)

    node = _run(["node", "--version"])
    major = int(node.lstrip("v").split(".")[0]) if node else 0
    add("tools", "node >= 20 (official TS conformance runners)", bool(node) and major >= 20,
        node or "not installed")

    docker = _run(["docker", "version", "--format", "{{.Server.Version}}"])
    add("tools", "docker daemon", bool(docker), docker or "not running")

    compose = _run(["docker", "compose", "version", "--short"])
    add("tools", "docker compose", bool(compose), compose or "not installed")

    git = _run(["git", "--version"])
    add("tools", "git", bool(git), git or "not installed")


# --- http helper ----------------------------------------------------------


def http(url: str, *, method: str = "GET", headers: dict | None = None,
         body: dict | None = None, timeout: float = 30.0) -> tuple[int, dict, str]:
    """Return (status, response_headers, text). Never raises for an HTTP error."""
    req = Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers=headers or {},
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read().decode(errors="replace")
    except HTTPError as e:
        return e.code, dict(e.headers or {}), e.read().decode(errors="replace")
    except (URLError, OSError) as e:
        return 0, {}, f"{getattr(e, 'reason', e)}"


def port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    family = socket.AF_INET6 if host.startswith("[") else socket.AF_INET
    target = host.strip("[]")
    try:
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((target, port)) == 0
    except OSError:
        return False


# --- zetaris --------------------------------------------------------------


def zetaris_headers(key: str, org: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "X-Org-ID": org,
        "X-Request-ID": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }


def zetaris_sql(base: str, key: str, org: str, sql: str, limit: int, timeout: float):
    return http(
        f"{base}/sql-editor/sqls/run",
        method="POST",
        headers=zetaris_headers(key, org),
        body={"queryId": str(uuid.uuid4()), "sql": sql, "source": "SqlEditor", "limit": limit},
        timeout=timeout,
    )


def check_zetaris() -> None:
    base = os.environ.get("ZETARIS_REST_URL", "http://localhost:8888/api/v1.0").rstrip("/")
    key = os.environ.get("ZETARIS_API_KEY", "").strip()
    org = os.environ.get("ZETARIS_ORG_ID", "1").strip()
    timeout = float(os.environ.get("ZETARIS_TIMEOUT_S", "60"))
    limit = int(os.environ.get("ZETARIS_QUERY_LIMIT", "1000"))

    host_port = re.sub(r"^https?://", "", base).split("/")[0]
    host, _, port = host_port.partition(":")
    reachable = port_open(host or "localhost", int(port or 80), timeout=2.0)
    add("zetaris", f"REST port reachable ({host_port})", reachable,
        "open" if reachable else "closed - is the zetaris-platform stack running?")

    if not reachable:
        for c in ("GET /datasource/datasources", "SELECT 1", "SHOW LIGHTNING DATABASES"):
            add("zetaris", c, False, "skipped - service unreachable")
        return
    if not key or key in PLACEHOLDER_TOKENS:
        for c in ("GET /datasource/datasources", "SELECT 1", "SHOW LIGHTNING DATABASES"):
            add("zetaris", c, False, "skipped - ZETARIS_API_KEY not set")
        return

    status, _, text = http(f"{base}/datasource/datasources",
                           headers=zetaris_headers(key, org), timeout=timeout)
    add("zetaris", "GET /datasource/datasources", status == 200, _diag(status, text))

    status, _, text = zetaris_sql(base, key, org, "SELECT 1", limit, timeout)
    ok = status == 200 and "1" in text
    add("zetaris", "SELECT 1", ok, _diag(status, text) if not ok else _rows_summary(text))

    status, _, text = zetaris_sql(base, key, org, "SHOW LIGHTNING DATABASES", limit, timeout)
    add("zetaris", "SHOW LIGHTNING DATABASES", status == 200,
        _rows_summary(text) if status == 200 else _diag(status, text))

    # Record the raw response shape once: we need to know where column names live.
    if status == 200:
        try:
            payload = json.loads(text)
            shape = sorted(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
            add("zetaris", "response top-level keys", True, str(shape))
        except json.JSONDecodeError:
            add("zetaris", "response top-level keys", None, "not JSON")


def _diag(status: int, text: str) -> str:
    if status == 0:
        return f"unreachable: {_short(text)}"
    hint = {401: " (bad ZETARIS_API_KEY)", 400: " (check X-Org-ID is numeric and the UUIDs)"}.get(status, "")
    return f"HTTP {status}{hint}: {_short(text)}"


def _rows_summary(text: str) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _short(text)
    rows_ = data.get("data") if isinstance(data, dict) else None
    if isinstance(rows_, list):
        return f"{len(rows_)} row(s): {_short(json.dumps(rows_[:5]))}"
    return _short(text)


def _short(text: str, n: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n] + "..."


# --- meterless nightshift -------------------------------------------------


def normalise_base(raw: str) -> str:
    """Normalise any pasted Nightshift URL to <host>/v1. Never produces /v1/v1."""
    url = (raw or "").strip().rstrip("/")
    if not url:
        url = "http://127.0.0.1:8088"
    if not re.match(r"^https?://", url):
        url = "http://" + url
    for suffix in ("/v1/chat/completions", "/v1/models", "/v1/completions", "/healthz", "/v1"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break
    return url.rstrip("/") + "/v1"


def meterless_state(base: str, token: str, app: str, timeout: float) -> tuple[str, list[str], str]:
    """Per the contract: GET /v1/models decides. Returns (state, route_ids, detail)."""
    status, _, text = http(f"{base}/models",
                           headers={"Authorization": f"Bearer {token}", "meterless-app": app},
                           timeout=timeout)
    if status in (401, 403):
        return "unauthorized", [], f"HTTP {status} - paste the Runtime token from Nightshift → Console"
    if status != 200:
        return "offline", [], _diag(status, text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return "offline", [], "200 but body is not JSON"
    ids = [m.get("id", "") for m in payload.get("data", []) if isinstance(m, dict)]
    routes = [i for i in ids if i.startswith("meterless/")]  # keep unknown meterless/* ids
    if not routes:
        return "offline", ids, "200 but no meterless/* ids"
    return "online", routes, f"{len(routes)} route(s)"


def check_meterless(do_chat: bool) -> None:
    base = normalise_base(os.environ.get("METERLESS_BASE_URL", ""))
    token = os.environ.get("METERLESS_RUNTIME_TOKEN", "").strip()
    app = os.environ.get("METERLESS_APP_ID", "hakken-agent").strip()
    model = os.environ.get("METERLESS_MODEL", "meterless/auto").strip()
    timeout = float(os.environ.get("METERLESS_TIMEOUT_S", "180"))

    add("meterless", "base URL normalised", "/v1/v1" not in base, base)

    # Auto Detect, per the contract.
    hits = [f"{h}:{p}" for p in DETECT_PORTS for h in DETECT_HOSTS if port_open(h, p)]
    add("meterless", "Auto Detect (8088/8090/8787/11434)", bool(hits),
        ", ".join(hits) if hits else "no runtime found on any candidate port")

    status, _, text = http(base.replace("/v1", "") + "/healthz", timeout=10)
    detail = ""
    if status == 200:
        try:
            health = json.loads(text)
            keys = health.get("providers", {}).get("cloud", {}).get("keys", [])
            detail = f"status={health.get('status')} engine_ready={health.get('engine_ready')} provider_keys={keys}"
        except json.JSONDecodeError:
            detail = "200, non-JSON body"
    add("meterless", "GET /healthz (process up only)", status == 200, detail or _diag(status, text))

    if not token or token in PLACEHOLDER_TOKENS:
        add("meterless", "GET /v1/models (decides state)", False,
            "skipped - METERLESS_RUNTIME_TOKEN not set")
        return

    state, routes, detail = meterless_state(base, token, app, timeout)
    add("meterless", "GET /v1/models (decides state)", state == "online", f"state={state} · {detail}")
    if routes:
        add("meterless", "meterless/* route ids", True, ", ".join(sorted(routes)))
    if state != "online" or not do_chat:
        return

    # One real chat completion: records which model answered. That is the NVIDIA evidence.
    started = time.monotonic()
    status, headers, text = http(
        f"{base}/chat/completions",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "meterless-app": app,
            "meterless-scope": "user",
            "Content-Type": "application/json",
        },
        # No tight max_tokens: these lanes spend hidden reasoning tokens, so a
        # one-word answer costs ~45 completion tokens and a small budget fails
        # as "<model>_empty_response", which looks like an outage. 512 is slack.
        body={"model": model, "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
              "max_tokens": 512},
        timeout=timeout,
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    if status != 200:
        add("meterless", f"chat completion on {model}", False, _diag(status, text))
        return
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        add("meterless", f"chat completion on {model}", False, "200 but body is not JSON")
        return
    content = (payload.get("choices") or [{}])[0].get("message", {}).get("content")
    add("meterless", f"chat completion on {model}", isinstance(content, str),
        f"{latency_ms} ms · content is {type(content).__name__} · {_short(str(content), 60)}")
    add("meterless", "response.model (which model answered)", bool(payload.get("model")),
        str(payload.get("model")))
    add("meterless", "usage", bool(payload.get("usage")), _short(json.dumps(payload.get("usage"))))
    ml_headers = {k: v for k, v in headers.items() if k.lower().startswith("meterless-")}
    add("meterless", "meterless-* response headers", None if not ml_headers else True,
        _short(json.dumps(ml_headers)) if ml_headers else "none returned - record the route instead")


# --- report ---------------------------------------------------------------


def save_results(path: Path) -> None:
    """Write the run to .state/preflight.json (gitignored).

    Deliberately NOT written into any shared doc: a preflight result is a fact
    about one machine at one moment, and shared docs that absorb it silently
    start lying to everyone else. See docs/ENVIRONMENTS.md.
    """
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "summary": {
            "pass": sum(1 for r in rows if r[2] == "PASS"),
            "fail": sum(1 for r in rows if r[2] == "FAIL"),
            "warn": sum(1 for r in rows if r[2] == "WARN"),
        },
        "checks": [
            {"group": g, "check": c, "status": s, "detail": d} for g, c, s, d in rows
        ],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"\n  (could not write {path}: {e})")
        return
    print(f"  saved to {path}")
    print("  This is a fact about THIS machine right now. Do not copy it into a")
    print("  shared doc -- put a one-line summary in your section of docs/ENVIRONMENTS.md.")


def report() -> int:
    width_check = max(len(r[1]) for r in rows)
    current = ""
    print()
    for group, check, status, detail in rows:
        if group != current:
            current = group
            print(f"\n  {group.upper()}")
        mark = {"PASS": "PASS", "FAIL": "FAIL", "WARN": "WARN"}[status]
        print(f"    [{mark}] {check.ljust(width_check)}  {detail}")
    failed = [r for r in rows if r[2] == "FAIL"]
    passed = [r for r in rows if r[2] == "PASS"]
    print(f"\n  {len(passed)} pass · {len(failed)} fail · {len(rows) - len(passed) - len(failed)} warn\n")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-chat", action="store_true", help="skip the live chat completion")
    parser.add_argument("--no-save", action="store_true",
                        help="do not write .state/preflight.json")
    args = parser.parse_args()

    check_tools()
    check_env()
    check_zetaris()
    check_meterless(do_chat=not args.no_chat)
    exit_code = report()
    if not args.no_save:
        save_results(Path(os.environ.get("STATE_DIR", ".state")) / "preflight.json"
                     if os.path.isabs(os.environ.get("STATE_DIR", ".state"))
                     else ROOT / os.environ.get("STATE_DIR", ".state") / "preflight.json")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
