"""Shared fixtures.

Tests must never depend on the developer's local `.env`: they have to behave
identically here and on a judge's fresh clone that has no `.env` at all. So
settings in tests are always built with `_env_file=None`, and any stray
HAKKEN-relevant environment variables are cleared.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.config import Settings

ENV_PREFIXES = ("ZETARIS_", "METERLESS_", "SAMPLE_MODE", "DOMAIN_PACK", "STATE_DIR",
                "MAX_AGENT_ITERATIONS", "MAX_RETRIES", "RUN_TIMEOUT_S", "DATASVC_", "LOG_LEVEL")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove inherited config so defaults are the documented defaults."""
    import os

    for name in list(os.environ):
        if name.upper().startswith(ENV_PREFIXES):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def make_settings() -> Callable[..., Settings]:
    """Build Settings ignoring the repo's .env file."""

    def _factory(**overrides: object) -> Settings:
        return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]

    return _factory
