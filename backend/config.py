from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./elec5620.db"
    jwt_secret: str = "local-demo-secret-change-before-deploying"
    demo_mode: bool = True
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    transcription_model: str = ""
    quality_threshold: float = 0.70
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    instructor_email: str = "instructor@example.com"
    instructor_password: str = "ChangeMe123!"
    public_base_url: str = "http://localhost:8080"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def settings() -> Settings:
    return Settings()
