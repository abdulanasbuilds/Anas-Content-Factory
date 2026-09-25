from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path

from .config import env


class ProviderError(RuntimeError):
    pass


class Gemini:
    name = "gemini"

    def available(self):
        return bool(env("GEMINI_API_KEY"))

    def generate(self, prompt: str):
        key = env("GEMINI_API_KEY")
        model = env("GEMINI_MODEL", "gemini-2.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        return post_json(url, {"contents": [{"parts": [{"text": prompt}]}]})

    def generate_vision(self, prompt: str, images: list[Path]):
        key = env("GEMINI_API_KEY")
        model = env("GEMINI_VISION_MODEL", env("GEMINI_MODEL", "gemini-2.5-flash"))
        parts = [{"text": prompt}]
        for path in images:
            mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
            parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(path.read_bytes()).decode("ascii")}})
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        return post_json(url, {"contents": [{"parts": parts}]})


class OpenRouter:
    name = "openrouter"

    def available(self):
        return bool(env("OPENROUTER_API_KEY"))

    def generate(self, prompt: str):
        key = env("OPENROUTER_API_KEY")
        model = env("OPENROUTER_MODEL", "openrouter/free")
        return post_json(
            "https://openrouter.ai/api/v1/chat/completions",
            {"model": model, "messages": [{"role": "user", "content": prompt}]},
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )

    def generate_vision(self, prompt: str, images: list[Path]):
        key = env("OPENROUTER_API_KEY")
        model = env("OPENROUTER_VISION_MODEL", env("OPENROUTER_MODEL", "openrouter/free"))
        content = [{"type": "text", "text": prompt}]
        for path in images:
            mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})
        return post_json(
            "https://openrouter.ai/api/v1/chat/completions",
            {"model": model, "messages": [{"role": "user", "content": content}]},
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )


def post_json(url, body, headers=None):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers or {"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ProviderError(f"HTTP {exc.code}: {detail[:1000]}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ProviderError(str(exc)) from exc

    if "candidates" in data:
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"Gemini returned an unexpected response: {data}") from exc
    if "choices" in data:
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"OpenRouter returned an unexpected response: {data}") from exc
    raise ProviderError(f"Provider returned no text content: {data}")


def generate(prompt: str):
    errors = []
    for provider in (Gemini(), OpenRouter()):
        if not provider.available():
            continue
        try:
            return provider.generate(prompt), provider.name
        except ProviderError as exc:
            errors.append(f"{provider.name}: {exc}")
    raise ProviderError("No configured AI provider succeeded. " + " | ".join(errors))


def generate_vision(prompt: str, images: list[Path]):
    errors = []
    for provider in (Gemini(), OpenRouter()):
        if not provider.available():
            continue
        try:
            return provider.generate_vision(prompt, images), provider.name
        except ProviderError as exc:
            errors.append(f"{provider.name}: {exc}")
    raise ProviderError("No configured vision-capable AI provider succeeded. " + " | ".join(errors))


def extract_json(text: str):
    cleaned = text.strip()
    fence = chr(96) * 3
    if cleaned.startswith(fence):
        lines = cleaned.splitlines()
        if len(lines) >= 3:
            cleaned = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    for start, char in enumerate(cleaned):
        if char not in "[{":
            continue
        for end in range(len(cleaned), start + 1, -1):
            try:
                return json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                continue
    raise ProviderError("AI response did not contain valid JSON.")
