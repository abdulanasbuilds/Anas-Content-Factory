import json
from pathlib import Path
from .providers import ProviderError, extract_json, generate

def apply_revision(job: Path, request: str):
    path = job / "decisions" / "edit-plan.json"
    if not path.exists():
        raise ProviderError("No edit plan found.")
    current = json.loads(path.read_text(encoding="utf-8"))
    prompt = (
        "Modify this video editing JSON according to the request. "
        "Use only files and timestamps in the current project. "
        "Return the complete JSON object and nothing else."
        + "\nREQUEST:\n" + request
        + "\nPLAN:\n" + json.dumps(current, indent=2, ensure_ascii=False)[:50000]
    )
    raw, provider = generate(prompt)
    updated = extract_json(raw)
    if not isinstance(updated, dict) or not isinstance(updated.get("edit_decisions"), list):
        raise ProviderError("Provider returned an invalid edit plan.")
    history = job / "decisions" / "revisions"
    history.mkdir(parents=True, exist_ok=True)
    number = len(list(history.glob("revision-*.json"))) + 1
    (history / f"revision-{number:03d}.json").write_text(
        json.dumps(
            {"revision": number, "request": request, "provider": provider, "plan": updated},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    path.write_text(json.dumps(updated, indent=2, ensure_ascii=False), encoding="utf-8")
    return updated, provider, number
