from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    env_file = repo_root() / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def jobs_dir() -> Path:
    raw = env("ACF_JOBS_DIR")
    path = Path(raw).expanduser() if raw else repo_root() / "jobs"
    if not path.is_absolute():
        path = repo_root() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _scalar(value: str):
    value = value.strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value.strip('"').strip("'")


def factory_config():
    path = repo_root() / "factory.config.yaml"
    if not path.exists():
        return {}
    root = {}
    stack = [(-1, root)]
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        text = raw.strip()
        if ":" not in text:
            continue
        key, value = text.split(":", 1)
        key = key.strip()
        value = value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value:
            parent[key] = _scalar(value)
        else:
            parent[key] = {}
            stack.append((indent, parent[key]))
    return root


def setting(name: str, default=None):
    return os.getenv(name, default)
