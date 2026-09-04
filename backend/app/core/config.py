from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # env_file lets credentials live in a gitignored backend/.env instead of a shell
    # history or a pasted string. Real environment variables still win over the file.
    model_config = SettingsConfigDict(
        env_prefix="OLYMPIZ_",
        extra="ignore",
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
    )

    app_name: str = "Olympiz Adaptive Tutor API"
    policy_version: str = "2026-08-28.2"
    catalog_version: str = "mechanics-2026-08-28"
    renderer_version: str = "template-1.0"
    grader_version: str = "deterministic-1.0"
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(
        default="gpt-5-mini",
        validation_alias=AliasChoices("OPENAI_MODEL", "OLYMPIZ_OPENAI_MODEL"),
    )
    openai_timeout_seconds: float = Field(default=6.0, gt=0, le=30)
    openai_max_output_tokens: int = Field(default=500, ge=100, le=1000)
    # Any OpenAI-compatible Chat Completions endpoint (Ollama Cloud, local Ollama,
    # Gemini's compat layer, Groq...). Takes precedence over OPENAI_API_KEY when set,
    # because it is the explicitly configured provider.
    llm_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_BASE_URL", "OLYMPIZ_LLM_BASE_URL"),
    )
    llm_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LLM_API_KEY", "OLLAMA_API_KEY", "OLYMPIZ_LLM_API_KEY"
        ),
    )
    llm_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_MODEL", "OLYMPIZ_LLM_MODEL"),
    )
    data_dir: Path = BACKEND_ROOT / "data"
    runtime_dir: Path = BACKEND_ROOT / "data" / "runtime"
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    )


settings = Settings()
