from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from .export_profiles import get_profile
from .media import binary, duration, has_audio


class EditPlanError(RuntimeError):
    pass


def _num(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _profile_filter(profile, reframe=None):
    width = profile["width"]
    height = profile["height"]
    reframe = reframe or {}
    mode = str(reframe.get("mode", "center")).lower()
    x = _num(reframe.get("x"), 0.5)
    y = _num(reframe.get("y"), 0.5)
    if mode == "left":
        x = 0.2
    elif mode == "right":
        x = 0.8
    elif mode == "top":
        y = 0.2
    elif mode == "bottom":
        y = 0.8
    x = min(1.0, max(0.0, x))
    y = min(1.0, max(0.0, y))
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}:(iw-{width})*{x}:(ih-{height})*{y}"
    )


def _escape_filter_path(path: Path):
    slash = chr(92)
    value = str(path.resolve()).replace(slash, "/")
    value = value.replace(":", slash + ":")
    value = value.replace("'", slash + "'")
    return value


def _caption_filter(job: Path, source: Path, start: float, end: float):
    from .transcription import write_srt

    transcript_path = job / "analysis" / "transcripts" / f"{source.stem}.json"
    if not transcript_path.exists():
        return None
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    srt = job / "working" / "captions" / f"{source.stem}_{int(start * 1000)}_{int(end * 1000)}.srt"
    if not write_srt(transcript, srt, start=start, end=end):
        return None
    return (
        f"subtitles='{_escape_filter_path(srt)}':"
        "force_style='FontSize=22,Outline=2,Alignment=2,MarginV=48'"
    )


def _graphics_filter(item):
    graphics = item.get("graphics")
    if not isinstance(graphics, dict):
        return None
    text = str(graphics.get("text", "")).strip()
    font = graphics.get("font_file")
    if not text or not font or not Path(font).exists():
        return None
    safe_text = text.replace("'", chr(92) + "'").replace(":", chr(92) + ":")
    position = str(graphics.get("position", "bottom")).lower()
    if position == "top":
        y = "80"
    elif position == "center":
        y = "(h-text_h)/2"
    else:
        y = "h-text_h-80"
    return (
        f"drawtext=fontfile='{_escape_filter_path(Path(font))}':"
        f"text='{safe_text}':x=(w-text_w)/2:y={y}:fontsize=44:"
        "fontcolor=white:borderw=3:bordercolor=black@0.65"
    )


def resolve_source(source_ref, manifest, input_path: Path):
    candidates = [Path(item["path"]) for item in manifest.get("files", [])]
    candidate_names = {item.name: item for item in candidates}
    raw = Path(str(source_ref))
    if raw.exists():
        return raw.resolve()
    if raw.name in candidate_names:
        return candidate_names[raw.name].resolve()
    if not raw.is_absolute():
        root = input_path if input_path.is_dir() else input_path.parent
        relative = root / raw
        if relative.exists():
            return relative.resolve()
    raise EditPlanError(f"Source media not found: {source_ref}")


def validate_plan(plan: dict, manifest: dict, input_path: Path):
    if not isinstance(plan, dict):
        raise EditPlanError("Edit plan is not an object.")
    decisions = plan.get("edit_decisions") or plan.get("timeline") or []
    if not isinstance(decisions, list):
        raise EditPlanError("edit_decisions must be a list.")

    normalized = []
    durations = {}
    for index, item in enumerate(decisions):
        if not isinstance(item, dict):
            continue
        source_ref = item.get("source") or item.get("path")
        if not source_ref:
            raise EditPlanError(f"Decision {index + 1} is missing source.")
        source = resolve_source(source_ref, manifest, input_path)
        if source.suffix.lower() not in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mts", ".m2ts"}:
            continue
        start = _num(item.get("start"), 0.0)
        end = _num(item.get("end"))
        if start is None or start < 0:
            raise EditPlanError(f"Decision {index + 1} has an invalid start.")
        if source not in durations:
            durations[source] = duration(source)
        total = durations[source]
        if end is None:
            end = total
        if end <= start:
            raise EditPlanError(f"Decision {index + 1} ends before it starts.")
        if total > 0 and end > total + 0.25:
            raise EditPlanError(
                f"Decision {index + 1} ends at {end:.3f}s but {source.name} is only {total:.3f}s long."
            )
        action = str(item.get("action") or item.get("operation") or "keep").lower()
        if action in {"remove", "delete", "skip"}:
            continue
        normalized.append(
            {
                **item,
                "source": str(source),
                "start": round(start, 3),
                "end": round(end, 3),
                "action": action,
            }
        )
    if not normalized:
        raise EditPlanError("The edit plan contains no usable video decisions.")
    return normalized


def _segment_key(item, profile_key):
    payload = json.dumps({"item": item, "profile": profile_key}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:14]


def _render_segment(job: Path, item: dict, index: int, profile_key: str, profile: dict):
    source = Path(item["source"])
    start = float(item["start"])
    end = float(item["end"])
    out_dir = job / "working" / "segments" / profile_key
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"segment_{index:04d}_{_segment_key(item, profile_key)}.mp4"
    if out.exists() and out.stat().st_size > 0:
        return out, True

    filters = [_profile_filter(profile, item.get("reframe"))]
    if item.get("captions") is True or isinstance(item.get("captions"), dict):
        caption_filter = _caption_filter(job, source, start, end)
        if caption_filter:
            filters.append(caption_filter)
    graphics_filter = _graphics_filter(item)
    if graphics_filter:
        filters.append(graphics_filter)

    vf = ",".join(filters)
    af = "aresample=async=1:first_pts=0,loudnorm=I=-16:TP=-1.5:LRA=11"
    duration_value = max(0.05, end - start)
    ffmpeg = binary("FFMPEG_BIN", "ffmpeg")

    if has_audio(source):
        cmd = [
            ffmpeg, "-y",
            "-ss", f"{start:.3f}",
            "-i", str(source),
            "-t", f"{duration_value:.3f}",
            "-map", "0:v:0", "-map", "0:a:0",
            "-vf", vf, "-af", af,
        ]
    else:
        cmd = [
            ffmpeg, "-y",
            "-ss", f"{start:.3f}",
            "-i", str(source),
            "-f", "lavfi", "-t", f"{duration_value:.3f}",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-map", "0:v:0", "-map", "1:a:0",
            "-vf", vf, "-af", af,
        ]

    cmd += [
        "-r", str(profile["fps"]),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", str(profile["crf"]),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", profile["audio_bitrate"],
        "-ar", "48000",
        "-ac", "2",
        "-movflags", "+faststart",
        str(out),
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise EditPlanError(
            f"FFmpeg failed rendering segment {index + 1}: "
            + result.stderr[-1200:]
        )
    return out, False


def render_plan(job: Path, plan: dict, profile_name: str, output_path: Path):
    state = json.loads((job / "project.json").read_text(encoding="utf-8"))
    manifest = json.loads((job / "analysis" / "media-manifest.json").read_text(encoding="utf-8"))
    input_path = Path(state["input_path"])
    profile_key, profile = get_profile(profile_name)
    decisions = validate_plan(plan, manifest, input_path)

    checkpoint = job / "working" / f"timeline-{profile_key}.json"
    if checkpoint.exists():
        try:
            progress = json.loads(checkpoint.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            progress = {"segments": []}
    else:
        progress = {"version": 1, "profile": profile_key, "segments": []}

    rendered = []
    for index, item in enumerate(decisions):
        segment_path, reused = _render_segment(job, item, index, profile_key, profile)
        rendered.append(segment_path)
        progress["segments"] = [
            *[entry for entry in progress.get("segments", []) if entry.get("index") != index],
            {
                "index": index,
                "source": item["source"],
                "start": item["start"],
                "end": item["end"],
                "path": str(segment_path),
                "status": "reused" if reused else "rendered",
            },
        ]
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")

    concat = job / "working" / f"concat-{profile_key}.txt"
    slash = chr(92)
    lines = []
    for segment in rendered:
        value = str(segment.resolve()).replace(slash, "/")
        value = value.replace("'", "'" + slash + "'")
        lines.append("file '" + value + "'")
    concat.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and output_path.stat().st_size > 0:
        output_path.unlink()

    cmd = [
        binary("FFMPEG_BIN", "ffmpeg"),
        "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat),
        "-c", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
        raise EditPlanError("FFmpeg failed concatenating the timeline: " + result.stderr[-1600:])

    render_manifest = {
        "version": 1,
        "profile": profile_key,
        "output": str(output_path),
        "segments": [
            {
                "index": i,
                "source": decisions[i]["source"],
                "start": decisions[i]["start"],
                "end": decisions[i]["end"],
                "captions_burned": bool(decisions[i].get("captions")),
                "action": decisions[i].get("action", "keep"),
            }
            for i in range(len(decisions))
        ],
    }
    manifest_path = output_path.with_suffix(".render.json")
    manifest_path.write_text(json.dumps(render_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path, render_manifest
