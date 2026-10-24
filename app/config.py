"""Configuration: environment in, validated settings out.

Every secret is a `SecretStr`, so a stray `print(settings)` or an exception
repr cannot leak it. `safe_dump()` is the only sanctioned way to show the
configuration, and it reports secrets as presence, never value.

Hard rule (hackathon §5): secrets come from the environment only. No NVIDIA key
appears here at all -- it lives solely in Nightshift -> Setup -> Providers.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent

# Rejected by the Meterless contract, plus our own .env.example placeholders.
PLACEHOLDER_SECRETS = {
    "rt-local",
    "your-nightshift-runtime-token",
    "your-zetaris-api-key",
    "your-pbs-public-subscription-key",
}


def normalise_meterless_base(raw: str) -> str:
    """Normalise any pasted Nightshift URL to `<host>/v1`.

    The Power contract requires accepting a URL with or without a scheme, and
    with or without a `/v1`, `/v1/chat/completions`, `/v1/models` or `/healthz`
    suffix. It must never produce `/v1/v1` -- the contract calls that "the most
    common bug".
    """
    url = (raw or "").strip().rstrip("/")
    if not url:
        url = "http://127.0.0.1:8088"
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        url = "http://" + url
    # Longest first, so /v1/chat/completions is not mistaken for /v1.
    for suffix in ("/v1/chat/completions", "/v1/completions", "/v1/models", "/healthz", "/v1"):
        if url.lower().endswith(suffix):
            url = url[: -len(suffix)]
            break
    return url.rstrip("/") + "/v1"


class Settings(BaseSettings):
    """Validated runtime configuration. Field names mirror the official env vars."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- Zetaris (data layer) ------------------------------------------------
    zetaris_rest_url: str = "http://localhost:8888/api/v1.0"
    zetaris_org_id: str = "1"
    zetaris_api_key: SecretStr = SecretStr("")
    # Measured: trivial queries ~4s warm, a 2-table JOIN 91s, and one attempt
    # timed out entirely. 60s was below the observed worst case.
    zetaris_timeout_s: float = 180.0
    zetaris_query_limit: int = Field(default=1000, gt=0)

    # -- Meterless Nightshift (primary AI provider) --------------------------
    meterless_base_url: str = "http://127.0.0.1:8088/v1"
    meterless_runtime_token: SecretStr = SecretStr("")
    meterless_app_id: str = "hakken-agent"
    meterless_model: str = "meterless/auto"
    meterless_model_fast: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    meterless_model_deep: str = "nvidia/nemotron-3-super-120b-a12b"
    # The contract is explicit: 180 s, because a cold model load can take minutes.
    meterless_timeout_s: float = 180.0

    # -- PBS public API (reference data, build-time only) --------------------
    # Used ONLY by scripts/fetch_reference.py, never at run time: agents read the
    # lexicon from Zetaris, and a run never touches this API. One request per
    # 20 s, shared across every user of the public key.
    pbs_api_base: str = "https://data-api.health.gov.au/pbs/api/v3"
    # The published *unregistered* key. Not a credential -- the API is free and
    # needs no login -- but a bare hex string in the repo would trip the secret
    # scan and could read to a judge as a committed secret, so it lives in .env
    # like everything else and is referred to by name.
    pbs_subscription_key: SecretStr = SecretStr("")

    # -- Runtime behaviour ---------------------------------------------------
    sample_mode: bool = False
    domain_pack: str = "demo"
    max_agent_iterations: int = Field(default=3, ge=1)
    max_retries: int = Field(default=2, ge=0)
    run_timeout_s: float = Field(default=600.0, gt=0)
    state_dir: Path = Path(".state")
    # The URL Zetaris uses to reach datasvc. Goes verbatim into the
    # registration SQL, so it must resolve from inside the Zetaris containers.
    datasvc_public_url: str = "http://host.docker.internal:8100"
    # The URL our own app uses. A compose hostname here is fine.
    datasvc_internal_url: str = "http://localhost:8100"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    port: int = 8000

    # -- validators ----------------------------------------------------------

    @field_validator("zetaris_rest_url")
    @classmethod
    def _check_zetaris_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v:
            raise ValueError("ZETARIS_REST_URL must not be empty")
        if ":8889" in v:
            # The Zetaris AGENTS.md forbids this: 8889 is an internal port.
            raise ValueError("port 8889 is internal to Zetaris and must never be called; use 8888")
        return v

    @field_validator("meterless_base_url")
    @classmethod
    def _normalise(cls, v: str) -> str:
        return normalise_meterless_base(v)

    @field_validator("datasvc_public_url")
    @classmethod
    def _zetaris_reachable(cls, v: str) -> str:
        """Reject a URL only our own compose network can resolve.

        This value is embedded in `CREATE LIGHTNING REST TABLE ... endpoint`.
        Zetaris runs in a different compose project, so a service name like
        `datasvc` resolves for us and not for it -- the CREATE succeeds and
        every later query fails, which is slow to diagnose.
        """
        v = v.strip().rstrip("/")
        host = re.sub(r"^https?://", "", v).split("/")[0].split(":")[0]
        if host == "datasvc":
            raise ValueError(
                "DATASVC_PUBLIC_URL must be reachable from the Zetaris containers, "
                "not a name on our own compose network. Use host.docker.internal:8100 "
                "(or the host's LAN address). Set DATASVC_INTERNAL_URL=http://datasvc:8100 "
                "for our app's own calls instead."
            )
        return v

    @field_validator("state_dir")
    @classmethod
    def _absolute_state_dir(cls, v: Path) -> Path:
        return v if v.is_absolute() else REPO_ROOT / v

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper(cls, v: object) -> object:
        return v.upper() if isinstance(v, str) else v

    # -- secret presence -----------------------------------------------------

    @staticmethod
    def _usable(secret: SecretStr) -> bool:
        value = secret.get_secret_value().strip()
        return bool(value) and value not in PLACEHOLDER_SECRETS

    @property
    def has_zetaris_key(self) -> bool:
        return self._usable(self.zetaris_api_key)

    @property
    def has_meterless_token(self) -> bool:
        """False for an unset key and for the contract-rejected `rt-local`."""
        return self._usable(self.meterless_runtime_token)

    @property
    def has_pbs_key(self) -> bool:
        """Whether a PBS public API key is configured. Build-time only."""
        value = self.pbs_subscription_key.get_secret_value().strip()
        return bool(value) and value not in PLACEHOLDER_SECRETS

    def require_meterless_token(self) -> str:
        if not self.has_meterless_token:
            raise ValueError(
                "METERLESS_RUNTIME_TOKEN is unset or a placeholder. Copy the Runtime "
                "token from Nightshift -> Console into .env. The placeholder 'rt-local' "
                "is rejected by the runtime."
            )
        return self.meterless_runtime_token.get_secret_value()

    def require_zetaris_key(self) -> str:
        if not self.has_zetaris_key:
            raise ValueError(
                "ZETARIS_API_KEY is unset or a placeholder. Create one in the Zetaris UI "
                "(Management -> API Tokens) and put it in .env."
            )
        return self.zetaris_api_key.get_secret_value()

    def lane_for(self, role: str) -> str:
        """Role -> pinned route. Planner/Executor take FAST, Evaluator/Writer DEEP."""
        fast_roles = {"planner", "executor"}
        deep_roles = {"evaluator", "writer"}
        key = role.strip().lower()
        if key in fast_roles:
            return self.meterless_model_fast
        if key in deep_roles:
            return self.meterless_model_deep
        return self.meterless_model

    def safe_dump(self) -> dict[str, object]:
        """Loggable configuration. Secrets appear as presence only, never value."""
        return {
            "zetaris_rest_url": self.zetaris_rest_url,
            "zetaris_org_id": self.zetaris_org_id,
            "zetaris_api_key": "set" if self.has_zetaris_key else "MISSING",
            "zetaris_timeout_s": self.zetaris_timeout_s,
            "zetaris_query_limit": self.zetaris_query_limit,
            "meterless_base_url": self.meterless_base_url,
            "meterless_runtime_token": "set" if self.has_meterless_token else "MISSING",
            "meterless_app_id": self.meterless_app_id,
            "meterless_model": self.meterless_model,
            "meterless_model_fast": self.meterless_model_fast,
            "meterless_model_deep": self.meterless_model_deep,
            "meterless_timeout_s": self.meterless_timeout_s,
            "pbs_api_base": self.pbs_api_base,
            # Presence only, for symmetry with the real secrets -- this one is a
            # published public key, but no secret-shaped value is ever dumped.
            "pbs_subscription_key": "set" if self.has_pbs_key else "MISSING",
            "sample_mode": self.sample_mode,
            "domain_pack": self.domain_pack,
            "max_agent_iterations": self.max_agent_iterations,
            "max_retries": self.max_retries,
            "run_timeout_s": self.run_timeout_s,
            "state_dir": str(self.state_dir),
            "datasvc_public_url": self.datasvc_public_url,
            "datasvc_internal_url": self.datasvc_internal_url,
            "log_level": self.log_level,
            "port": self.port,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings. Cached so .env is read once."""
    return Settings()
