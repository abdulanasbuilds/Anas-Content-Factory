from __future__ import annotations

import os


STYLES = {
    "clean": {
        "description": "Clean, restrained, professional motion design.",
        "motion_density": "low",
        "beat_limit": 5,
        "rules": [
            "Prefer a few meaningful callouts instead of constant movement.",
            "Keep overlays away from the speaker's face.",
            "Use short phrases, not paragraphs.",
            "Prioritize readability and visual hierarchy over effects.",
        ],
    },
    "short-form": {
        "description": "Fast, clear social video with frequent but purposeful visual changes.",
        "motion_density": "medium",
        "beat_limit": 8,
        "rules": [
            "Use stronger opening callouts in the first seconds.",
            "Change the visual treatment when the spoken idea changes.",
            "Keep text concise and easy to scan.",
            "Do not add an effect merely to fill empty time.",
        ],
    },
    "course": {
        "description": "Educational editing with simple visual aids and strong clarity.",
        "motion_density": "low",
        "beat_limit": 6,
        "rules": [
            "Prioritize comprehension over visual novelty.",
            "Use takeaway callouts and simple visual labels.",
            "Keep the speaker visible when explanation is important.",
            "Use full-screen visual takeover only when it improves understanding.",
        ],
    },
    "showreel": {
        "description": "High-energy promotional montage with stronger visual rhythm.",
        "motion_density": "high",
        "beat_limit": 10,
        "rules": [
            "Use rhythm changes around meaningful moments.",
            "Prefer visual variety over repetitive overlays.",
            "Keep branding consistent.",
            "Use motion to support the story rather than hide weak material.",
        ],
    },
}


def _clean(value: str) -> str:
    value = str(value or "").strip().lower().replace("_", "-")
    return value


def choose(project_type: str, requested: str | None = None):
    env_style = os.getenv("ACF_STYLE")
    requested = requested or env_style
    key = _clean(requested)
    if key in STYLES:
        return key, STYLES[key]

    project = _clean(project_type)
    mapping = {
        "talking-head": "clean",
        "podcast": "clean",
        "interview": "clean",
        "course": "course",
        "short-form": "short-form",
        "advertisement": "showreel",
        "event": "showreel",
        "event-highlight": "showreel",
    }
    key = mapping.get(project, "clean")
    return key, STYLES[key]


def prompt_context(project_type: str, requested: str | None = None):
    key, style = choose(project_type, requested)
    rules = "\n".join(f"- {rule}" for rule in style["rules"])
    return (
        f"STYLE PROFILE: {key}\n"
        f"STYLE DESCRIPTION: {style['description']}\n"
        f"MOTION DENSITY: {style['motion_density']}\n"
        f"MAX MOTION BEATS: {style['beat_limit']}\n"
        "STYLE RULES:\n" + rules
    )


def record_feedback(job: Path, request: str):
    path = job / "analysis" / "style-memory.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# Project Style Memory\n\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"- {str(request).strip()}\n")


def read_feedback(job: Path, limit: int = 12000):
    path = job / "analysis" / "style-memory.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:limit]
