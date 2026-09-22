import json
from concurrent.futures import ThreadPoolExecutor
import tomllib
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
OLLAMA_URL = "http://localhost:11434/api/chat"
AGENTS = [f"M{i}" for i in range(1, 7)]


def load(name: str) -> dict:
    if name not in AGENTS:
        raise ValueError(f"Unknown agent {name!r}, pick one of {AGENTS}")
    return tomllib.loads((HERE / name / "config.toml").read_text(encoding="utf-8"))


def ask(name: str, prompt: str) -> str:
    """Send prompt to agent `name` (M1-M6) and return its reply. Importable from anywhere."""
    cfg = load(name)
    body = json.dumps({
        "model": cfg["model"],
        "stream": False,
        "think": cfg.get("think", False),
        "messages": [
            {"role": "system", "content": cfg["instructions"].strip()},
            {"role": "user", "content": prompt},
        ],
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)["message"]["content"]


def ask_all(prompts: dict[str, str]) -> dict[str, str]:
    """Run agents in parallel, each on its own prompt: {"M1": "...", "M4": "..."} -> {name: reply}."""
    with ThreadPoolExecutor(len(prompts)) as pool:
        return dict(zip(prompts, pool.map(ask, prompts, prompts.values())))
