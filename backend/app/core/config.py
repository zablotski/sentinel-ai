import hashlib
import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

logger = logging.getLogger("sentinel.config")


class ModelConfig:
    """Central infrastructure config endpoints for Sentinel AI"""

    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    QDRANT_HOST: str = "http://localhost:6333"


class PolicyConfig(BaseModel):
    allowed: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)
    review_required: list[str] = Field(default_factory=list)


class UnknownLicenseHandling(BaseModel):
    """How to treat packages whose npm license field is UNKNOWN."""

    fetch_github_evidence: bool = True
    auto_classify_threshold: float = 0.85
    review_threshold: float = 0.60


class JudgeConfig(BaseModel):
    """Rulebook inputs for the global compliance judge."""

    permissive_licenses: list[str] = Field(
        default_factory=lambda: [
            "MIT",
            "Apache-2.0",
            "Apache 2.0",
            "BSD",
            "BSD-2-Clause",
            "BSD-3-Clause",
            "ISC",
            "0BSD",
            "Unlicense",
        ]
    )
    copyleft_markers: list[str] = Field(
        default_factory=lambda: ["GPL", "AGPL", "COPYLEFT", "LGPL"]
    )


class SentinelConfig(BaseModel):
    version: str = "1"
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    unknown_license_handling: UnknownLicenseHandling = Field(
        default_factory=UnknownLicenseHandling
    )
    judge: JudgeConfig = Field(default_factory=JudgeConfig)


class ModelsFileConfig(BaseModel):
    """Contents of sentinel.models.yml: provider choice and per-role model overrides."""

    provider: str | None = None
    models: dict[str, dict[str, str]] = Field(default_factory=dict)

    def model_override(self, provider: str, role: str) -> str | None:
        return (self.models.get(provider) or {}).get(role)


def default_models_config() -> ModelsFileConfig:
    """Empty override set when `sentinel.models.yml` is absent."""
    return ModelsFileConfig()


def default_sentinel_config() -> SentinelConfig:
    """Conservative in-repo defaults when `.sentinel.yml` is absent."""
    return SentinelConfig(
        version="1",
        policy=PolicyConfig(
            allowed=[
                "MIT",
                "Apache-2.0",
                "BSD-1-Clause",
                "BSD-2-Clause",
                "BSD-3-Clause",
                "0BSD",
                "ISC",
                "Zlib",
                "Unlicense",
            ],
            forbidden=[
                "GPL-2.0-only",
                "GPL-3.0-only",
                "AGPL-3.0-only",
            ],
            review_required=[
                "LGPL-2.1-only",
                "LGPL-3.0-only",
                "MPL-2.0",
            ],
        ),
    )


def _env_truthy(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in ("true", "1", "yes", "on")


def backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_local_env() -> None:
    """Load `.env` from repo root and `backend/`; honor existing shell exports."""
    root = backend_root()
    load_dotenv(root.parent / ".env", override=False)
    load_dotenv(root / ".env", override=False)
    load_dotenv(override=False)

    llm_key = (os.getenv("LLM_API_KEY") or "").strip()
    groq_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not llm_key and groq_key:
        os.environ["LLM_API_KEY"] = groq_key


def is_ci_environment() -> bool:
    """True when running in stateless CI (e.g. GitHub Actions)."""
    load_local_env()
    return _env_truthy(os.getenv("SENTINEL_CI"))


def repository_root() -> Path:
    """Project root: nearest ancestor containing sentinel.models.yml or .git."""
    for candidate in (backend_root(), *backend_root().parents):
        if (candidate / "sentinel.models.yml").is_file() or (candidate / ".git").exists():
            return candidate
    return backend_root()


def _resolve_config_path(path: str) -> Path:
    load_local_env()
    if path == ".sentinel.yml":
        override = (os.getenv("SENTINEL_CONFIG_PATH") or "").strip()
        if override:
            return Path(override).expanduser().resolve()

    config_path = Path(path)
    if config_path.is_absolute():
        return config_path
    return (repository_root() / config_path).resolve()


@lru_cache(maxsize=8)
def load_sentinel_config(path: str = ".sentinel.yml") -> SentinelConfig:
    """Load Sentinel policy from YAML; return defaults if the file is missing."""
    resolved = _resolve_config_path(path)
    if not resolved.is_file():
        logger.warning("Sentinel config not found at %s; using default policy", resolved)
        return default_sentinel_config()

    with resolved.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)

    if not isinstance(document, dict):
        logger.warning("Invalid Sentinel config at %s; using default policy", resolved)
        return default_sentinel_config()

    try:
        config = SentinelConfig.model_validate(document)
    except Exception as err:
        logger.warning(
            "Failed to parse Sentinel config at %s (%s); using default policy",
            resolved,
            err,
        )
        return default_sentinel_config()

    logger.info("Loaded Sentinel config v%s from %s", config.version, resolved)
    return config


def reload_sentinel_config(path: str = ".sentinel.yml") -> SentinelConfig:
    load_sentinel_config.cache_clear()
    return load_sentinel_config(path)


def policy_fingerprint(config: SentinelConfig | None = None) -> str:
    """Short stable hash of the effective policy; part of the verdict-cache key."""
    cfg = config if config is not None else load_sentinel_config()
    canonical = json.dumps(cfg.model_dump(), sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


def _resolve_models_config_path() -> Path:
    load_local_env()
    override = (os.getenv("SENTINEL_MODELS_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (repository_root() / "sentinel.models.yml").resolve()


@lru_cache(maxsize=1)
def load_models_config() -> ModelsFileConfig:
    """Load provider/model selections from sentinel.models.yml; defaults if missing."""
    resolved = _resolve_models_config_path()
    if not resolved.is_file():
        logger.debug("Models config not found at %s; using built-in model registry", resolved)
        return default_models_config()

    with resolved.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)

    if not isinstance(document, dict):
        logger.warning("Invalid models config at %s; using built-in model registry", resolved)
        return default_models_config()

    try:
        config = ModelsFileConfig.model_validate(document)
    except Exception as err:
        logger.warning(
            "Failed to parse models config at %s (%s); using built-in model registry",
            resolved,
            err,
        )
        return default_models_config()

    logger.info("Loaded models config from %s (provider=%s)", resolved, config.provider or "default")
    return config


def reload_models_config() -> ModelsFileConfig:
    load_models_config.cache_clear()
    return load_models_config()


def configure_observability() -> None:
    load_local_env()

    tracing_enabled = _env_truthy(
        os.getenv("LANGCHAIN_TRACING_V2") or os.getenv("LANGSMITH_TRACING")
    )
    api_key = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY") or ""
    project = (
        os.getenv("LANGCHAIN_PROJECT")
        or os.getenv("LANGSMITH_PROJECT")
        or "sentinel-ai-backend"
    )

    if tracing_enabled:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGSMITH_TRACING"] = "true"
    else:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")

    if api_key:
        os.environ["LANGCHAIN_API_KEY"] = api_key
        os.environ["LANGSMITH_API_KEY"] = api_key

    if project:
        os.environ["LANGCHAIN_PROJECT"] = project
        os.environ["LANGSMITH_PROJECT"] = project
