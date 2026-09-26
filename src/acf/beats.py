from __future__ import annotations

from pathlib import Path


def normalize_beats(plan: dict, resolve_source, manifest: dict, input_path: Path, beat_limit: int = 8):
    raw = plan.get("motion_beats") or plan.get("beats") or []
    if not isinstance(raw, list):
        return []

    normalized = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        source_ref = item.get("source")
        text = str(item.get("text") or item.get("label") or "").strip()
        if not source_ref or not text:
            continue
        try:
            source = resolve_source(source_ref, manifest, input_path)
            start = float(item.get("start", 0))
            end = float(item.get("end", start + 2))
        except (TypeError, ValueError):
            continue
        if end <= start or start < 0:
            continue
        normalized.append(
            {
                "id": item.get("id") or f"beat-{index + 1:03d}",
                "source": str(source),
                "start": round(start, 3),
                "end": round(end, 3),
                "text": text[:140],
                "position": str(item.get("position") or "bottom").lower(),
                "style": str(item.get("style") or "callout").lower(),
                "fontsize": int(item.get("fontsize") or 42),
            }
        )

    normalized.sort(key=lambda beat: (beat["source"], beat["start"]))
    return normalized[:max(0, int(beat_limit))]
