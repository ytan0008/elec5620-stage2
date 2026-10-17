from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./elec5620.db"
    jwt_secret: str = "local-secret-change-before-deploying"
    # Forces the built-in local engine even when a key is present (used by the automated tests).
    demo_mode: bool = False
    openai_api_key: str = ""
    # Any OpenAI-compatible chat endpoint (e.g. DeepSeek, Qwen, a local gateway). Empty means api.openai.com.
    openai_base_url: str = ""
    llm_model: str = "gpt-6-luna"
    # GPT-6 models take a reasoning effort (none | low | medium | high). Conversation uses the fast setting;
    # scoring, plans and quality verdicts use the scoring setting. Leave both empty for models without reasoning.
    llm_reasoning_effort: str = "none"
    llm_scoring_effort: str = "low"
    # The Responses API supports tools together with reasoning. Set false for providers that only offer Chat Completions.
    llm_use_responses_api: bool = True
    # Maximum tool-call rounds an agent may take before it must submit its structured answer.
    agent_tool_rounds: int = 3
    # Cloud speech needs an endpoint with /audio/speech and /audio/transcriptions (OpenAI by default).
    server_speech: bool = True
    speech_base_url: str = ""
    tts_model: str = "gpt-4o-mini-tts"
    transcription_model: str = "whisper-1"
    # Offline speech recognition (faster-whisper) for answers when no cloud key is set or the cloud fails.
    # It does not depend on the browser's online recognition service.
    local_stt: bool = True
    local_stt_model: str = "base.en"
    local_stt_dir: str = "models"
    quality_threshold: float = 0.70
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    instructor_email: str = "instructor@example.com"
    instructor_password: str = "ChangeMe123!"
    public_base_url: str = "http://localhost:8080"
    # Show password-reset links on screen when no SMTP server is configured. Local use only.
    password_reset_link_on_screen: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def has_api_key(self) -> bool:
        """False for an empty key or the shared placeholder (e.g. 'xxx' in .env.example)."""
        key = self.openai_api_key.strip()
        return bool(key) and key.lower() not in ("xxx", "your-key-here", "sk-xxx") and not set(key.lower()) <= {"x"}

    @property
    def ai_mode(self) -> str:
        """REAL when a cloud model is configured, otherwise the built-in LOCAL engine."""
        return "REAL" if self.has_api_key and not self.demo_mode else "LOCAL"


@lru_cache
def settings() -> Settings:
    return Settings()
