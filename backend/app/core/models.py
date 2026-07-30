class ModelRegistry:
    """
    Centralized inventory of all AI models utilized across Sentinel AI.
    Provides complete visibility, tracking, and auditability for compliance.
    """

    # Ollama — heavy reasoning (Actor)
    LAWYER_NODE_MODEL: str = "deepseek-r1:8b"

    # Ollama — lightweight verdict QA (Auditor)
    CRITIC_NODE_MODEL: str = "llama3.2:3b"

    # Ollama — local security classifier
    GUARDRAIL_MODEL: str = "llama-guard3:1b"

    # Groq — CI/CD cloud models
    GROQ_HEAVY_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_STANDARD_MODEL: str = "llama-3.1-8b-instant"
    GROQ_GUARDRAIL_MODEL: str = "meta-llama/llama-prompt-guard-2-22m"

    @classmethod
    def model_for_role(cls, provider: str, role: str) -> str:
        """Resolve model id for a node role and active LLM provider."""
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
