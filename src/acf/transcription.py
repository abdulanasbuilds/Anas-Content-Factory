from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def _timestamp(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number / 1000.0 if number > 1000 else number
    text = str(value).strip().replace(",", ".")
    parts = text.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(text)
    except ValueError:
        return None


def _clean_text(text):
    value = " ".join(str(text or "").split()).strip()
    for mark in [",", ".", "!", "?", ";", ":"]:
        value = value.replace(" " + mark, mark)
    return value


def _raw_segments(raw):
    for key in ("segments", "transcription", "results"):
        value = raw.get(key) if isinstance(raw, dict) else None
        if isinstance(value, list):
            return value
    return []


def normalize_whisper(raw: dict, source: str | None = None):
    normalized = []
    for item in _raw_segments(raw):
        if not isinstance(item, dict):
            continue
        offsets = item.get("offsets") or {}
        timestamps = item.get("timestamps") or {}
        start = _timestamp(item.get("start", timestamps.get("from", offsets.get("from"))))
        end = _timestamp(item.get("end", timestamps.get("to", offsets.get("to"))))
        text = _clean_text(item.get("text") or item.get("sentence") or "")
        if start is None or end is None or not text:
            continue
        words = []
        for word in item.get("words") or []:
            if not isinstance(word, dict):
                continue
            ws = _timestamp(word.get("start"))
            we = _timestamp(word.get("end"))
            wt = _clean_text(word.get("word") or word.get("text"))
            if ws is not None and we is not None and wt:
                words.append({"start": ws, "end": we, "text": wt})
        normalized.append(
            {
                "id": f"seg-{len(normalized)+1:05d}",
                "start": round(max(0.0, start), 3),
                "end": round(max(start, end), 3),
                "text": text,
                "speaker": item.get("speaker") or item.get("speaker_id"),
                "confidence": item.get("confidence"),
                "words": words,
            }
        )
    normalized.sort(key=lambda x: (x["start"], x["end"]))
    return {
        "version": 1,
        "source": source,
        "language": raw.get("language") if isinstance(raw, dict) else None,
        "segments": normalized,
    }


def format_time(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    ms = total_ms % 1000
    total = total_ms // 1000
    s = total % 60
    m = (total // 60) % 60
    h = total // 3600
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def srt_time(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    ms = total_ms % 1000
    total = total_ms // 1000
    s = total % 60
    m = (total // 60) % 60
    h = total // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def render_markdown(transcript: dict) -> str:
    lines = ["# Transcript", ""]
    if transcript.get("source"):
        lines += [f"Source: {transcript['source']}", ""]
    for segment in transcript.get("segments", []):
        speaker = f"{segment['speaker']} " if segment.get("speaker") else ""
        lines.append(
            f"- {format_time(segment['start'])} -> {format_time(segment['end'])} {speaker}{segment['text']}"
        )
    lines.append("")
    return "\n".join(lines)


def write_srt(transcript: dict, destination: Path, start: float = 0.0, end: float | None = None):
    cues = []
    for segment in transcript.get("segments", []):
        if segment["end"] <= start:
            continue
        if end is not None and segment["start"] >= end:
            break
        cue_start = max(segment["start"], start) - start
        cue_end = (min(segment["end"], end) if end is not None else segment["end"]) - start
        if cue_end <= cue_start:
            continue
        cues.append((cue_start, cue_end, segment["text"]))
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for idx, (cue_start, cue_end, text) in enumerate(cues, 1):
        lines += [str(idx), f"{srt_time(cue_start)} --> {srt_time(cue_end)}", text, ""]
    destination.write_text("\n".join(lines), encoding="utf-8")
    return bool(cues)


def normalize_file(raw_path: Path, destination: Path, source: str | None = None):
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    normalized = normalize_whisper(raw, source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
    return normalized


def transcribe(audio: Path, output_json: Path) -> bool:
    binary = os.getenv("WHISPER_BIN") or shutil.which("whisper-cli") or shutil.which("whisper")
    model = os.getenv("WHISPER_MODEL")
    if not binary or not model or not Path(model).exists():
        return False
    output_json.parent.mkdir(parents=True, exist_ok=True)
    raw_prefix = output_json.parent / f"{output_json.stem}.raw"
    raw_json = Path(str(raw_prefix) + ".json")
    try:
        subprocess.run(
            [binary, "-m", model, "-f", str(audio), "-oj", "-of", str(raw_prefix)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if not raw_json.exists():
            candidates = list(output_json.parent.glob(raw_prefix.name + "*.json"))
            if candidates:
                raw_json = candidates[0]
        if not raw_json.exists():
            return False
        normalize_file(raw_json, output_json, str(audio))
        return output_json.exists()
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return False
