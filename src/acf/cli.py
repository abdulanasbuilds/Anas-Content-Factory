from __future__ import annotations
import argparse
from pathlib import Path
from .config import jobs_dir
from .orchestrator import create_job, analyze, plan
from .state import load
from .qc import run as qc_run

def main():
    parser = argparse.ArgumentParser(prog="acf", description="Anas Content Factory")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "analyze"):
        p = sub.add_parser(name); p.add_argument("path")
    for name in ("plan", "status", "qc"):
        p = sub.add_parser(name); p.add_argument("project")
    args = parser.parse_args()

    if args.command in {"run", "analyze"}:
        source = Path(args.path).expanduser().resolve()
        if not source.exists():
            raise SystemExit(f"Path not found: {source}")
        job = create_job(source)
        manifest = analyze(source, job)
        print(f"Job: {job}")
        print(f"Discovered: {len(manifest['files'])} media files")
        if args.command == "run":
            print("Planning:", plan(job))
        return

    job = Path(args.project)
    if not job.is_absolute():
        job = jobs_dir() / job
    if not (job / "project.json").exists():
        raise SystemExit(f"Project not found: {job}")

    if args.command == "status":
        print(load(job / "project.json"))
    elif args.command == "plan":
        print(plan(job))
    else:
        print(qc_run(job))
