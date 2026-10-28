"""Offline speech recognition: browser recordings are decoded and passed to the local Whisper model."""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_suite.db"
os.environ["DEMO_MODE"] = "true"
import math
import struct
import wave
from backend import speech
from backend.config import settings


def tone(path, seconds=1.0, rate=8000):
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(rate)
        out.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(int(seconds * rate))))


def test_recordings_are_decoded_to_16k_mono(tmp_path):
    path = tmp_path / "answer.wav"
    tone(path, seconds=1.0)
    audio = speech.decode_audio(path)
    assert audio.dtype.name == "float32" and abs(len(audio) - 16000) < 400  # resampled from 8 kHz to 16 kHz
    assert 0.1 < float(abs(audio).max()) <= 1.0


def test_offline_model_is_used_without_a_cloud_key(tmp_path, monkeypatch):
    path = tmp_path / "answer.wav"
    tone(path, seconds=1.5)

    class Segment:
        text = " I would like to talk about my hometown. "

    class Model:
        def transcribe(self, audio, **options):
            assert options["language"] == "en" and len(audio) > 16000
            return [Segment()], None

    monkeypatch.setattr(settings(), "local_stt", True)
    monkeypatch.setattr(speech, "_local_model", lambda: Model())
    assert speech.server_speech_available() is False and speech.stt_available() is True
    assert speech.transcribe(path) == "I would like to talk about my hometown."
    tiny = tmp_path / "click.wav"
    tone(tiny, seconds=0.05)
    assert speech.transcribe(tiny) == ""  # too short to be speech
