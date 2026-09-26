from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .config import factory_config, jobs_dir
from .delivery import deliver
from .editor import EditPlanError, render_plan
from .escalation import escalate, pending
from .export_profiles import get_profile
from .media import VIDEO_EXTS, discover, extract_audio, make_proxy, write_manifest, duration
from .media_index import build as build_media_index
from .silence import analyze_job_audio
from .providers import ProviderError, extract_json, generate
from .review import render as render_review
from .shorts import generate_candidates, render_candidates
from .state import ensure_state, fail_stage, finish_stage, load, now, recover_for_resume, save, start_stage
from .transcription import render_markdown, transcribe
from .visual import analyze as analyze_visual


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "project"


def _state_path(job):
    return job / "project.json"


def _load_state(job):
    return ensure_state(load(_state_path(job)))


def _write_references(job, references):
    lines = ["# References", ""]
    for item in references:
        lines += [f"- URL: {item['url']}", f"  Purpose: {item.get('purpose', 'editorial reference')}", ""]
    (job / "analysis" / "references.md").write_text(chr(10).join(lines), encoding="utf-8")


def create_job(source: Path, references=None):
    base_name = safe_name(source.stem if source.is_file() else source.name)
    job = jobs_dir() / base_name
    if (job / "project.json").exists():
        try:
            old = load(job / "project.json")
            if Path(old.get("input_path", "")).resolve() == source.resolve():
                state = ensure_state(old)
                state["references"] = references or state.get("references", [])
                save(job / "project.json", state)
                _write_references(job, state["references"])
                return job
        except Exception:
            pass
        fingerprint = hashlib.sha1(str(source.resolve()).encode("utf-8")).hexdigest()[:10]
        job = jobs_dir() / f"{base_name}-{fingerprint}"

    for folder in ("source", "analysis", "assets", "decisions", "working", "review", "exports", "delivery"):
        (job / folder).mkdir(parents=True, exist_ok=True)

    state = ensure_state(
        {
            "version": 2,
            "project_id": job.name,
            "status": "DISCOVERING",
            "current_stage": "DISCOVERING",
            "input_path": str(source.resolve()),
            "project_type": "unknown",
            "requested_outputs": [],
            "review_approved": False,
            "provider_used": None,
            "fallback_provider": "openrouter",
            "completed_stages": [],
            "stages": {},
            "references": references or [],
            "blocked": False,
            "human_action_required": False,
            "errors": [],
            "warnings": [],
            "output_locations": [],
            "created_at": now(),
            "updated_at": now(),
        }
    )
    save(job / "project.json", state)
    _write_references(job, state["references"])
    return job


def _ensure_required_analysis_files(job):
    defaults = {
        "summary.md": "# Project Summary\n",
        "transcript.md": "# Transcript\n",
        "transcript.json": json.dumps({"version": 1, "segments": []}, indent=2),
        "scenes.json": json.dumps({"version": 1, "scenes": []}, indent=2),
        "speakers.json": json.dumps({"version": 1, "speakers": []}, indent=2),
        "highlights.json": json.dumps({"version": 1, "highlights": []}, indent=2),
        "issues.json": json.dumps({"version": 1, "issues": []}, indent=2),
        "assets.json": json.dumps({"version": 1, "assets": []}, indent=2),
    }
    for name, value in defaults.items():
        path = job / "analysis" / name
        if not path.exists():
            path.write_text(value, encoding="utf-8")


def analyze_source(source: Path, job: Path):
    manifest_path = job / "analysis" / "media-manifest.json"
    start_stage(_state_path(job), "ANALYZING")
    files = discover(source)
    if not files:
        raise EditPlanError("No supported media files were found.")
    manifest = write_manifest(files, manifest_path)

    warnings = []
    for item in manifest["files"]:
        path = Path(item["path"])
        if path.suffix.lower() not in VIDEO_EXTS:
            continue
        proxy = job / "working" / "proxies" / f"{path.stem}_proxy.mp4"
        audio = job / "working" / "audio" / f"{path.stem}.wav"
        if not make_proxy(path, proxy):
            warnings.append(f"Could not create proxy for {path.name}.")
        if not extract_audio(path, audio):
            warnings.append(f"Could not extract audio for {path.name}.")

    _ensure_required_analysis_files(job)
    try:
        analyze_job_audio(job, manifest)
    except Exception as exc:
        warnings.append(f"Could not analyze silence: {exc}")

    finish_stage(
        _state_path(job),
        "ANALYZING",
        [
            str(manifest_path),
            str(job / "analysis" / "silence.json"),
        ] + ([str(job / "working" / "proxies")] if (job / "working" / "proxies").exists() else []),
        warnings,
    )
    return manifest


def transcribe_stage(job: Path, manifest: dict):
    start_stage(_state_path(job), "TRANSCRIBING")
    raw_segments = []
    warnings = []
    transcript_dir = job / "analysis" / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    for item in manifest.get("files", []):
        source = Path(item["path"])
        if source.suffix.lower() in VIDEO_EXTS:
            audio = job / "working" / "audio" / f"{source.stem}.wav"
        else:
            audio = source
        if not audio.exists():
            continue
        normalized_path = transcript_dir / f"{source.stem}.json"
        if not normalized_path.exists() or normalized_path.stat().st_size == 0:
            ok = transcribe(audio, normalized_path)
            if not ok:
                warnings.append(
                    f"No local transcript for {source.name}. Configure WHISPER_BIN and WHISPER_MODEL if timestamped speech analysis is needed."
                )
        if normalized_path.exists():
            try:
                data = json.loads(normalized_path.read_text(encoding="utf-8"))
                for segment in data.get("segments", []):
                    raw_segments.append(
                        {
                            **segment,
                            "source": str(source.resolve()),
                            "id": f"{source.stem}:{segment['id']}",
                        }
                    )
            except json.JSONDecodeError:
                try:
                    normalized_path.unlink()
                except OSError:
                    pass
                if transcribe(audio, normalized_path):
                    data = json.loads(normalized_path.read_text(encoding="utf-8"))
                    for segment in data.get("segments", []):
                        raw_segments.append({**segment, "source": str(source.resolve()), "id": f"{source.stem}:{segment['id']}"})
                else:
                    warnings.append(f"Transcript file is invalid and could not be regenerated: {normalized_path}")

    combined = {"version": 1, "segments": sorted(raw_segments, key=lambda x: (x["start"], x["end"])), "sources": sorted({x["source"] for x in raw_segments})}
    (job / "analysis" / "transcript.json").write_text(
        json.dumps(combined, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (job / "analysis" / "transcript.md").write_text(render_markdown(combined), encoding="utf-8")

    speakers = sorted({x["speaker"] for x in raw_segments if x.get("speaker")})
    (job / "analysis" / "speakers.json").write_text(
        json.dumps({"version": 1, "speakers": [{"id": speaker, "label": speaker} for speaker in speakers]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    finish_stage(
        _state_path(job),
        "TRANSCRIBING",
        [
            str(job / "analysis" / "transcript.json"),
            str(job / "analysis" / "transcript.md"),
            str(job / "analysis" / "speakers.json"),
        ],
        warnings,
    )
    return combined


def visual_stage(job: Path, manifest: dict):
    start_stage(_state_path(job), "VISUAL_ANALYSIS")
    result = analyze_visual(job, manifest)
    try:
        build_media_index(job, manifest)
    except Exception as exc:
        result.setdefault("warnings", []).append(f"Could not build media index: {exc}")
    finish_stage(
        _state_path(job),
        "VISUAL_ANALYSIS",
        [
            str(job / "analysis" / "scenes.json"),
            str(job / "analysis" / "assets.json"),
            str(job / "analysis" / "media-index.json"),
        ],
        result.get("warnings", []),
    )
    return result


def _transcript_context(job, limit=45000):
    path = job / "analysis" / "transcript.json"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:limit]


def _silence_context(job, limit=14000):
    path = job / "analysis" / "silence.json"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:limit]


def _visual_context(job, limit=26000):
    parts = []
    for name in ("scenes.json", "assets.json"):
        path = job / "analysis" / name
        if path.exists():
            parts.append(path.read_text(encoding="utf-8")[:limit // 2])
    return "\n".join(parts)


def _fallback_plan(manifest):
    for item in manifest.get("files", []):
        path = Path(item["path"])
        if path.suffix.lower() not in VIDEO_EXTS:
            continue
        total = float(item.get("probe", {}).get("format", {}).get("duration", 0) or 0)
        return {
            "version": 1,
            "project_type": "general",
            "summary": "Automatic fallback: keep the primary source as a continuous timeline.",
            "requested_outputs": ["youtube_1080p"],
            "edit_decisions": [{"source": str(path), "start": 0, "end": total, "action": "keep"}],
            "highlights": [],
            "issues": [],
            "missing_assets": [],
            "shorts": [],
        }
    raise EditPlanError("No video source is available for a fallback plan.")


def _normalize_plan(plan, manifest):
    if not isinstance(plan, dict):
        raise EditPlanError("Producer response is not a JSON object.")
    normalized = dict(plan)
    normalized.setdefault("version", 1)
    normalized.setdefault("project_type", "general")
    normalized.setdefault("summary", "")
    normalized.setdefault("highlight", [])
    normalized.setdefault("highlights", [])
    normalized.setdefault("issues", [])
    normalized.setdefault("missing_assets", [])
    normalized.setdefault("edit_decisions", [])

    if not normalized["edit_decisions"]:
        normalized = _fallback_plan(manifest)

    outputs = normalized.get("requested_outputs") or [factory_config().get("editing", {}).get("default_output_profile", "youtube_1080p")]
    cleaned_outputs = []
    for item in outputs:
        name = item.get("profile") if isinstance(item, dict) else item
        if not name:
            continue
        try:
            key, _ = get_profile(str(name))
            cleaned_outputs.append(key)
        except KeyError:
            continue
    normalized["requested_outputs"] = sorted(set(cleaned_outputs or ["youtube_1080p"]))
    normalized["shorts_requested"] = True
    return normalized


def plan_stage(job: Path, manifest: dict):
    start_stage(_state_path(job), "PLANNING")
    state = _load_state(job)
    references = state.get("references", [])
    prompt = (
        "You are the Producer and Director for a professional post-production system. "
        "Understand the supplied media using the manifest, timestamped transcript and visual analysis. "
        "Infer the content category. Build a conservative, executable edit plan. "
        "Story and clarity come before effects. Preserve meaningful pauses, personality, context and emotion. "
        "Remove only genuine mistakes, unusable footage, repetition and accidental dead air. "
        "Never invent files, people, quotes or timestamps. "
        "Return JSON only with project_type, summary, requested_outputs, edit_decisions, highlights, issues, missing_assets, shorts. "
        "Each edit_decision needs source, start, end, action and may contain captions, reframe, graphics or audio. "
        "Use exact media paths from the manifest. "
        "A detected silent region is only a pacing signal, not an automatic deletion: preserve "
        "meaningful pauses and emotional beats. "
        "\nMANIFEST:\n" + json.dumps(manifest, indent=2, ensure_ascii=False)[:50000]
        + "\nTRANSCRIPT:\n" + _transcript_context(job)
        + "\nVISUAL ANALYSIS:\n" + _visual_context(job)
        + "\nSILENCE ANALYSIS:\n" + _silence_context(job)
        + "\nREFERENCES:\n" + json.dumps(references, indent=2, ensure_ascii=False)
    )
    try:
        raw, provider = generate(prompt)
        plan = _normalize_plan(extract_json(raw), manifest)
    except ProviderError as exc:
        fallback = _fallback_plan(manifest) if any(
            Path(x["path"]).suffix.lower() in VIDEO_EXTS for x in manifest.get("files", [])
        ) else None
        if fallback:
            plan = fallback
            provider = None
            warning = f"Semantic planning unavailable; deterministic fallback used: {exc}"
        else:
            escalate(
                job,
                "PLANNING",
                "Configure a working Gemini or OpenRouter provider, then resume the job.",
                "No semantic planning provider succeeded.",
                {"error": str(exc)},
            )
            return None
    else:
        warning = None

    (job / "decisions" / "edit-plan.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (job / "analysis" / "summary.md").write_text(
        "# Project Summary\n\n" + str(plan.get("summary", "")).strip() + "\n",
        encoding="utf-8",
    )
    (job / "analysis" / "highlights.json").write_text(
        json.dumps({"version": 1, "highlights": plan.get("highlights", [])}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (job / "analysis" / "issues.json").write_text(
        json.dumps({"version": 1, "issues": plan.get("issues", [])}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    category = safe_name(str(plan.get("project_type", "general")).lower())
    (job / "working" / f"category-{category}").mkdir(parents=True, exist_ok=True)
    state = _load_state(job)
    state["project_type"] = plan.get("project_type", "general")
    state["requested_outputs"] = plan["requested_outputs"]
    state["provider_used"] = provider
    state["status"] = "PLANNING"
    state["current_stage"] = "PLANNING"
    state["updated_at"] = now()
    save(_state_path(job), state)

    warnings = [warning] if warning else []
    finish_stage(
        _state_path(job),
        "PLANNING",
        [
            str(job / "decisions" / "edit-plan.json"),
            str(job / "analysis" / "summary.md"),
            str(job / "analysis" / "highlights.json"),
            str(job / "analysis" / "issues.json"),
        ],
        warnings,
    )
    return plan


def execute_stage(job: Path):
    start_stage(_state_path(job), "EXECUTING")
    plan = json.loads((job / "decisions" / "edit-plan.json").read_text(encoding="utf-8"))
    output = job / "exports" / "master_1080p.mp4"
    render_plan(job, plan, "master_1080p", output)
    finish_stage(_state_path(job), "EXECUTING", [str(output), str(output.with_suffix(".render.json"))])
    return output


def review_stage(job: Path):
    start_stage(_state_path(job), "REVIEW")
    state = _load_state(job)
    state["review_approved"] = False
    save(_state_path(job), state)
    plan = json.loads((job / "decisions" / "edit-plan.json").read_text(encoding="utf-8"))
    output, _ = render_review(job, plan)
    finish_stage(_state_path(job), "REVIEW", [str(output), str(job / "review" / "review-notes.md")])
    return output


def _review_gate(job: Path):
    policy = factory_config().get("editing", {})
    required = policy.get("review_required_before_final", True)
    if required in {False, "false", "False", 0}:
        return True
    state = _load_state(job)
    if state.get("review_approved"):
        return True
    action = pending(job)
    if action and action.get("stage") == "REVIEW":
        return False
    escalate(
        job,
        "REVIEW",
        f"Watch {job / 'review' / 'review.mp4'} and approve it with acf review {job.name} --approve. For changes, use acf revise {job.name} ...",
        "The review gate is enabled before Shorts and final delivery.",
        {"review_file": str(job / "review" / "review.mp4")},
    )
    return False


def shorts_stage(job: Path):
    start_stage(_state_path(job), "SHORTS")
    plan = json.loads((job / "decisions" / "edit-plan.json").read_text(encoding="utf-8"))
    candidates, provider, warning = generate_candidates(job, plan)
    candidates_path = job / "decisions" / "shorts-candidates.json"
    candidates_path.write_text(
        json.dumps({"version": 1, "provider": provider, "candidates": candidates, "warning": warning}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    rendered = render_candidates(job, candidates) if candidates else []
    finish_stage(
        _state_path(job),
        "SHORTS",
        [str(candidates_path)] + ([str(job / "exports" / "shorts" / "shorts-manifest.json")] if rendered else []),
        [warning] if warning else None,
    )
    return rendered


def qc_stage(job: Path):
    from .qc import run as run_qc

    start_stage(_state_path(job), "QC")
    report = run_qc(job)
    if not report["passed"]:
        report_path = job / "analysis" / "qc-report.md"
        escalate(
            job,
            "QC",
            f"Review {report_path} and resolve the failing media checks, then resume.",
            "Automated quality control failed.",
            report,
        )
        return report
    finish_stage(_state_path(job), "QC", [str(job / "analysis" / "qc-report.json"), str(job / "analysis" / "qc-report.md")])
    return report


def delivery_stage(job: Path):
    state = _load_state(job)
    if not _stage_done(job, "REVIEW") or not _review_gate(job):
        return _load_state(job)
    if not state["stages"].get("QC", {}).get("status") == "completed":
        report = qc_stage(job)
        if not report.get("passed"):
            return _load_state(job)
    start_stage(_state_path(job), "DELIVERING")
    plan = json.loads((job / "decisions" / "edit-plan.json").read_text(encoding="utf-8"))
    locations = deliver(job, plan, _load_state(job).get("requested_outputs") or [factory_config().get("editing", {}).get("default_output_profile", "youtube_1080p")])
    from .qc import run as run_qc
    report = run_qc(job)
    if not report["passed"]:
        escalate(
            job,
            "DELIVERING",
            "Final delivery was rendered but post-delivery QC failed. Review the QC report and resume.",
            "Final output quality checks failed.",
            report,
        )
        return locations
    state = _load_state(job)
    state["output_locations"] = locations
    save(_state_path(job), state)
    finish_stage(_state_path(job), "DELIVERING", locations)
    finish_stage(_state_path(job), "COMPLETED", locations)
    return locations


def _stage_done(job, stage):
    return _load_state(job)["stages"].get(stage, {}).get("status") == "completed"


def _guard(job: Path, stage: str, function, question: str):
    try:
        return function()
    except Exception as exc:
        escalate(
            job,
            stage,
            question,
            f"Stage {stage} stopped with an error.",
            {"error": str(exc)},
        )
        return None


def run_pipeline(job: Path):
    state = recover_for_resume(_state_path(job))
    if pending(job):
        return _load_state(job)
    source = Path(state["input_path"])

    if not _stage_done(job, "ANALYZING"):
        manifest = _guard(
            job,
            "ANALYZING",
            lambda: analyze_source(source, job),
            "Fix the media-discovery or FFmpeg issue shown in the human-action record, then run acf resume.",
        )
        if manifest is None:
            return _load_state(job)
    else:
        manifest = json.loads((job / "analysis" / "media-manifest.json").read_text(encoding="utf-8"))

    if not _stage_done(job, "TRANSCRIBING"):
        if _guard(
            job,
            "TRANSCRIBING",
            lambda: transcribe_stage(job, manifest),
            "Configure or fix transcription if timestamped speech is required, then run acf resume.",
        ) is None:
            return _load_state(job)

    if not _stage_done(job, "VISUAL_ANALYSIS"):
        if _guard(
            job,
            "VISUAL_ANALYSIS",
            lambda: visual_stage(job, manifest),
            "Fix the visual-analysis provider or media issue, then run acf resume.",
        ) is None:
            return _load_state(job)

    if not _stage_done(job, "PLANNING"):
        plan = _guard(
            job,
            "PLANNING",
            lambda: plan_stage(job, manifest),
            "Fix the planning/provider issue shown in the human-action record, then run acf resume.",
        )
        if plan is None:
            return _load_state(job)
    else:
        plan = json.loads((job / "decisions" / "edit-plan.json").read_text(encoding="utf-8"))

    for stage, fn, question in (
        ("EXECUTING", lambda: execute_stage(job), "Fix the FFmpeg/edit-plan error, then run acf resume."),
        ("REVIEW", lambda: review_stage(job), "Fix the review-rendering error, then run acf resume."),
    ):
        if not _stage_done(job, stage):
            if _guard(job, stage, fn, question) is None:
                return _load_state(job)

    if not _stage_done(job, "REVIEW") or not _review_gate(job):
        return _load_state(job)

    if not _stage_done(job, "SHORTS"):
        if _guard(
            job,
            "SHORTS",
            lambda: shorts_stage(job),
            "Fix the Shorts generation/rendering issue, then run acf resume.",
        ) is None:
            return _load_state(job)

    if not _stage_done(job, "QC"):
        report = _guard(
            job,
            "QC",
            lambda: qc_stage(job),
            "Review the QC report, fix the reported media problem, then run acf resume.",
        )
        if report is None or not report.get("passed"):
            return _load_state(job)

    if not _stage_done(job, "DELIVERING"):
        result = _guard(
            job,
            "DELIVERING",
            lambda: delivery_stage(job),
            "Fix the final-delivery or post-delivery QC problem, then run acf resume.",
        )
        if result is None:
            return _load_state(job)
    return _load_state(job)


def resume(job: Path):
    return run_pipeline(job)


def rerun_from_plan(job: Path):
    state = _load_state(job)
    state["status"] = "RESUMING"
    state["current_stage"] = "EXECUTING"
    state["blocked"] = False
    state["human_action_required"] = False
    state["review_approved"] = False
    for stage in ("EXECUTING", "REVIEW", "SHORTS", "QC", "DELIVERING", "COMPLETED"):
        state["stages"][stage] = {
            "status": "pending",
            "attempts": state["stages"].get(stage, {}).get("attempts", 0),
        }
    state["completed_stages"] = [
        x for x in state.get("completed_stages", [])
        if x not in {"EXECUTING", "REVIEW", "SHORTS", "QC", "DELIVERING", "COMPLETED"}
    ]
    save(_state_path(job), state)
    return run_pipeline(job)


def approve_review(job: Path):
    state = _load_state(job)
    if not _stage_done(job, "REVIEW"):
        state["review_approved"] = False
        state["updated_at"] = now()
        save(_state_path(job), state)
        return state
    state["review_approved"] = True
    state["blocked"] = False
    state["human_action_required"] = False
    state["status"] = "RESUMING"
    state["updated_at"] = now()
    save(_state_path(job), state)
    return run_pipeline(job)


def revise_and_resume(job: Path, instruction: str):
    from .plan_revision import apply_revision

    try:
        plan, provider, number = apply_revision(job, instruction)
    except ProviderError as exc:
        record = escalate(
            job,
            "PLANNING",
            "The edit revision could not be generated. Fix the AI provider problem shown in the human-action record, then run acf resume.",
            "Natural-language revision provider failed.",
            {"error": str(exc), "instruction": instruction},
        )
        return None, None, _load_state(job)
    state = _load_state(job)
    state["provider_used"] = provider
    save(_state_path(job), state)
    return plan, number, rerun_from_plan(job)
