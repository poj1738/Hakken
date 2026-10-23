"""Config layer: URL normalisation, placeholder rejection, and secret hygiene."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from app.config import PLACEHOLDER_SECRETS, normalise_meterless_base


class TestNormaliseMeterlessBase:
    """The Power contract: accept anything pasted, normalise to <host>/v1.

    "Never produce /v1/v1" -- the contract calls that the most common bug.
    """

    @pytest.mark.parametrize(
        ("pasted", "expected"),
        [
            ("http://127.0.0.1:8088/v1", "http://127.0.0.1:8088/v1"),
            ("http://127.0.0.1:8088", "http://127.0.0.1:8088/v1"),
            ("127.0.0.1:8088", "http://127.0.0.1:8088/v1"),              # no scheme
            ("http://127.0.0.1:8088/", "http://127.0.0.1:8088/v1"),      # trailing slash
            ("http://127.0.0.1:8088/v1/", "http://127.0.0.1:8088/v1"),
            ("http://127.0.0.1:8088/v1/models", "http://127.0.0.1:8088/v1"),
            ("http://127.0.0.1:8088/v1/chat/completions", "http://127.0.0.1:8088/v1"),
            ("http://127.0.0.1:8088/healthz", "http://127.0.0.1:8088/v1"),
            ("localhost:8090/v1", "http://localhost:8090/v1"),
            ("https://box.local/v1/models", "https://box.local/v1"),
            ("", "http://127.0.0.1:8088/v1"),                            # default
            ("  http://127.0.0.1:8088/v1  ", "http://127.0.0.1:8088/v1"),
        ],
    )
    def test_normalises(self, pasted: str, expected: str, make_settings) -> None:
        assert normalise_meterless_base(pasted) == expected

    @pytest.mark.parametrize(
        "pasted",
        [
            "http://127.0.0.1:8088/v1",
            "http://127.0.0.1:8088/v1/",
            "http://127.0.0.1:8088/v1/models",
            "http://127.0.0.1:8088/v1/chat/completions",
            "http://127.0.0.1:8088",
            "127.0.0.1:8088",
            "",
        ],
    )
    def test_never_produces_v1_v1(self, pasted: str, make_settings) -> None:
        assert "/v1/v1" not in normalise_meterless_base(pasted)

    def test_always_ends_in_exactly_one_v1(self, make_settings) -> None:
        for pasted in ("box:8088", "http://box:8088/healthz", "http://box:8088/v1/models"):
            out = normalise_meterless_base(pasted)
            assert out.endswith("/v1")
            assert out.count("/v1") == 1


class TestSecretHandling:
    def test_placeholder_token_is_not_usable(self, make_settings) -> None:
        """The contract: the placeholder rt-local is rejected."""
        for placeholder in PLACEHOLDER_SECRETS:
            s = make_settings(
                meterless_runtime_token=SecretStr(placeholder),
                zetaris_api_key=SecretStr(placeholder),
            )
            assert s.has_meterless_token is False
            assert s.has_zetaris_key is False

    def test_empty_and_whitespace_token_is_not_usable(self, make_settings) -> None:
        for value in ("", "   "):
            assert make_settings(meterless_runtime_token=SecretStr(value)).has_meterless_token is False

    def test_real_looking_token_is_usable(self, make_settings) -> None:
        s = make_settings(meterless_runtime_token=SecretStr("a-plausible-runtime-token-value"))
        assert s.has_meterless_token is True

    def test_require_token_raises_a_useful_message(self, make_settings) -> None:
        s = make_settings(meterless_runtime_token=SecretStr("rt-local"))
        with pytest.raises(ValueError, match="rt-local"):
            s.require_meterless_token()
        with pytest.raises(ValueError, match="ZETARIS_API_KEY"):
            make_settings(zetaris_api_key=SecretStr("")).require_zetaris_key()

    def test_secrets_never_appear_in_repr_or_str(self, make_settings) -> None:
        secret = "super-secret-token-do-not-leak"  # pragma: allowlist secret
        s = make_settings(
            meterless_runtime_token=SecretStr(secret),
            zetaris_api_key=SecretStr(secret),
        )
        assert secret not in repr(s)
        assert secret not in str(s)
        assert secret not in str(s.meterless_runtime_token)
        assert secret not in str(s.model_dump())

    def test_safe_dump_reports_presence_not_value(self, make_settings) -> None:
        secret = "super-secret-token-do-not-leak"  # pragma: allowlist secret
        s = make_settings(
            meterless_runtime_token=SecretStr(secret),
            zetaris_api_key=SecretStr("your-zetaris-api-key"),
        )
        dumped = s.safe_dump()
        assert secret not in str(dumped)
        assert dumped["meterless_runtime_token"] == "set"
        assert dumped["zetaris_api_key"] == "MISSING"


class TestZetarisUrlGuard:
    def test_rejects_internal_port_8889(self, make_settings) -> None:
        """Zetaris AGENTS.md: do not call port 8889 on a local instance."""
        with pytest.raises(ValidationError, match="8889"):
            make_settings(zetaris_rest_url="http://localhost:8889/api/v1.0")

    def test_rejects_empty(self, make_settings) -> None:
        with pytest.raises(ValidationError):
            make_settings(zetaris_rest_url="   ")

    def test_strips_trailing_slash(self, make_settings) -> None:
        assert make_settings(zetaris_rest_url="http://localhost:8888/api/v1.0/").zetaris_rest_url == (
            "http://localhost:8888/api/v1.0"
        )


class TestLaneRouting:
    """Role -> disposition is our declared intent; see docs/DECISIONS.md for why
    it cannot be a guarantee (the runtime's router does not honour pinning)."""

    def test_planner_and_executor_take_fast(self, make_settings) -> None:
        s = make_settings(meterless_model_fast="meterless/fast")
        assert s.lane_for("Planner") == "meterless/fast"
        assert s.lane_for("executor") == "meterless/fast"

    def test_evaluator_and_writer_take_deep(self, make_settings) -> None:
        s = make_settings(meterless_model_deep="meterless/deep")
        assert s.lane_for("Evaluator") == "meterless/deep"
        assert s.lane_for("  WRITER ") == "meterless/deep"

    def test_unknown_role_falls_back_to_default(self, make_settings) -> None:
        s = make_settings(meterless_model="meterless/auto")
        assert s.lane_for("Librarian") == "meterless/auto"


class TestOtherValidation:
    def test_state_dir_is_made_absolute(self, make_settings) -> None:
        assert make_settings(state_dir=".state").state_dir.is_absolute()

    def test_log_level_is_upper_cased(self, make_settings) -> None:
        assert make_settings(log_level="debug").log_level == "DEBUG"

    def test_timeout_default_matches_the_contract(self, make_settings) -> None:
        """180 s, because a cold model load can take minutes."""
        assert make_settings().meterless_timeout_s == 180.0

    def test_bounds_are_enforced(self, make_settings) -> None:
        with pytest.raises(ValidationError):
            make_settings(max_agent_iterations=0)
        with pytest.raises(ValidationError):
            make_settings(zetaris_query_limit=0)
