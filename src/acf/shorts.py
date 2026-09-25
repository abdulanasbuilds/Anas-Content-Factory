from __future__ import annotations

import json
import re
from pathlib import Path

from .editor import render_plan
from .providers import ProviderError, extract_json, generate


def _slug(value):
    value = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "short")).strip("-").lower()
    return value[:70] or "short"


def _load_transcript_text(job: Path):
    path = job / "analysis" / "transcript.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    return "\n".join(
        f"{item['start']:.3f}-{item['end']:.3f}: {item['text']}"
        for item in data.get("segments", [])
    )


def _fallback_candidates(plan):
    candidates = []
    for item in plan.get("highlights", []) or []:
        if not isinstance(item, dict):
            continue
        start = item.get("start")
        end = item.get("end")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
            candidates.append(
                {
                    "title": item.get("title") or "Highlight",
                    "source": item.get("source"),
                    "start": start,
                    "end": min(end, start + 60),
                    "hook": item.get("reason") or item.get("description", ""),
                    "reframe": {"x": 0.5, "y": 0.5},
                    "confidence": 0.5,
                }
            )
    return candidates[:5]


def generate_candidates(job: Path, plan: dict):
    transcript = _load_transcript_text(job)
    scenes_path = job / "analysis" / "scenes.json"
    scenes = scenes_path.read_text(encoding="utf-8")[:18000] if scenes_path.exists() else ""
    prompt = (
        "You are the Shorts producer for Anas Content Factory. "
        "Select self-contained short-form moments from the existing edit material. "
        "Do not invent timestamps or source names. Prefer strong hooks, useful statements, "
        "emotion, surprising facts, or a clean beginning-middle-end. Keep each candidate "
        "between 20 and 60 seconds. Return JSON only: {shorts:[{title,source,start,end,hook,reframe,confidence}]}."
        "\nCURRENT PLAN:\n" + json.dumps(plan, indent=2, ensure_ascii=False)[:25000]
        + "\nTRANSCRIPT:\n" + transcript[:30000]
        + "\nVISUAL SCENES:\n" + scenes
    )
    try:
        raw, provider = generate(prompt)
        data = extract_json(raw)
        candidates = data.get("shorts", []) if isinstance(data, dict) else []
        valid = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            try:
                start = float(candidate["start"])
                end = float(candidate["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if end <= start or end - start < 8:
                continue
            valid.append(
                {
                    "title": candidate.get("title") or "Short",
                    "source": candidate.get("source"),
                    "start": start,
                    "end": min(end, start + 60),
                    "hook": candidate.get("hook", ""),
                    "reframe": candidate.get("reframe") or {"x": 0.5, "y": 0.5},
                    "confidence": candidate.get("confidence", 0.0),
                }
            )
        return valid[:6], provider, None
    except ProviderError as exc:
        return _fallback_candidates(plan), None, str(exc)


def render_candidates(job: Path, candidates: list[dict]):
    root = job / "exports" / "shorts"
    root.mkdir(parents=True, exist_ok=True)
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
                    "captions": True,
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
            }
        )
    (root / "shorts-manifest.json").write_text(
        json.dumps({"version": 1, "shorts": rendered}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return rendered
