from __future__ import annotations

import json
from pathlib import Path

from .state import ensure_state, load, now, save


def escalate(job: Path, stage: str, question: str, reason: str, context=None):
    state_path = job / "project.json"
    state = ensure_state(load(state_path))
    record = {
        "status": "open",
        "created_at": now(),
        "stage": stage,
        "question": question,
        "reason": reason,
        "context": context or {},
    }
    target = job / "decisions" / "human-action.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    state.update(
        status="WAITING_FOR_HUMAN",
        current_stage=stage,
        blocked=True,
        human_action_required=True,
        updated_at=now(),
    )
    state["human_action"] = record
    save(state_path, state)
    return record


def resolve(job: Path, answer: str):
    state_path = job / "project.json"
    state = ensure_state(load(state_path))
    target = job / "decisions" / "human-action.json"
    if not target.exists():
        return False
    record = json.loads(target.read_text(encoding="utf-8"))
    record.update(status="resolved", resolved_at=now(), answer=answer)
    target.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    state["human_action"] = record
    state["blocked"] = False
    state["human_action_required"] = False
    state["status"] = "RESUMING"
    state["updated_at"] = now()
    save(state_path, state)
    return True


def pending(job: Path):
    target = job / "decisions" / "human-action.json"
    if not target.exists():
        return None
    record = json.loads(target.read_text(encoding="utf-8"))
    return record if record.get("status") == "open" else None


def format_question(record: dict) -> str:
    lines = [
        "ANAS CONTENT FACTORY needs your input.",
        "",
        f"Stage: {record.get('stage', 'unknown')}",
        f"Reason: {record.get('reason', 'unknown')}",
        "",
        record.get("question", ""),
        "",
        "Provide the answer, then resume the job.",
    ]
    return "\n".join(lines)
