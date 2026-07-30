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


class SentinelConfig(BaseModel):
    version: str = "1"
    policy: PolicyConfig = Field(default_factory=PolicyConfig)


def default_sentinel_config() -> SentinelConfig:
    """Conservative in-repo defaults when `.sentinel.yml` is absent."""
    return SentinelConfig(
        version="1",
        policy=PolicyConfig(
            allowed=[
                "MIT",
                "Apache-2.0",
                "BSD-2-Clause",
                "BSD-3-Clause",
                "ISC",
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
    return backend_root().parent


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
