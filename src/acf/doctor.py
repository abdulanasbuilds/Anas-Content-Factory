from __future__ import annotations

import json
import shutil
from pathlib import Path

from .config import env, jobs_dir
from .providers import Gemini, OpenRouter


def run():
    checks = []

    def add(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    ffmpeg = env("FFMPEG_BIN") or shutil.which("ffmpeg")
    ffprobe = env("FFPROBE_BIN") or shutil.which("ffprobe")
    whisper = env("WHISPER_BIN") or shutil.which("whisper-cli") or shutil.which("whisper")
    model = env("WHISPER_MODEL")

    add("python", True, "Python runtime is active.")
    add("jobs_dir", jobs_dir().exists(), str(jobs_dir()))
    add("ffmpeg", bool(ffmpeg), str(ffmpeg or "not found"))
    add("ffprobe", bool(ffprobe), str(ffprobe or "not found"))
    add("gemini_key", Gemini().available(), "configured" if Gemini().available() else "not configured")
    add("openrouter_key", OpenRouter().available(), "configured" if OpenRouter().available() else "not configured")
    add("whisper_binary", bool(whisper), str(whisper or "optional and not found"))
    add("whisper_model", bool(model and Path(model).exists()), model or "optional and not configured")

    providers_ok = Gemini().available() or OpenRouter().available()
    required_ok = bool(ffmpeg) and bool(ffprobe) and providers_ok
    return {"passed": required_ok, "checks": checks}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
