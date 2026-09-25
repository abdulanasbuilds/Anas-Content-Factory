from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .editor import render_plan
from .export_profiles import get_profile
from .media import binary, probe


def _transcode(source: Path, destination: Path, profile_key: str, profile: dict):
    if destination.exists() and destination.stat().st_size > 0:
        return True
    destination.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={profile['width']}:{profile['height']}:force_original_aspect_ratio=increase,"
        f"crop={profile['width']}:{profile['height']}"
    )
    cmd = [
        binary("FFMPEG_BIN", "ffmpeg"),
        "-y", "-i", str(source),
        "-vf", vf,
        "-r", str(profile["fps"]),
        "-c:v", "libx264", "-preset", "medium", "-crf", str(profile["crf"]),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", profile["audio_bitrate"], "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(destination),
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0 or not destination.exists() or destination.stat().st_size == 0:
        raise RuntimeError("Delivery transcode failed: " + result.stderr[-1400:])
    return True


def deliver(job: Path, plan: dict, outputs=None):
    names = outputs or ["youtube_1080p"]
    delivery_root = job / "delivery"
    delivery_root.mkdir(parents=True, exist_ok=True)
    master = job / "exports" / "master_1080p.mp4"

    if not master.exists() or master.stat().st_size == 0:
        render_plan(job, plan, "master_1080p", master)

    locations = []
    manifests = []
    for requested in names:
        profile_key, profile = get_profile(requested)
        if profile_key == "master_1080p":
            destination = delivery_root / "master_1080p.mp4"
            if not destination.exists():
                destination.write_bytes(master.read_bytes())
        else:
            destination = delivery_root / f"{profile_key}.mp4"
            _transcode(master, destination, profile_key, profile)
        locations.append(str(destination))
        manifests.append({
            "profile": profile_key,
            "path": str(destination),
            "probe": probe(destination),
        })

    (delivery_root / "delivery-manifest.json").write_text(
        json.dumps({"version": 1, "outputs": manifests}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return locations
