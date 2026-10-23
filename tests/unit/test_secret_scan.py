"""The secret scanner must catch real keys and ignore placeholders.

This is the guard that stands between us and a disqualification, so it gets
tested like production code. No real secret appears in this file: every
"secret" below is synthetic and shaped to match a pattern.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import secret_scan  # noqa: E402

MUST_CATCH = [
    ("nvidia-api-key", "nvapi-aBcDeFgH1234567890xyz"),
    ("openai-style-key", "sk-proj-AbCdEfGh1234567890abcd"),
    ("bearer-literal", "Authorization: Bearer AbCdEf1234567890GhIjKlMnOp"),
    ("jwt", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmno"),
    ("aws-access-key", "AKIAQ7RZ4TPLMN2XJW8D"),
    ("private-key-block", "-----BEGIN PRIVATE KEY-----"),
    # The underscore in ZETARIS_API_KEY defeats a \b anchor; this is why the
    # pattern uses a (?<![A-Za-z]) lookbehind instead.
    ("assigned-secret", 'ZETARIS_API_KEY="A1b2C3d4E5f6G7h8I9j0"'),
    ("long-hex-token", "a3f9c81d5e7b2046a3f9c81d5e7b2046a3f9c81d"),
]

MUST_IGNORE = [
    "METERLESS_RUNTIME_TOKEN=your-nightshift-runtime-token",
    "ZETARIS_API_KEY=your-zetaris-api-key",
    "token = os.environ['METERLESS_RUNTIME_TOKEN']",
    "METERLESS_MODEL_FAST=meterless/fast",
    "METERLESS_BASE_URL=http://127.0.0.1:8088/v1",
    "# the placeholder rt-local is rejected by the runtime",
]


def _scan_line(tmp_path: Path, line: str) -> list[tuple[int, str]]:
    """Scan one line through the real scanner, via a file under the repo root."""
    target = REPO_ROOT / "_pytest_secret_scan_tmp.txt"
    target.write_text(line + "\n", encoding="utf-8")
    try:
        return secret_scan.scan(target.name)
    finally:
        target.unlink(missing_ok=True)


@pytest.mark.parametrize(("expected_pattern", "line"), MUST_CATCH, ids=[c[0] for c in MUST_CATCH])
def test_catches_secret_shaped_content(tmp_path: Path, expected_pattern: str, line: str) -> None:
    hits = _scan_line(tmp_path, line)
    assert hits, f"scanner missed a {expected_pattern}"
    assert expected_pattern in {name for _, name in hits}


@pytest.mark.parametrize("line", MUST_IGNORE)
def test_ignores_placeholders_and_var_names(tmp_path: Path, line: str) -> None:
    assert _scan_line(tmp_path, line) == [], f"false positive on: {line}"


def test_placeholder_does_not_mask_a_real_secret(tmp_path: Path) -> None:
    """Regression: the allowlist is checked against the match, not the line.

    An earlier version skipped any line containing a placeholder, so a real key
    sitting next to the word "your-zetaris-api-key" went undetected.
    """
    line = "# your-zetaris-api-key goes here -> nvapi-RealLooking1234567890"
    hits = _scan_line(tmp_path, line)
    assert "nvidia-api-key" in {name for _, name in hits}


def test_env_example_is_skipped_but_env_is_not() -> None:
    assert secret_scan.skip(".env.example") is True
    assert secret_scan.skip(".env") is False
    assert secret_scan.skip(".refs/meterless/README.md") is True
    assert secret_scan.skip("app/config.py") is False
