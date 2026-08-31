from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OLYMPIZ_", extra="ignore")

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
    data_dir: Path = BACKEND_ROOT / "data"
    runtime_dir: Path = BACKEND_ROOT / "data" / "runtime"
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    )


settings = Settings()
