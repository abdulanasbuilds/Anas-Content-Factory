from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .config import factory_config
from .media import binary


_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")


def parse_silencedetect(stderr: str):
    starts = []
    ranges = []
    for line in str(stderr or "").splitlines():
        match = _START_RE.search(line)
        if match:
            starts.append(float(match.group(1)))
            continue
        match = _END_RE.search(line)
        if not match:
            continue
        end = float(match.group(1))
        start = starts.pop(0) if starts else max(0.0, end)
        ranges.append(
            {
                "start": round(start, 3),
                "end": round(max(start, end), 3),
                "duration": round(max(0.0, end - start), 3),
            }
        )
    return ranges


def detect_silence(audio: Path, threshold_db=None, min_seconds=None):
    policy = factory_config().get("silence", {})
    threshold_db = float(
        policy.get("threshold_db", -35) if threshold_db is None else threshold_db
    )
    min_seconds = float(
        policy.get("min_seconds", 1.2) if min_seconds is None else min_seconds
    )
    cmd = [
        binary("FFMPEG_BIN", "ffmpeg"),
        "-hide_banner",
        "-i",
        str(audio),
        "-af",
        f"silencedetect=noise={threshold_db}dB:d={min_seconds}",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    ranges = parse_silencedetect(result.stderr)
    return {
        "audio": str(audio.resolve()),
        "threshold_db": threshold_db,
        "min_seconds": min_seconds,
        "silence": ranges,
        "command_ok": result.returncode == 0,
    }


def analyze_job_audio(job: Path, manifest: dict):
    output = job / "analysis" / "silence.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    sources = []

    for item in manifest.get("files", []):
        source = Path(item["path"])
        if source.suffix.lower() not in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mts", ".m2ts"}:
            continue
        audio = job / "working" / "audio" / f"{source.stem}.wav"
        if not audio.exists():
            continue
        try:
            result = detect_silence(audio)
            sources.append(
                {
                    "source": str(source.resolve()),
                    "audio": str(audio.resolve()),
                    "threshold_db": result["threshold_db"],
                    "min_seconds": result["min_seconds"],
                    "silence": result["silence"],
                    "command_ok": result["command_ok"],
                }
            )
        except OSError as exc:
            sources.append(
                {
                    "source": str(source.resolve()),
                    "audio": str(audio.resolve()),
                    "silence": [],
                    "command_ok": False,
                    "error": str(exc),
                }
            )

    data = {"version": 1, "sources": sources}
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data
