from __future__ import annotations

import json
from pathlib import Path

from .editor import render_plan
from .export_profiles import get_profile
from .media import probe


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
        destination = delivery_root / f"{profile_key}.mp4"

        if profile_key == "master_1080p":
            if not destination.exists() or destination.stat().st_size == 0:
                destination.write_bytes(master.read_bytes())
        elif profile_key == "youtube_1080p":
            if not destination.exists() or destination.stat().st_size == 0:
                destination.write_bytes(master.read_bytes())
        else:
            # Render non-landscape outputs directly from the editorial plan so
            # the plan's reframing/focal-point decisions are preserved.
            render_plan(job, plan, profile_key, destination)

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
