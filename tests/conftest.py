import os

# Keep the suite fast and offline: the Whisper model is not loaded during tests (tests/test_speech.py uses a stub).
os.environ.setdefault("LOCAL_STT", "false")
