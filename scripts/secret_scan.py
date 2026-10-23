#!/usr/bin/env python3
"""Block secrets from entering the repo. Runs as a pre-commit hook and in CI.

    python3 scripts/secret_scan.py            # scan staged files (hook mode)
    python3 scripts/secret_scan.py --all      # scan every tracked file
    python3 scripts/secret_scan.py --install  # install the pre-commit hook

Exit 1 on any hit, so a commit is refused. Findings print the file, line number
and pattern name -- never the matched secret itself.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# name -> pattern. Deliberately strict about real key shapes and loose about
# anything that looks like a live bearer token.
PATTERNS: dict[str, re.Pattern[str]] = {
    "nvidia-api-key": re.compile(r"nvapi-[A-Za-z0-9_\-]{10,}"),
    "openai-style-key": re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    "bearer-literal": re.compile(r"Bearer\s+[A-Za-z0-9_\-\.=]{20,}"),
    "long-hex-token": re.compile(r"\b[0-9a-f]{40,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    "aws-access-key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "private-key-block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    # (?<![A-Za-z]) not \b, so ZETARIS_API_KEY= matches despite the underscore.
    "assigned-secret": re.compile(
        r"(?i)(?<![A-Za-z])(?:api[_-]?key|secret|password|passwd|token)\s*[:=]\s*"
        r"['\"]?[A-Za-z0-9_\-]{16,}"
    ),
}

# Files that legitimately contain secret-shaped text.
SKIP_FILES = {
    ".env.example",
    "scripts/secret_scan.py",            # the patterns themselves
    "tests/unit/test_secret_scan.py",    # the scanner's own synthetic corpus
}

# An explicit, reviewable escape hatch for a line that must contain a
# secret-shaped literal (a test fixture, a documented example). Preferred over
# widening a pattern, because it keeps the rest of the file scanned.
PRAGMA = re.compile(r"pragma:\s*allowlist\s+secret")
SKIP_SUFFIXES = {".lock", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".woff", ".woff2"}
SKIP_DIR_PARTS = {".git", ".refs", "node_modules", ".venv", "__pycache__", "web/dist", ".state"}

# A placeholder is not a secret.
ALLOWLIST = re.compile(
    r"(?i)your-[a-z\-]*(?:key|token)|example|placeholder|REPLACE_ME|xxxx+|<[a-z_\-]+>|rt-local"
)


def git(*args: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    return [l for l in out.stdout.splitlines() if l.strip()] if out.returncode == 0 else []


def skip(rel: str) -> bool:
    if rel in SKIP_FILES or Path(rel).suffix.lower() in SKIP_SUFFIXES:
        return True
    return any(part in SKIP_DIR_PARTS for part in Path(rel).parts) or "web/dist" in rel


def scan(rel: str) -> list[tuple[int, str]]:
    path = ROOT / rel
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []  # binary or unreadable: nothing to scan
    hits = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if PRAGMA.search(line):
            continue
        for name, pattern in PATTERNS.items():
            match = pattern.search(line)
            # The allowlist is checked against the match, never the whole line:
            # a placeholder elsewhere on the line must not mask a real secret.
            if match and not ALLOWLIST.search(match.group(0)):
                hits.append((lineno, name))
    return hits


HOOK = """#!/bin/sh
# Installed by scripts/secret_scan.py --install
exec python3 "$(git rev-parse --show-toplevel)/scripts/secret_scan.py"
"""


def install_hook() -> int:
    hooks = ROOT / ".git" / "hooks"
    if not hooks.is_dir():
        print("no .git/hooks directory; is this a git repo?", file=sys.stderr)
        return 1
    hook = hooks / "pre-commit"
    hook.write_text(HOOK, encoding="utf-8")
    hook.chmod(0o755)
    print(f"installed pre-commit hook at {hook}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="scan every tracked file")
    parser.add_argument("--install", action="store_true", help="install the pre-commit hook")
    args = parser.parse_args()

    if args.install:
        return install_hook()

    files = git("ls-files") if args.all else git("diff", "--cached", "--name-only", "--diff-filter=ACM")
    targets = [f for f in files if not skip(f)]

    # A real .env must never be staged, whatever its contents.
    staged = set(git("diff", "--cached", "--name-only"))
    env_staged = sorted(f for f in staged if Path(f).name == ".env" or f.startswith(".env."))
    env_staged = [f for f in env_staged if Path(f).name != ".env.example"]

    findings: list[str] = []
    for rel in targets:
        for lineno, name in scan(rel):
            findings.append(f"  {rel}:{lineno}  [{name}]")

    if env_staged:
        print("SECRET SCAN FAILED: an env file is staged", file=sys.stderr)
        for f in env_staged:
            print(f"  {f}  -- only .env.example may be committed", file=sys.stderr)
    if findings:
        print("SECRET SCAN FAILED: secret-shaped content found", file=sys.stderr)
        for f in findings:
            print(f, file=sys.stderr)
        print("\n  Values are not printed. Remove the secret, then re-stage.", file=sys.stderr)

    if env_staged or findings:
        return 1
    print(f"secret scan clean ({len(targets)} file(s) scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
