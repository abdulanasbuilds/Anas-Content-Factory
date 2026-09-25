from datetime import datetime, timezone
import json

def now():
    return datetime.now(timezone.utc).isoformat()

def save(path, state):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(path)

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))
