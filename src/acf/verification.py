from __future__ import annotations

import json
from pathlib import Path

from .media import duration, extract_frame
from .providers import ProviderError, extract_json, generate_vision


def _sample_times(total: float, count: int = 6):
    if total <= 0:
        return []
    count = max(2, int(count))
    if count == 2:
        return [0.0, max(0.0, total - 0.25)]
    return [
        max(0.0, total * index / (count - 1))
        for index in range(count)
    ]


def verify_review(job: Path, review_path: Path, max_frames: int = 6):
    total = duration(review_path)
    frame_dir = job / "review" / "verification-frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    frames = []
    for index, timestamp in enumerate(_sample_times(total, max_frames)):
        frame = frame_dir / f"frame-{index:02d}.jpg"
        if extract_frame(review_path, timestamp, frame, width=960):
            frames.append({"timestamp": round(timestamp, 3), "path": str(frame)})

    if not frames:
        return {
            "version": 1,
            "passed": False,
            "provider": None,
            "frames": [],
            "issues": [{"severity": "warning", "message": "No verification frames could be extracted."}],
        }

    prompt = (
        "You are the final visual verifier for a video post-production system. "
        "Inspect sampled frames from the rendered review video. "
        "Do not judge artistic taste as a failure unless it creates a concrete production problem. "
        "Look for black/empty frames, text outside the frame, unreadable or clipped overlays, "
        "graphics covering the speaker's important face area, obviously broken crops, duplicated "
        "or accidental UI, and other clear rendering defects. "
        "Return JSON only: {passed:boolean, issues:[{severity,message,frame_index}], observations:[string]}. "
        "Use severity critical, error or warning."
    )

    try:
        raw, provider = generate_vision(prompt, [Path(item["path"]) for item in frames])
        data = extract_json(raw)
        if not isinstance(data, dict):
            raise ProviderError("Verification response was not an object.")
        issues = data.get("issues", [])
        normalized = []
        for issue in issues if isinstance(issues, list) else []:
            if not isinstance(issue, dict):
                continue
            normalized.append(
                {
                    "severity": issue.get("severity", "warning"),
                    "message": str(issue.get("message") or ""),
                    "frame_index": issue.get("frame_index"),
                }
            )
        critical = any(item["severity"] in {"critical", "error"} for item in normalized)
        return {
            "version": 1,
            "passed": not critical and bool(data.get("passed", True)),
            "provider": provider,
            "frames": frames,
            "issues": normalized,
            "observations": data.get("observations", []),
        }
    except (ProviderError, OSError) as exc:
        return {
            "version": 1,
            "passed": True,
            "provider": None,
            "frames": frames,
            "issues": [],
            "observations": [],
            "warning": f"Visual verification unavailable: {exc}",
        }
