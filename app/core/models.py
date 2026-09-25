from app.core.config import load_models_config


class ModelRegistry:
    """
    Centralized inventory of all AI models utilized across Sentinel AI.
    Provides complete visibility, tracking, and auditability for compliance.

    Values here are built-in defaults; per-role overrides can be supplied in
    `sentinel.models.yml` (see `load_models_config`).
    """

    # Ollama — heavy reasoning (Actor)
    LAWYER_NODE_MODEL: str = "deepseek-r1:8b"

    # Ollama — lightweight verdict QA (Auditor)
    CRITIC_NODE_MODEL: str = "llama3.2:3b"

    # Ollama — local security classifier
    GUARDRAIL_MODEL: str = "llama-guard3:1b"

    # Groq — CI/CD cloud models
    GROQ_HEAVY_MODEL: str = "openai/gpt-oss-120b"
    GROQ_STANDARD_MODEL: str = "openai/gpt-oss-20b"
    GROQ_GUARDRAIL_MODEL: str = "meta-llama/llama-prompt-guard-2-22m"

    @classmethod
    def default_model_for_role(cls, provider: str, role: str) -> str:
        """Built-in default model id for a node role and provider (no YAML)."""
        normalized = provider.strip().lower()
        role_key = role.strip().lower()

        if normalized == "groq":
            if role_key == "heavy":
                return cls.GROQ_HEAVY_MODEL
            if role_key == "guardrail":
                return cls.GROQ_GUARDRAIL_MODEL
            return cls.GROQ_STANDARD_MODEL

        if role_key == "heavy":
            return cls.LAWYER_NODE_MODEL
        if role_key == "guardrail":
            return cls.GUARDRAIL_MODEL
        return cls.CRITIC_NODE_MODEL

    @classmethod
    def model_for_role(cls, provider: str, role: str) -> str:
        """Resolve model id for a role: sentinel.models.yml override, else default."""
        override = load_models_config().model_override(
            provider.strip().lower(), role.strip().lower()
        )
        if override:
            return override
        return cls.default_model_for_role(provider, role)
