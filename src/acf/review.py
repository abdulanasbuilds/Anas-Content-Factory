from __future__ import annotations

import json
from pathlib import Path

from .editor import render_plan


def render(job: Path, plan: dict):
    output = job / "review" / "review.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    path, manifest = render_plan(job, plan, "review", output)

    notes = {
        "rendered_at": json.loads(
            (job / "project.json").read_text(encoding="utf-8")
        ).get("updated_at"),
        "output": str(path),
        "profile": manifest["profile"],
        "style_profile": manifest.get("style_profile"),
        "motion_beats": manifest.get("motion_beats", []),
        "instructions": [
            "Watch the review render from start to finish.",
            "Check story, pacing, natural speech, audio, framing, captions and obvious missing assets.",
            "Check review/verification.json for the automatic sampled-frame visual verification.",
            'Use acf revise PROJECT "your change" for natural-language revisions.',
        ],
    }

    (job / "review" / "review-notes.md").write_text(
        "# Review Build\n\n"
        f"Review file: {path}\n\n"
        f"Style profile: {manifest.get('style_profile') or 'unknown'}\n\n"
        "## Human/editor checks\n\n"
        + "\n".join(f"- {item}" for item in notes["instructions"])
        + "\n",
        encoding="utf-8",
    )

    (job / "review" / "review-manifest.json").write_text(
        json.dumps(
            {"version": 2, **notes, "render_manifest": manifest},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path, manifest
