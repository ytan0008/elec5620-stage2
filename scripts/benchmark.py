"""Performance measurements behind docs/PERFORMANCE.md.

    python scripts/benchmark.py <audio-folder>

The audio folder holds clipN.wav recordings with the spoken text in clipN.txt (docs/PERFORMANCE.md says how ours
were made). The script applies the migrations to a fresh SQLite database, starts the backend on port 8010
(LOCAL engine, offline speech recognition on), measures speech recognition, API latency and the agents' own
step timings, and prints a JSON summary."""
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

import requests

AUDIO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("bench-audio")
DB = Path(tempfile.gettempdir()) / "certifyai-bench.db"
BASE = "http://127.0.0.1:8010"
ESSAY = ("Some people believe that technology has made our lives more complicated, but I think it has mostly made them easier. "
         "For example, online banking saves time and allows people to manage money from home, while video calls let families stay in touch. ") * 8


def words(text):
    return re.findall(r"[a-z']+", text.lower())


def wer(ref, hyp):
    r, h = words(ref), words(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / len(r)


def timed(fn, n):
    out = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t) * 1000)
    return out


def summary(ms):
    ms = sorted(ms)
    return {"n": len(ms), "median_ms": round(statistics.median(ms), 1), "p95_ms": round(ms[max(0, int(len(ms) * .95) - 1)], 1), "max_ms": round(ms[-1], 1)}


def main():
    DB.unlink(missing_ok=True)
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{DB.as_posix()}", "DEMO_MODE": "true", "LOCAL_STT": "true", "PYTHONIOENCODING": "utf-8"}
    t0 = time.perf_counter()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True, capture_output=True)
    t0 = time.perf_counter()
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8010", "--log-level", "warning"], env=env)
    try:
        for _ in range(300):
            try:
                if requests.get(BASE + "/api/health", timeout=1).ok:
                    break
            except requests.RequestException:
                time.sleep(.1)
        result = {"backend_ready_s": round(time.perf_counter() - t0, 2)}
        reg = requests.post(BASE + "/api/auth/register", json={"email": "bench@example.com", "name": "Bench", "password": "Example123!", "exam": "IELTS", "proficiency": "intermediate",
                                                                "target_score": 7, "exam_date": "2026-12-15", "weekly_hours": 8, "priority_skills": ["writing", "speaking"]}).json()
        h = {"Authorization": "Bearer " + reg["token"]}

        # --- offline speech recognition (faster-whisper base.en, int8, CPU)
        stt = []
        for clip in sorted(AUDIO.glob("clip*.wav")):
            ref = (clip.with_suffix(".txt")).read_text(encoding="utf-8-sig").strip()
            with wave.open(str(clip)) as w:
                seconds = w.getnframes() / w.getframerate()
            t = time.perf_counter()
            text = requests.post(BASE + "/api/stt", headers=h, files={"file": (clip.name, clip.read_bytes(), "audio/wav")}).json()["text"]
            took = time.perf_counter() - t
            stt.append({"clip": clip.name, "audio_s": round(seconds, 1), "transcribe_s": round(took, 2), "real_time_factor": round(took / seconds, 2), "wer": round(wer(ref, text), 3), "text": text})
        result["stt_first_request_includes_model_load"] = stt[0]["transcribe_s"]
        # warm runs
        warm = []
        for clip in sorted(AUDIO.glob("clip*.wav")):
            ref = clip.with_suffix(".txt").read_text(encoding="utf-8-sig").strip()
            with wave.open(str(clip)) as w:
                seconds = w.getnframes() / w.getframerate()
            t = time.perf_counter()
            text = requests.post(BASE + "/api/stt", headers=h, files={"file": (clip.name, clip.read_bytes(), "audio/wav")}).json()["text"]
            took = time.perf_counter() - t
            warm.append({"clip": clip.name, "audio_s": round(seconds, 1), "transcribe_s": round(took, 2), "real_time_factor": round(took / seconds, 2), "wer": round(wer(ref, text), 3), "text": text})
        result["stt_warm"] = warm

        # --- other requests stay responsive while a long answer is transcribed (run_in_threadpool)
        long_clip = sorted(AUDIO.glob("clip*.wav"))[-1]
        during, done = [], threading.Event()

        def transcribe():
            requests.post(BASE + "/api/stt", headers=h, files={"file": (long_clip.name, long_clip.read_bytes(), "audio/wav")})
            done.set()
        th = threading.Thread(target=transcribe)
        t = time.perf_counter()
        th.start()
        time.sleep(.05)
        while not done.is_set():
            during.append(timed(lambda: requests.get(BASE + "/api/health"), 1)[0])
            time.sleep(.05)
        th.join()
        result["health_during_transcription"] = {**summary(during), "transcription_s": round(time.perf_counter() - t, 2)}

        # --- API latency (LOCAL engine, real HTTP, same machine)
        api = {}
        api["GET /api/me"] = summary(timed(lambda: requests.get(BASE + "/api/me", headers=h), 30))
        api["POST /api/chat/tutor (agent reply)"] = summary(timed(lambda: requests.post(BASE + "/api/chat/tutor", headers=h, json={"message": "How can I improve my writing coherence?"}), 10))
        api["POST /api/plans/generate (Coordinator + Assessment + Quality)"] = summary(timed(lambda: requests.post(BASE + "/api/plans/generate", headers=h), 5))
        plan = requests.post(BASE + "/api/plans/generate", headers=h).json()
        requests.post(BASE + f"/api/plans/{plan['id']}/decision?accept=true", headers=h)

        def writing():
            task = requests.post(BASE + "/api/practice/writing", headers=h).json()
            r = requests.post(BASE + f"/api/practice/{task['id']}/submit", headers=h, json={"text": ESSAY})
            assert r.ok, r.text
        api["Writing submit (Tutor + Assessment + Quality gate)"] = summary(timed(writing, 10))
        api["GET /api/analytics"] = summary(timed(lambda: requests.get(BASE + "/api/analytics", headers=h), 10))
        api["POST /api/reports (Assessment report)"] = summary(timed(lambda: requests.post(BASE + "/api/reports", headers=h), 5))
        api["POST /api/mock-exams (prepare mock)"] = summary(timed(lambda: (requests.post(BASE + "/api/mock-exams", headers=h).json(), requests.post(BASE + f"/api/mock-exams/{requests.get(BASE + '/api/mock-exams', headers=h).json()[0]['id']}/end", headers=h, json={})), 3))
        result["api"] = api
    finally:
        server.terminate()
        server.wait(10)

    # --- per-agent step timings recorded by the agents themselves (AgentEvent.duration_ms)
    import sqlite3
    con = sqlite3.connect(DB)
    rows = con.execute("select agent, duration_ms from agent_execution_events where duration_ms > 0").fetchall()
    con.close()
    agents = {}
    for agent, ms in rows:
        agents.setdefault(agent, []).append(ms)
    result["agent_steps"] = {a: summary(v) for a, v in sorted(agents.items())}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
