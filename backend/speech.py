"""Server-side speech: cloud text-to-speech (cached) and speech-to-text.

Text-to-speech is optional: without it the browser speaks with the Web Speech
API. Speech-to-text uses the cloud model when a key is set and otherwise (or
when the cloud fails) an offline Whisper model on this server, so answers can
be recognised even where the browser's online recognition service is blocked.
"""
import hashlib
import logging
import threading
from functools import lru_cache
from pathlib import Path
from backend.config import settings

log = logging.getLogger(__name__)

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


def local_stt_available() -> bool:
    if not settings().local_stt:
        return False
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def stt_available() -> bool:
    return server_speech_available() or local_stt_available()


@lru_cache(maxsize=1)
def _local_model():
    from faster_whisper import WhisperModel
    config = settings()
    return WhisperModel(config.local_stt_model, device="cpu", compute_type="int8", download_root=config.local_stt_dir)


def warm_up() -> None:
    """Load the offline model in the background so the first answer is not delayed."""
    if local_stt_available():
        threading.Thread(target=lambda: _safe(_local_model), daemon=True).start()


def _safe(fn):
    try:
        fn()
    except Exception as exc:  # The model can still be loaded on first use.
        log.warning("Offline speech model not loaded yet: %s", exc)


def decode_audio(path: Path):
    """Browser recordings (webm/opus, ogg, mp4, wav) to 16 kHz mono float32, which Whisper expects."""
    import av
    import numpy as np
    chunks = []
    with av.open(str(path)) as container:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        for frame in container.decode(audio=0):
            chunks.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(frame))
        chunks.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(None))
    return (np.concatenate(chunks).astype(np.float32) / 32768.0) if chunks else np.zeros(0, dtype=np.float32)


def transcribe_local(path: Path) -> str:
    audio = decode_audio(path)
    if len(audio) < 1600:  # under 0.1 s
        return ""
    segments, _ = _local_model().transcribe(audio, language="en", beam_size=1, vad_filter=True, condition_on_previous_text=False)
    return " ".join(segment.text.strip() for segment in segments).strip()


def transcribe(path: Path) -> str:
    if server_speech_available():
        try:
            with path.open("rb") as stream:
                result = _client().audio.transcriptions.create(model=settings().transcription_model or "whisper-1", file=stream, language="en")
            return result.text
        except Exception:
            if not local_stt_available():
                raise
    return transcribe_local(path)
