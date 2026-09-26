from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from .config import factory_config


VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mts", ".m2ts"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def binary(env_name, default):
    return os.getenv(env_name) or shutil.which(default) or default


def run(cmd, check=True):
    return subprocess.run(
        cmd,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def discover(root: Path):
    if root.is_file():
        return [root]
    allowed = VIDEO_EXTS | AUDIO_EXTS | IMAGE_EXTS
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in allowed)


def probe(path: Path):
    cmd = [
        binary("FFPROBE_BIN", "ffprobe"),
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        str(path),
    ]
    try:
        return json.loads(run(cmd).stdout)
    except Exception as exc:
        return {"error": str(exc)}


def duration(path: Path) -> float:
    data = probe(path)
    try:
        return float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        return 0.0


def has_audio(path: Path) -> bool:
    data = probe(path)
    return any(stream.get("codec_type") == "audio" for stream in data.get("streams", []))


def write_manifest(files, destination: Path):
    manifest = {"version": 2, "files": []}
    for path in files:
        stat = path.stat()
        manifest["files"].append(
            {
                "path": str(path.resolve()),
                "name": path.name,
                "extension": path.suffix.lower(),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "probe": probe(path),
            }
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def extract_audio(source: Path, destination: Path):
    if destination.exists() and destination.stat().st_size > 0:
        return True
    destination.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        binary("FFMPEG_BIN", "ffmpeg"), "-y", "-i", str(source),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(destination),
    ]
    try:
        run(cmd)
        return destination.exists() and destination.stat().st_size > 0
    except Exception:
        return False


def make_proxy(source: Path, destination: Path, width=None):
    if width is None:
        width = int(factory_config().get("resource_policy", {}).get("proxy_width", 1280))
    if destination.exists() and destination.stat().st_size > 0:
        return True
    destination.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        binary("FFMPEG_BIN", "ffmpeg"), "-y", "-i", str(source),
        "-vf", f"scale={width}:-2",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-an",
        str(destination),
    ]
    try:
        run(cmd)
        return destination.exists() and destination.stat().st_size > 0
    except Exception:
        return False


def extract_frame(source: Path, timestamp: float, destination: Path, width=768):
    destination.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        binary("FFMPEG_BIN", "ffmpeg"), "-y",
        "-ss", f"{max(0.0, timestamp):.3f}", "-i", str(source),
        "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "5",
        str(destination),
    ]
    try:
        run(cmd)
        return destination.exists() and destination.stat().st_size > 0
    except Exception:
        return False
