"""Server-side speech: cloud text-to-speech (cached) and speech-to-text.

Both are optional. When unavailable the browser renders speech with the Web
Speech API, so listening audio and spoken replies still work offline.
"""
import hashlib
from pathlib import Path
from backend.config import settings

TTS_DIR = Path("uploads") / "tts"
VOICES = {"narrator": "fable", "female": "nova", "female2": "shimmer", "male": "onyx", "male2": "echo", "witch": "shimmer", "boy": "echo"}


def _client():
    from openai import OpenAI
    config = settings()
    return OpenAI(api_key=config.openai_api_key, base_url=config.speech_base_url or None, timeout=60)


def server_speech_available() -> bool:
    config = settings()
    return config.has_api_key and not config.demo_mode and config.server_speech


def synthesise(text: str, voice: str = "female", speed: float = 1.0) -> Path:
    config = settings()
    voice_id = VOICES.get(voice, voice if voice in VOICES.values() else "nova")
    speed = max(.5, min(1.5, round(speed, 2)))
    key = hashlib.sha256(f"{config.tts_model}|{voice_id}|{speed}|{text}".encode()).hexdigest()
    path = TTS_DIR / f"{key}.mp3"
    if path.is_file():
        return path
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    instructions = {"narrator": "Neutral British exam narrator, clear and measured.", "witch": "Warm, playful and encouraging British tutor.", "boy": "Friendly, upbeat young tutor."}.get(voice)
    kwargs = {"model": config.tts_model, "voice": voice_id, "input": text[:4000], "response_format": "mp3", "speed": speed}
    if instructions and "tts-1" not in config.tts_model:
        kwargs["instructions"] = instructions
    response = _client().audio.speech.create(**kwargs)
    path.write_bytes(response.content if hasattr(response, "content") else response.read())
    return path


def transcribe(path: Path) -> str:
    with path.open("rb") as stream:
        result = _client().audio.transcriptions.create(model=settings().transcription_model or "whisper-1", file=stream, language="en")
    return result.text
