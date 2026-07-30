import logging
import os
from functools import lru_cache
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import ModelConfig, load_local_env
from app.core.models import ModelRegistry

logger = logging.getLogger("sentinel.llm")

NodeRole = Literal["heavy", "standard", "guardrail"]

_VALID_ROLES = frozenset({"heavy", "standard", "guardrail"})


def _ensure_env_loaded() -> None:
    load_local_env()


def _normalize_provider(raw: str | None) -> str:
    if not raw or not raw.strip():
        return "groq"
    return raw.strip().lower()


def _api_key_from_env() -> str:
    _ensure_env_loaded()
    return (
        (os.getenv("LLM_API_KEY") or "").strip()
        or (os.getenv("GROQ_API_KEY") or "").strip()
    )


def get_active_provider() -> str:
    """Return the effective LLM provider after Groq key validation and fallback."""
    return _resolve_effective_provider()


def _resolve_effective_provider() -> str:
    _ensure_env_loaded()
    requested = _normalize_provider(os.getenv("LLM_PROVIDER"))

    if requested == "groq":
        if not _api_key_from_env():
            logger.warning(
                "LLM_PROVIDER=groq but LLM_API_KEY is unset; falling back to ollama"
            )
            return "ollama"
        return "groq"

    if requested == "ollama":
        return "ollama"

    logger.warning("Unknown LLM_PROVIDER=%r; falling back to ollama", requested)
    return "ollama"


def _build_groq_client(model_name: str) -> BaseChatModel:
    from langchain_groq import ChatGroq

    api_key = _api_key_from_env()
    if not api_key:
        raise RuntimeError("Groq client requires LLM_API_KEY")

    return ChatGroq(model=model_name, temperature=0.0, api_key=api_key)


def _build_ollama_client(model_name: str) -> BaseChatModel:
    _ensure_env_loaded()
    base_url = (
        os.getenv("OLLAMA_BASE_URL", ModelConfig.OLLAMA_BASE_URL).strip()
        or ModelConfig.OLLAMA_BASE_URL
    )
    return ChatOpenAI(
        base_url=base_url,
        api_key="local-no-key-needed",
        model=model_name,
        temperature=0.0,
    )


@lru_cache(maxsize=len(_VALID_ROLES))
def get_node_llm(role: str) -> BaseChatModel:
    """Return a cached chat model for the given node role (heavy, standard, guardrail)."""
    role_key = role.strip().lower()
    if role_key not in _VALID_ROLES:
        raise ValueError(
            f"Unknown LLM role {role!r}; expected one of: {sorted(_VALID_ROLES)}"
        )

    provider = _resolve_effective_provider()
    model_name = ModelRegistry.model_for_role(provider, role_key)

    if provider == "groq":
        client = _build_groq_client(model_name)
    else:
        client = _build_ollama_client(model_name)

    logger.info("LLM client ready: provider=%s role=%s model=%s", provider, role_key, model_name)
    return client
