from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import jobs_dir
from .actions import apply_remove_dead_air, classify
from .doctor import run as doctor_run
from .escalation import format_question, pending, resolve
from .media_index import search as search_media
from .orchestrator import (
    analyze_source,
    approve_review,
    create_job,
    delivery_stage,
    plan_stage,
    qc_stage,
    rerun_from_plan,
    resume,
    revise_and_resume,
    run_pipeline,
)
from .state import load


def _job(value):
    path = Path(value).expanduser()
    if path.is_absolute() and (path / "project.json").exists():
        return path
    path = jobs_dir() / value
    if not (path / "project.json").exists():
        raise SystemExit(f"Project not found: {path}")
    return path


def _references(values):
    return [{"url": value, "purpose": "user-supplied reference"} for value in (values or [])]


def main():
    parser = argparse.ArgumentParser(prog="acf", description="Anas Content Factory")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run")
    p.add_argument("path")
    p.add_argument("--reference", action="append", default=[])
    
    p = sub.add_parser("analyze")
    p.add_argument("path")
    p.add_argument("--reference", action="append", default=[])

    p = sub.add_parser("status")
    p.add_argument("project")

    p = sub.add_parser("plan")
    p.add_argument("project")

    p = sub.add_parser("review")
    p.add_argument("project")
    p.add_argument("--answer")
    p.add_argument("--approve", action="store_true")

    p = sub.add_parser("action")
    p.add_argument("project")
    p.add_argument("request", nargs="+")

    p = sub.add_parser("assets")
    p.add_argument("project")
    p.add_argument("query", nargs="+")
    p.add_argument("--limit", type=int, default=10)

    p = sub.add_parser("revise")
    p.add_argument("project")
    p.add_argument("instruction", nargs="+")
    
    for name in ("resume", "deliver", "qc"):
        p = sub.add_parser(name)
        p.add_argument("project")
    sub.add_parser("doctor")

    args = parser.parse_args()

    if args.command in {"run", "analyze"}:
        source = Path(args.path).expanduser().resolve()
        if not source.exists():
            raise SystemExit(f"Path not found: {source}")
        job = create_job(source, _references(args.reference))
        if args.command == "analyze":
            manifest = analyze_source(source, job)
            print(json.dumps({"job": str(job), "media_files": len(manifest["files"])}, indent=2))
            return
        result = run_pipeline(job)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if args.command == "doctor":
        print(json.dumps(doctor_run(), indent=2, ensure_ascii=False))
        return

    job = _job(args.project)

    if args.command == "status":
        print(json.dumps(load(job / "project.json"), indent=2, ensure_ascii=False))
    elif args.command == "plan":
        state = load(job / "project.json")
        manifest = json.loads((job / "analysis" / "media-manifest.json").read_text(encoding="utf-8"))
        result = plan_stage(job, manifest)
        print(json.dumps(result or load(job / "project.json"), indent=2, ensure_ascii=False))
    elif args.command == "review":
        action = pending(job)
        if args.approve:
            if action and action.get("stage") != "REVIEW":
                print(format_question(action))
                return
            if action:
                resolve(job, "approved")
            result = approve_review(job)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.answer:
            if not action:
                print("No open human-action request.")
                return
            resolve(job, args.answer)
            result = resume(job)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif action:
            print(format_question(action))
        else:
            review_file = job / "review" / "review.mp4"
            state = load(job / "project.json")
            print(f"Review build: {review_file}")
            print(f"Approved: {state.get('review_approved', False)}")
            print(f"State: {state.get('status')}")
    elif args.command == "action":
        request = " ".join(args.request).strip()
        action_name = classify(request)
        if action_name == "remove_dead_air":
            revised, details = apply_remove_dead_air(job)
            result = rerun_from_plan(job)
            print(json.dumps({
                "action": action_name,
                "removed_seconds": details.get("removed_seconds", 0),
                "removed_ranges": details.get("removed_ranges", []),
                "state": result,
            }, indent=2, ensure_ascii=False))
        elif action_name == "create_shorts":
            from .orchestrator import shorts_stage
            rendered = shorts_stage(job)
            print(json.dumps({
                "action": action_name,
                "shorts": rendered,
            }, indent=2, ensure_ascii=False))
        else:
            print(json.dumps({
                "action": action_name,
                "message": "No native deterministic action matched. Use acf revise for an editorial-language change.",
            }, indent=2, ensure_ascii=False))
    elif args.command == "assets":
        query = " ".join(args.query).strip()
        print(json.dumps({
            "query": query,
            "results": search_media(job, query, args.limit),
        }, indent=2, ensure_ascii=False))
    elif args.command == "revise":
        instruction = " ".join(args.instruction).strip()
        result = revise_and_resume(job, instruction)
        print(json.dumps(result[2], indent=2, ensure_ascii=False))
        if result[1]:
            print(f"Revision: {result[1]}")
    elif args.command == "resume":
        print(json.dumps(resume(job), indent=2, ensure_ascii=False))
    elif args.command == "deliver":
        print(json.dumps(delivery_stage(job), indent=2, ensure_ascii=False))
    elif args.command == "qc":
        print(json.dumps(qc_stage(job), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
