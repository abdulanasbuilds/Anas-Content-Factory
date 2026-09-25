from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]

def jobs_dir():
    value = os.getenv("ACF_JOBS_DIR", "").strip()
    path = Path(value).expanduser() if value else ROOT / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()

def env(name, default=""):
    return os.getenv(name, default).strip()
