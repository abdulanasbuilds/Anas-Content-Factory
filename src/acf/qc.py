from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .export_profiles import get_profile
from .media import binary, probe


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def _run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _fps(stream):
    raw = stream.get("r_frame_rate", "0/1")
    try:
        a, b = raw.split("/", 1)
        return float(a) / float(b)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _stream(data, kind):
    return next((item for item in data.get("streams", []) if item.get("codec_type") == kind), None)


def _volume(output):
    mean = None
    peak = None
    for line in output.splitlines():
        if "mean_volume:" in line:
            try:
                mean = float(line.split("mean_volume:", 1)[1].split("dB", 1)[0].strip())
            except ValueError:
                pass
        if "max_volume:" in line:
            try:
                peak = float(line.split("max_volume:", 1)[1].split("dB", 1)[0].strip())
            except ValueError:
                pass
    return mean, peak


def _black_frames(output):
    spans = []
    for line in output.splitlines():
        if "black_start:" not in line or "black_end:" not in line:
            continue
        try:
            start = float(line.split("black_start:", 1)[1].split()[0])
            end = float(line.split("black_end:", 1)[1].split()[0])
            spans.append({"start": start, "end": end, "duration": max(0.0, end - start)})
        except (ValueError, IndexError):
            continue
    return spans


def check_file(path: Path, expected_profile: str | None = None, captions_required: bool = False):
    report = {
        "file": str(path),
        "passed": True,
        "checks": [],
    }

    def check(name, passed, detail):
        report["checks"].append({"name": name, "passed": bool(passed), "detail": detail})
        report["passed"] = report["passed"] and bool(passed)

    if not path.exists():
        check("exists", False, "File does not exist.")
        return report
    size = path.stat().st_size
    check("non_empty", size > 0, f"size={size}")

    data = probe(path)
    video = _stream(data, "video")
    audio = _stream(data, "audio")
    format_data = data.get("format", {})
    try:
        duration_value = float(format_data.get("duration", 0))
    except (TypeError, ValueError):
        duration_value = 0.0
    check("duration", duration_value > 0, f"duration={duration_value:.3f}s")
    check("video_stream", video is not None, "video stream present")
    check("audio_stream", audio is not None, "audio stream present")

    if video is not None:
        width = int(video.get("width", 0) or 0)
        height = int(video.get("height", 0) or 0)
        fps = _fps(video)
        check("dimensions", width > 0 and height > 0, f"{width}x{height}")
        if expected_profile:
            key, profile = get_profile(expected_profile)
            expected_ratio = profile["width"] / profile["height"]
            actual_ratio = width / height if height else 0
            ratio_ok = abs(actual_ratio - expected_ratio) / expected_ratio < 0.025 if expected_ratio else False
            fps_ok = abs(fps - profile["fps"]) < 0.6
            check("aspect_ratio", ratio_ok, f"actual={actual_ratio:.4f}, expected={expected_ratio:.4f}")
            check("frame_rate", fps_ok, f"actual={fps:.3f}, expected={profile['fps']}")
            check("profile_dimensions", width == profile["width"] and height == profile["height"], f"actual={width}x{height}, expected={profile['width']}x{profile['height']}")

    decode = _run([binary("FFMPEG_BIN", "ffmpeg"), "-v", "error", "-i", str(path), "-f", "null", "-"])
    check("decode_integrity", decode.returncode == 0, decode.stderr[-1000:] or "decode passed")

    if audio is not None:
        volume = _run([
            binary("FFMPEG_BIN", "ffmpeg"), "-v", "error", "-i", str(path),
            "-af", "volumedetect", "-vn", "-f", "null", "-"
        ])
        mean, peak = _volume(volume.stderr)
        check("not_silent", peak is not None and peak > -55.0, f"mean_volume={mean}, max_volume={peak}")
        check("not_clipped", peak is not None and peak < -0.05, f"max_volume={peak}")
    else:
        mean, peak = None, None

    if video is not None:
        black = _run([
            binary("FFMPEG_BIN", "ffmpeg"), "-v", "info", "-i", str(path),
            "-vf", "blackdetect=d=1:pix_th=0.10", "-an", "-f", "null", "-"
        ])
        spans = _black_frames(black.stderr)
        long_black = [span for span in spans if span["duration"] >= 2.0]
        check("black_frames", not long_black, f"long_black_spans={long_black[:5]}")

    render_manifest = path.with_suffix(".render.json")
    if captions_required:
        captions_burned = False
        if render_manifest.exists():
            try:
                render = json.loads(render_manifest.read_text(encoding="utf-8"))
                captions_burned = all(item.get("captions_burned") for item in render.get("segments", []))
            except json.JSONDecodeError:
                pass
        check("captions", captions_burned, "caption render metadata confirms burned captions")

    return report


def run(job: Path):
    reports = []
    targets = []
    review_manifest = job / "review" / "review-manifest.json"
    if review_manifest.exists():
        try:
            data = json.loads(review_manifest.read_text(encoding="utf-8"))
            targets.append((Path(data["output"]), "review", False))
        except (KeyError, json.JSONDecodeError):
            pass

    for path in (job / "delivery").glob("*.mp4"):
        targets.append((path, path.stem, False))

    shorts_manifest = job / "exports" / "shorts" / "shorts-manifest.json"
    if shorts_manifest.exists():
        try:
            data = json.loads(shorts_manifest.read_text(encoding="utf-8"))
            for item in data.get("shorts", []):
                targets.append((Path(item["path"]), "vertical_1080x1920", True))
        except (KeyError, json.JSONDecodeError):
            pass

    for path, profile, captions in targets:
        reports.append(check_file(path, None if profile == "review" else profile, captions))

    plan_path = job / "decisions" / "edit-plan.json"
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            expected = plan.get("requested_outputs") or []
            delivery_started = (job / "delivery" / "delivery-manifest.json").exists()
            if delivery_started and isinstance(expected, list):
                existing_profiles = {Path(item["file"]).stem for item in reports if item.get("file")}
                for request in expected:
                    name = request.get("profile") if isinstance(request, dict) else request
                    if not name:
                        continue
                    key, _ = get_profile(str(name))
                    if key not in existing_profiles and key not in {"master_1080p"}:
                        reports.append({"file": str(job / "delivery" / f"{key}.mp4"), "passed": False, "checks": [{"name": "expected_output", "passed": False, "detail": "Expected delivery output is missing."}]})
        except Exception as exc:
            reports.append({"file": str(plan_path), "passed": False, "checks": [{"name": "plan_parse", "passed": False, "detail": str(exc)}]})

    passed = all(item.get("passed", False) for item in reports) if reports else False
    payload = {"version": 2, "passed": passed, "reports": reports}
    (job / "analysis" / "qc-report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    lines = ["# QC Report", "", f"Overall: {'PASS' if passed else 'FAIL'}", ""]
    for report in reports:
        lines.append(f"## {report.get('file')}")
        for item in report.get("checks", []):
            mark = "PASS" if item["passed"] else "FAIL"
            lines.append(f"- {mark}: {item['name']} — {item['detail']}")
        lines.append("")
    (job / "analysis" / "qc-report.md").write_text("\n".join(lines), encoding="utf-8")
    return payload
