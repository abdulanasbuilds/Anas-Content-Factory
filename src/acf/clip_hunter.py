from __future__ import annotations

import json
from pathlib import Path

from .config import factory_config
from .providers import ProviderError, extract_json, generate


def load_segments(job: Path):
    path = job / "analysis" / "transcript.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [item for item in data.get("segments", []) if isinstance(item, dict) and item.get("text")]


def chunk_segments(segments, size=120, max_chunks=8):
    size = max(1, int(size))
    max_chunks = max(1, int(max_chunks))
    all_chunks = [
        segments[index:index + size]
        for index in range(0, len(segments), size)
        if segments[index:index + size]
    ]
    if len(all_chunks) <= max_chunks:
        return all_chunks

    if max_chunks == 1:
        return [all_chunks[len(all_chunks) // 2]]

    indices = []
    for slot in range(max_chunks):
        index = round(slot * (len(all_chunks) - 1) / (max_chunks - 1))
        if index not in indices:
            indices.append(index)
    return [all_chunks[index] for index in indices]


def _score(candidate):
    explicit = candidate.get("clip_score", candidate.get("score"))
    try:
        return max(0.0, min(1.0, float(explicit)))
    except (TypeError, ValueError):
        pass

    weights = {
        "hook_strength": 0.25,
        "standalone_clarity": 0.25,
        "usefulness": 0.20,
        "emotional_strength": 0.10,
        "pacing": 0.10,
        "surprise": 0.10,
    }
    total = 0.0
    used = 0.0
    for key, weight in weights.items():
        try:
            total += max(0.0, min(1.0, float(candidate.get(key)))) * weight
            used += weight
        except (TypeError, ValueError):
            pass
    return round(total / used, 4) if used else 0.5


def _candidate_prompt(chunk, project_summary, project_type, max_per_chunk):
    lines = []
    sources = []
    for item in chunk:
        source = item.get("source", "")
        sources.append(source)
        lines.append(
            f"SOURCE={source}\n"
            f"START={float(item.get('start', 0)):.3f}\n"
            f"END={float(item.get('end', 0)):.3f}\n"
            f"TEXT={item.get('text', '')}"
        )
    source_hint = sorted(set(sources))
    return (
        "You are the clip-selection specialist for Anas Content Factory. "
        "Find self-contained moments that can become short-form videos. "
        "Do not predict virality as a certainty. Score editorial clip quality instead: "
        "hook strength, standalone clarity, usefulness, emotional strength, pacing and surprise. "
        f"Return at most {max_per_chunk} candidates. "
        "Every timestamp and source must come directly from the supplied transcript. "
        "Prefer 20-60 second moments with a clear beginning and payoff. "
        "Return JSON only: {shorts:[{title,source,start,end,hook,hook_strength,standalone_clarity,"
        "usefulness,emotional_strength,pacing,surprise,clip_score,reframe}]}."
        f"\nPROJECT TYPE: {project_type}\nPROJECT SUMMARY: {project_summary}\n"
        f"ALLOWED SOURCES: {json.dumps(source_hint, ensure_ascii=False)}\n"
        "\nTRANSCRIPT CHUNK:\n" + "\n---\n".join(lines)
    )


def _normalize_candidate(candidate, chunk, min_seconds, max_seconds):
    if not isinstance(candidate, dict):
        return None
    try:
        start = float(candidate["start"])
        end = float(candidate["end"])
    except (KeyError, TypeError, ValueError):
        return None
    if end <= start:
        return None
    duration = end - start
    if duration < min_seconds:
        return None
    end = min(end, start + max_seconds)
    if end - start < min_seconds:
        return None

    allowed_sources = {str(item.get("source")) for item in chunk if item.get("source")}
    source = str(candidate.get("source") or "")
    if source not in allowed_sources:
        if len(allowed_sources) != 1:
            return None
        source = next(iter(allowed_sources))

    chunk_start = min(float(item["start"]) for item in chunk)
    chunk_end = max(float(item["end"]) for item in chunk)
    if start < chunk_start - 0.25 or start >= chunk_end + 0.25:
        return None
    end = min(end, chunk_end)
    if end - start < min_seconds:
        return None

    normalized = {
        "title": candidate.get("title") or "Short",
        "source": source,
        "start": round(start, 3),
        "end": round(end, 3),
        "hook": str(candidate.get("hook") or "").strip(),
        "reframe": candidate.get("reframe") or {"x": 0.5, "y": 0.5},
    }
    for key in (
        "hook_strength",
        "standalone_clarity",
        "usefulness",
        "emotional_strength",
        "pacing",
        "surprise",
    ):
        if key in candidate:
            normalized[key] = candidate[key]
    normalized["clip_score"] = _score(candidate)
    normalized["confidence"] = normalized["clip_score"]
    return normalized


def _overlap(a, b):
    if a["source"] != b["source"]:
        return 0.0
    start = max(a["start"], b["start"])
    end = min(a["end"], b["end"])
    intersection = max(0.0, end - start)
    union = max(a["end"], b["end"]) - min(a["start"], b["start"])
    return intersection / union if union else 0.0


def dedupe_and_rank(candidates, limit):
    ordered = sorted(
        candidates,
        key=lambda item: (-float(item.get("clip_score", 0)), item["source"], item["start"]),
    )
    selected = []
    for candidate in ordered:
        if any(_overlap(candidate, existing) >= 0.65 for existing in selected):
            continue
        selected.append(candidate)
        if len(selected) >= int(limit):
            break
    return selected


def hunt(job: Path, plan: dict):
    policy = factory_config().get("shorts", {})
    min_seconds = float(policy.get("min_seconds", 20))
    max_seconds = float(policy.get("max_seconds", 60))
    max_candidates = int(policy.get("max_candidates", 6))
    chunk_size = int(policy.get("chunk_segments", 120))
    max_chunks = int(policy.get("max_chunks", 8))
    per_chunk = int(policy.get("candidates_per_chunk", 3))

    segments = load_segments(job)
    if not segments:
        return [], None, "No timestamped transcript is available for Clip Hunter."

    candidates = []
    chunks = chunk_segments(segments, chunk_size, max_chunks)
    summary = str(plan.get("summary") or "")
    project_type = str(plan.get("project_type") or "general")

    providers = []
    errors = []
    for chunk in chunks:
        prompt = _candidate_prompt(chunk, summary, project_type, per_chunk)
        try:
            raw, provider = generate(prompt)
            providers.append(provider)
            parsed = extract_json(raw)
            for item in (parsed.get("shorts", []) if isinstance(parsed, dict) else []):
                normalized = _normalize_candidate(item, chunk, min_seconds, max_seconds)
                if normalized:
                    candidates.append(normalized)
        except ProviderError as exc:
            errors.append(str(exc))

    if not candidates:
        highlights = plan.get("highlights", []) or []
        for item in highlights:
            if not isinstance(item, dict):
                continue
            try:
                start = float(item["start"])
                end = min(float(item["end"]), start + max_seconds)
            except (KeyError, TypeError, ValueError):
                continue
            if end - start < min_seconds:
                continue
            source = item.get("source")
            if not source:
                continue
            candidates.append(
                {
                    "title": item.get("title") or "Highlight",
                    "source": source,
                    "start": start,
                    "end": end,
                    "hook": item.get("reason") or item.get("description", ""),
                    "reframe": {"x": 0.5, "y": 0.5},
                    "clip_score": 0.5,
                    "confidence": 0.5,
                }
            )

    warning = None
    if errors and candidates:
        warning = "Some Clip Hunter chunks failed: " + " | ".join(errors[:3])
    elif errors:
        warning = "Clip Hunter provider errors: " + " | ".join(errors[:3])

    provider = providers[0] if providers else None
    return dedupe_and_rank(candidates, max_candidates), provider, warning
