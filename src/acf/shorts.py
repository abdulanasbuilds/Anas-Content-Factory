from __future__ import annotations

import json
import re
from pathlib import Path

from .config import factory_config
from .editor import render_plan
from .providers import ProviderError, extract_json, generate


def _slug(value):
    value = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "short")).strip("-").lower()
    return value[:70] or "short"


def generate_candidates(job: Path, plan: dict):
    from .clip_hunter import hunt

    return hunt(job, plan)
def render_candidates(job: Path, candidates: list[dict]):
    root = job / "exports" / "shorts"
    root.mkdir(parents=True, exist_ok=True)
    transcript_available = False
    transcript_path = job / "analysis" / "transcript.json"
    if transcript_path.exists():
        try:
            transcript_available = bool(json.loads(transcript_path.read_text(encoding="utf-8")).get("segments"))
        except json.JSONDecodeError:
            transcript_available = False

    rendered = []
    for index, candidate in enumerate(candidates, 1):
        title = candidate.get("title") or f"Short {index}"
        plan = {
            "project_type": "short-form",
            "summary": candidate.get("hook", ""),
            "requested_outputs": ["vertical_1080x1920"],
            "edit_decisions": [
                {
                    "source": candidate["source"],
                    "start": candidate["start"],
                    "end": candidate["end"],
                    "action": "keep",
                    "captions": transcript_available,
                    "reframe": candidate.get("reframe") or {"x": 0.5, "y": 0.5},
                }
            ],
        }
        output = root / f"{index:02d}-{_slug(title)}.mp4"
        render_plan(job, plan, "vertical_1080x1920", output)
        rendered.append(
            {
                "title": title,
                "path": str(output),
                "source": candidate["source"],
                "start": candidate["start"],
                "end": candidate["end"],
                "hook": candidate.get("hook", ""),
                "confidence": candidate.get("confidence", 0.0),
                "captions": transcript_available,
            }
        )
    (root / "shorts-manifest.json").write_text(
        json.dumps({"version": 1, "shorts": rendered}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return rendered
