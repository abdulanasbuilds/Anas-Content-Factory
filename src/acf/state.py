from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


STAGES = [
    "DISCOVERING",
    "ANALYZING",
    "TRANSCRIBING",
    "VISUAL_ANALYSIS",
    "PLANNING",
    "EXECUTING",
    "REVIEW",
    "SHORTS",
    "QC",
    "DELIVERING",
    "COMPLETED",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_state(state: dict) -> dict:
    state.setdefault("version", 2)
    state.setdefault("status", "DISCOVERING")
    state.setdefault("current_stage", "DISCOVERING")
    state.setdefault("completed_stages", [])
    state.setdefault("stages", {})
    state.setdefault("errors", [])
    state.setdefault("warnings", [])
    state.setdefault("blocked", False)
    state.setdefault("human_action_required", False)
    state.setdefault("output_locations", [])
    state.setdefault("requested_outputs", [])
    state.setdefault("review_approved", False)
    state.setdefault("references", [])
    state.setdefault("updated_at", now())
    for stage in STAGES:
        state["stages"].setdefault(stage, {"status": "pending", "attempts": 0})
    return state


def start_stage(path: Path, stage: str) -> dict:
    state = ensure_state(load(path))
    info = state["stages"].setdefault(stage, {"status": "pending", "attempts": 0})
    info.update(
        status="running",
        attempts=int(info.get("attempts", 0)) + 1,
        started_at=now(),
        finished_at=None,
    )
    state.update(
        status=stage,
        current_stage=stage,
        updated_at=now(),
        blocked=False,
        human_action_required=False,
    )
    save(path, state)
    return state


def finish_stage(path: Path, stage: str, artifacts: list[str] | None = None, warnings: list[str] | None = None) -> dict:
    state = ensure_state(load(path))
    info = state["stages"].setdefault(stage, {"attempts": 0})
    info.update(status="completed", finished_at=now())
    if artifacts:
        info["artifacts"] = sorted(set(artifacts))
    if warnings:
        state.setdefault("warnings", []).extend(warnings)
    if stage not in state["completed_stages"]:
        state["completed_stages"].append(stage)
    state["blocked"] = False
    state["human_action_required"] = False
    state["status"] = stage
    state["current_stage"] = stage
    state["updated_at"] = now()
    save(path, state)
    return state


def fail_stage(path: Path, stage: str, error: str, blocked: bool = False) -> dict:
    state = ensure_state(load(path))
    info = state["stages"].setdefault(stage, {"attempts": 0})
    info.update(
        status="blocked" if blocked else "failed",
        finished_at=now(),
        error=error,
    )
    state.setdefault("errors", []).append({"stage": stage, "message": error, "at": now()})
    state.update(
        status="BLOCKED" if blocked else "FAILED",
        current_stage=stage,
        blocked=blocked,
        human_action_required=blocked,
        updated_at=now(),
    )
    save(path, state)
    return state


def recover_for_resume(path: Path) -> dict:
    state = ensure_state(load(path))
    for info in state["stages"].values():
        if info.get("status") == "running":
            info["status"] = "pending"
            info["recovered_at"] = now()
    if state.get("status") in {"FAILED", "BLOCKED"}:
        state["blocked"] = False
        state["human_action_required"] = False
    state["updated_at"] = now()
    save(path, state)
    return state
