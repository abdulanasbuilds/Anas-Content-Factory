from __future__ import annotations
import json, urllib.error, urllib.request
from .config import env

class ProviderError(RuntimeError):
    pass

class Gemini:
    name="gemini"
    def available(self): return bool(env("GEMINI_API_KEY"))
    def generate(self,prompt):
        key=env("GEMINI_API_KEY")
        model=env("GEMINI_MODEL","gemini-2.5-flash")
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        return post(url,{"contents":[{"parts":[{"text":prompt}]}]})

class OpenRouter:
    name="openrouter"
    def available(self): return bool(env("OPENROUTER_API_KEY"))
    def generate(self,prompt):
        key=env("OPENROUTER_API_KEY")
        model=env("OPENROUTER_MODEL","openrouter/free")
        return post("https://openrouter.ai/api/v1/chat/completions",
                    {"model":model,"messages":[{"role":"user","content":prompt}]},
                    {"Authorization":f"Bearer {key}","Content-Type":"application/json"})

def post(url,body,headers=None):
    req=urllib.request.Request(url,data=json.dumps(body).encode(),
        headers=headers or {"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=180) as response:
            data=json.loads(response.read().decode())
    except (urllib.error.URLError,TimeoutError) as exc:
        raise ProviderError(str(exc)) from exc
    if "candidates" in data:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    if "choices" in data:
        return data["choices"][0]["message"]["content"]
    return json.dumps(data)

def generate(prompt):
    errors=[]
    for provider in (Gemini(),OpenRouter()):
        if not provider.available():
            continue
        try:
            return provider.generate(prompt),provider.name
        except ProviderError as exc:
            errors.append(f"{provider.name}: {exc}")
    raise ProviderError("No configured AI provider succeeded. "+" | ".join(errors))
