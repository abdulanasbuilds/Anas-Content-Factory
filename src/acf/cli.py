from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import jobs_dir
from .escalation import format_question, pending, resolve
from .orchestrator import (
    analyze_source,
    create_job,
    delivery_stage,
    plan_stage,
    qc_stage,
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

    p = sub.add_parser("revise")
    p.add_argument("project")
    p.add_argument("instruction", nargs="+")
    
    for name in ("resume", "deliver", "qc"):
        p = sub.add_parser(name)
        p.add_argument("project")

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
        if args.answer:
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
            print(f"Review build: {review_file}")
            print(f"State: {load(job / 'project.json').get('status')}")
    elif args.command == "revise":
        instruction = " ".join(args.instruction).strip()
        result = revise_and_resume(job, instruction)
        print(json.dumps(result[2], indent=2, ensure_ascii=False))
        print(f"Revision: {result[1]}")
    elif args.command == "resume":
        print(json.dumps(resume(job), indent=2, ensure_ascii=False))
    elif args.command == "deliver":
        print(json.dumps(delivery_stage(job), indent=2, ensure_ascii=False))
    elif args.command == "qc":
        print(json.dumps(qc_stage(job), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
