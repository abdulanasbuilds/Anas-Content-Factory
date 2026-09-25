from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path

def transcribe(audio: Path, output_json: Path) -> bool:
    binary = os.getenv("WHISPER_BIN") or shutil.which("whisper-cli") or shutil.which("whisper")
    model = os.getenv("WHISPER_MODEL", "models/ggml-base.en.bin")
    if not binary:
        return False
    output_json.parent.mkdir(parents=True, exist_ok=True)
    prefix = output_json.with_suffix("")
    try:
        subprocess.run(
            [binary, "-m", model, "-f", str(audio), "-oj", "-of", str(prefix)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        return output_json.exists()
    except Exception:
        return False
