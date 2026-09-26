from __future__ import annotations

import json
import re
from pathlib import Path


def _text(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "")


def _tokens(value):
    raw = re.findall(r"[a-zA-Z0-9_@.-]{2,}", _text(value).lower())
    return {token.strip("._-") for token in raw if token.strip("._-")}


def build(job: Path, manifest: dict | None = None):
    if manifest is None:
        manifest = json.loads(
            (job / "analysis" / "media-manifest.json").read_text(encoding="utf-8")
        )

    assets = {}
    assets_path = job / "analysis" / "assets.json"
    scenes_path = job / "analysis" / "scenes.json"

    if assets_path.exists():
        try:
            assets = json.loads(assets_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            assets = {}
    scenes = {}
    if scenes_path.exists():
        try:
            scenes = json.loads(scenes_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            scenes = {}

    records = []
    for item in manifest.get("files", []):
        path = str(Path(item["path"]).resolve())
        probe = item.get("probe", {})
        record = {
            "id": f"media:{len(records)+1:05d}",
            "path": path,
            "name": item.get("name") or Path(path).name,
            "extension": item.get("extension") or Path(path).suffix.lower(),
            "kind": "video" if str(item.get("extension", "")).lower() in {
                ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mts", ".m2ts"
            } else "asset",
            "duration": (probe.get("format") or {}).get("duration"),
            "search_text": " ".join(
                [path, item.get("name", ""), item.get("extension", "")]
            ),
        }
        record["tokens"] = sorted(_tokens(record["search_text"]))
        records.append(record)

    for key, entries in (
        ("assets", assets.get("assets", [])),
        ("scenes", scenes.get("scenes", [])),
    ):
        for item in entries:
            if not isinstance(item, dict):
                continue
            source = item.get("source") or item.get("path")
            if not source:
                continue
            searchable = " ".join(
                [
                    _text(source),
                    _text(item.get("name")),
                    _text(item.get("description")),
                    _text(item.get("subjects")),
                    _text(item.get("on_screen_text")),
                    _text(item.get("role")),
                ]
            )
            records.append(
                {
                    "id": f"{key}:{len(records)+1:05d}",
                    "path": str(source),
                    "kind": key[:-1],
                    "start": item.get("start"),
                    "end": item.get("end"),
                    "description": item.get("description"),
                    "role": item.get("role"),
                    "search_text": searchable,
                    "tokens": sorted(_tokens(searchable)),
                }
            )

    data = {"version": 1, "records": records}
    target = job / "analysis" / "media-index.json"
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def search(job: Path, query: str, limit: int = 10):
    path = job / "analysis" / "media-index.json"
    if not path.exists():
        build(job)
    data = json.loads(path.read_text(encoding="utf-8"))
    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    scored = []
    for record in data.get("records", []):
        text = _text(record.get("search_text")).lower()
        tokens = set(record.get("tokens", []))
        score = sum(2.0 if token in tokens else 1.0 for token in query_tokens if token in text)
        if score <= 0:
            continue
        scored.append((score, record))
    scored.sort(key=lambda item: (-item[0], item[1].get("id", "")))
    return [record for _, record in scored[:max(1, int(limit))]]
