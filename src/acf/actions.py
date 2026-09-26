from __future__ import annotations

import json
import re
from pathlib import Path

from .config import factory_config


_ACTIONS = {
    "remove_dead_air": (
        r"\b(remove|cut|trim|delete)\b.*\b(dead\s+air|silence|silent\s+parts|long\s+pauses)\b",
        r"\b(dead\s+air|silence|silent\s+parts)\b",
    ),
    "create_shorts": (
        r"\b(create|make|generate|find)\b.*\b(shorts?|clips?|reels?)\b",
        r"\b(shorts?|reels?)\b.*\b(best|strongest|clips?)\b",
    ),
    "add_captions": (
        r"\b(add|burn|generate)\b.*\b(captions?|subtitles?)\b",
    ),
}


def classify(request: str):
    text = " ".join(str(request or "").lower().split())
    for action, patterns in _ACTIONS.items():
        if any(re.search(pattern, text) for pattern in patterns):
            return action
    return "unknown"


def _load_plan(job: Path):
    return json.loads((job / "decisions" / "edit-plan.json").read_text(encoding="utf-8"))


def _load_silence(job: Path):
    path = job / "analysis" / "silence.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _ranges_for_source(silence_data, source, policy):
    for item in silence_data.get("sources", []):
        if str(Path(item.get("source", "")).resolve()) != str(Path(source).resolve()):
            continue
        maximum = float(policy.get("max_seconds", 8))
        minimum = float(policy.get("min_seconds", 1.2))
        return [
            (float(entry["start"]), float(entry["end"]))
            for entry in item.get("silence", [])
            if float(entry.get("duration", 0)) >= minimum
            and float(entry.get("duration", 0)) <= maximum
        ]
    return []


def remove_dead_air_from_plan(plan: dict, silence_data: dict):
    policy = factory_config().get("silence", {})
    padding = float(policy.get("trim_padding_seconds", 0.12))
    new_decisions = []
    removed = []

    for item in plan.get("edit_decisions", []):
        if not isinstance(item, dict) or str(item.get("action", "keep")).lower() in {"remove", "delete", "skip"}:
            new_decisions.append(item)
            continue

        source = item.get("source")
        if not source:
            new_decisions.append(item)
            continue

        start = float(item.get("start", 0))
        end = float(item.get("end", start))
        ranges = []
        for silence_start, silence_end in _ranges_for_source(silence_data, source, policy):
            cut_start = max(start, silence_start + padding)
            cut_end = min(end, silence_end - padding)
            if cut_end - cut_start >= float(policy.get("min_cut_seconds", 0.7)):
                ranges.append((cut_start, cut_end))

        if not ranges:
            new_decisions.append(item)
            continue

        cursor = start
        for cut_start, cut_end in sorted(ranges):
            if cut_start > cursor:
                new_decisions.append(
                    {
                        **item,
                        "start": round(cursor, 3),
                        "end": round(cut_start, 3),
                        "action": "keep",
                    }
                )
            removed.append(
                {
                    "source": source,
                    "start": round(cut_start, 3),
                    "end": round(cut_end, 3),
                    "duration": round(cut_end - cut_start, 3),
                    "reason": "detected_silence",
                }
            )
            cursor = max(cursor, cut_end)

        if cursor < end:
            new_decisions.append(
                {
                    **item,
                    "start": round(cursor, 3),
                    "end": round(end, 3),
                    "action": "keep",
                }
            )

    output = dict(plan)
    output["edit_decisions"] = new_decisions
    output.setdefault("automation", {})["dead_air"] = {
        "enabled": True,
        "removed_ranges": removed,
        "removed_seconds": round(sum(x["duration"] for x in removed), 3),
    }
    return output


def apply_remove_dead_air(job: Path):
    plan = _load_plan(job)
    silence = _load_silence(job)
    revised = remove_dead_air_from_plan(plan, silence)
    revisions = job / "decisions" / "revisions"
    revisions.mkdir(parents=True, exist_ok=True)
    existing = sorted(revisions.glob("router-*.json"))
    number = len(existing) + 1
    path = revisions / f"router-{number:03d}.json"
    path.write_text(json.dumps(revised, indent=2, ensure_ascii=False), encoding="utf-8")
    (job / "decisions" / "edit-plan.json").write_text(
        json.dumps(revised, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return revised, revised.get("automation", {}).get("dead_air", {})


def describe(action):
    return {
        "remove_dead_air": "Uses FFmpeg silencedetect results to create conservative keep-ranges without asking an LLM to perform the mechanical cut.",
        "create_shorts": "Runs the chunked Clip Hunter and Shorts renderer.",
        "add_captions": "Uses the existing transcript-backed caption renderer.",
        "unknown": "No deterministic ACF action matched the request.",
    }.get(action, "Unknown action.")
