from __future__ import annotations
import json
import re
from pathlib import Path
from .config import jobs_dir
from .media import discover, write_manifest, extract_audio, make_proxy, VIDEO_EXTS
from .providers import generate, ProviderError
from .state import now, save, load
from .transcription import transcribe

def safe_name(value):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "project"

def create_job(source):
    name = safe_name(source.stem if source.is_file() else source.name)
    job = jobs_dir() / name
    for folder in ("source","analysis","assets","decisions","working","review","exports","delivery"):
        (job / folder).mkdir(parents=True, exist_ok=True)
    save(job / "project.json", {
        "version": 1,
        "project_id": name,
        "status": "DISCOVERING",
        "current_stage": "DISCOVERING",
        "input_path": str(source.resolve()),
        "project_type": "unknown",
        "requested_outputs": [],
        "provider_used": None,
        "fallback_provider": "openrouter",
        "completed_stages": [],
        "blocked": False,
        "human_action_required": False,
        "errors": [],
        "output_locations": [],
        "created_at": now(),
        "updated_at": now(),
    })
    return job

def analyze(source, job):
    state = load(job / "project.json")
    files = discover(source)
    manifest = write_manifest(files, job / "analysis" / "media-manifest.json")
    state.update(status="ANALYZING", current_stage="ANALYZING", updated_at=now())
    save(job / "project.json", state)

    transcripts = []
    for item in manifest["files"]:
        path = Path(item["path"])
        if path.suffix.lower() not in VIDEO_EXTS:
            continue
        proxy = job / "working" / "proxies" / f"{path.stem}_proxy.mp4"
        proxy.parent.mkdir(parents=True, exist_ok=True)
        make_proxy(path, proxy)
        audio = job / "working" / "audio" / f"{path.stem}.wav"
        audio.parent.mkdir(parents=True, exist_ok=True)
        if extract_audio(path, audio):
            transcript = job / "analysis" / "transcripts" / f"{path.stem}.json"
            if transcribe(audio, transcript):
                transcripts.append(str(transcript))
    state["transcripts"] = transcripts
    state["completed_stages"] = ["DISCOVERING", "ANALYZING"]
    state["updated_at"] = now()
    save(job / "project.json", state)
    return manifest

def plan(job):
    state = load(job / "project.json")
    manifest = json.loads((job / "analysis" / "media-manifest.json").read_text(encoding="utf-8"))
    transcript_text = ""
    transcript_dir = job / "analysis" / "transcripts"
    if transcript_dir.exists():
        for path in transcript_dir.glob("*.json"):
            transcript_text += "\\n" + path.read_text(encoding="utf-8")[:30000]

    prompt = """You are the Producer/Director for Anas Content Factory.
Infer the project type and create a professional conservative editorial plan.
Do not invent files, assets or timestamps.
Return JSON with keys: project_type, summary, highlights, issues, requested_outputs, edit_decisions, missing_assets.
The user wants maximum autonomy and minimal questions.

MEDIA MANIFEST:
""" + json.dumps(manifest, indent=2)[:50000] + """

AVAILABLE TRANSCRIPTS:
""" + transcript_text[:50000]

    try:
        result, provider = generate(prompt)
    except ProviderError as exc:
        state.update(
            status="BLOCKED",
            current_stage="PLANNING",
            blocked=True,
            human_action_required=True,
            errors=[str(exc)],
            updated_at=now(),
        )
        save(job / "project.json", state)
        return False, str(exc)

    (job / "analysis" / "summary.md").write_text(result, encoding="utf-8")
    (job / "decisions" / "edit-plan.json").write_text(result, encoding="utf-8")
    state.update(
        status="REVIEW",
        current_stage="REVIEW",
        project_type="auto-detected",
        provider_used=provider,
        completed_stages=["DISCOVERING", "ANALYZING", "PLANNING"],
        updated_at=now(),
    )
    save(job / "project.json", state)
    return True, provider
