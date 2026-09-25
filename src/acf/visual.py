from __future__ import annotations

import json
from pathlib import Path

from .config import factory_config
from .media import VIDEO_EXTS, duration, extract_frame
from .providers import ProviderError, extract_json, generate_vision


def _frame_times(total_duration: float, max_frames: int = 24):
    if total_duration <= 0:
        return []
    count = min(max_frames, max(6, int(total_duration / 30) + 1))
    if count == 1:
        return [max(0.0, total_duration / 2)]
    margin = min(1.0, total_duration / 20)
    usable = max(0.0, total_duration - 2 * margin)
    return [margin + usable * i / (count - 1) for i in range(count)]


def _parse_visual_response(text, frames):
    data = extract_json(text)
    items = data.get("frames") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ProviderError("Vision response did not contain a frames list.")
    out = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        frame = frames[min(index, len(frames) - 1)]
        timestamp = item.get("timestamp", frame["timestamp"])
        out.append(
            {
                "timestamp": float(timestamp),
                "frame": frame["path"],
                "shot_type": item.get("shot_type", "unknown"),
                "description": item.get("description", ""),
                "subjects": item.get("subjects", []),
                "on_screen_text": item.get("on_screen_text", ""),
                "visual_quality": item.get("visual_quality", "unknown"),
                "edit_value": item.get("edit_value", ""),
            }
        )
    return out


def analyze(job: Path, manifest: dict):
    config = factory_config().get("resource_policy", {})
    max_frames = int(config.get("max_visual_frames_per_video", 24))
    frame_width = int(config.get("visual_frame_width", 768))
    frame_root = job / "working" / "frames"
    visual_root = job / "analysis" / "visual"
    frame_root.mkdir(parents=True, exist_ok=True)
    visual_root.mkdir(parents=True, exist_ok=True)

    all_scenes = []
    warnings = []
    provider_used = None

    for item in manifest.get("files", []):
        source = Path(item["path"])
        if source.suffix.lower() not in VIDEO_EXTS:
            continue

        proxy = job / "working" / "proxies" / f"{source.stem}_proxy.mp4"
        total = duration(proxy) or float(item.get("probe", {}).get("format", {}).get("duration", 0) or 0)
        times = _frame_times(total, max_frames)
        frames = []
        for index, timestamp in enumerate(times):
            frame_path = frame_root / source.stem / f"frame_{index:03d}.jpg"
            if extract_frame(proxy if proxy.exists() else source, timestamp, frame_path, width=frame_width):
                frames.append({"timestamp": timestamp, "path": str(frame_path)})

        result_file = visual_root / f"{source.stem}.json"
        if result_file.exists() and result_file.stat().st_size > 0:
            try:
                prior = json.loads(result_file.read_text(encoding="utf-8"))
                if prior.get("provider") or prior.get("scenes"):
                    all_scenes.extend(prior.get("scenes", []))
                    provider_used = prior.get("provider") or provider_used
                    continue
            except json.JSONDecodeError:
                pass

        scenes = []
        try:
            for offset in range(0, len(frames), 6):
                batch = frames[offset:offset + 6]
                prompt = (
                    "You are the visual analyst for a professional video editor. "
                    "Analyze these sampled frames conservatively. Never invent text or people. "
                    "Return JSON only with key frames, an array with one item per image. "
                    "Each item must contain timestamp, shot_type, description, subjects, "
                    "on_screen_text, visual_quality, edit_value."
                )
                text, provider = generate_vision(prompt, [Path(f["path"]) for f in batch])
                provider_used = provider
                scenes.extend(_parse_visual_response(text, batch))
        except ProviderError as exc:
            warnings.append(f"Visual AI unavailable for {source.name}: {exc}")

        result_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "source": str(source),
                    "provider": provider_used,
                    "frame_count": len(frames),
                    "scenes": scenes,
                    "warning": warnings[-1] if warnings and not scenes else None,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        all_scenes.extend(scenes)

    assets = []
    for item in manifest.get("files", []):
        if Path(item["path"]).suffix.lower() not in VIDEO_EXTS:
            assets.append(item)

    (job / "analysis" / "scenes.json").write_text(
        json.dumps({"version": 1, "scenes": all_scenes}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (job / "analysis" / "assets.json").write_text(
        json.dumps({"version": 1, "assets": assets}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {"scenes": all_scenes, "assets": assets, "provider": provider_used, "warnings": warnings}
