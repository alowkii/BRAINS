import json
import logging
import re
import tomllib
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OLLAMA_URL = "http://localhost:11434/api/chat"
TIMEOUT = 120  # seconds per request
AGENTS = [f"M{i}" for i in range(1, 7)]
CONFIGS = AGENTS + ["GEN", "GOD"]  # GEN writes, GOD judges; neither reviews
DEFAULT_PROFILE = "factual"  # one <profile>.toml per agent folder: factual, emotional, ...


def profiles() -> list[str]:
    """Profiles every agent has a config for."""
    return sorted(p.stem for p in (HERE / "GEN").glob("*.toml"))


class AgentError(RuntimeError):
    """A config is broken, or Ollama would not answer."""


@lru_cache(maxsize=None)
def load(name: str, profile: str = DEFAULT_PROFILE) -> dict:
    """Read an agent's <profile>.toml. Cached - restart the process after editing one."""
    if name not in CONFIGS:
        raise AgentError(f"Unknown agent {name!r}, pick one of {CONFIGS}")
    path = HERE / name / f"{profile}.toml"
    if not path.exists():
        raise AgentError(f"No {profile!r} profile for {name}, pick one of {profiles()}")
    try:
        cfg = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise AgentError(f"Cannot read {path}: {e}") from e
    for key in ("model", "instructions"):
        if not isinstance(cfg.get(key), str) or not cfg[key].strip():
            raise AgentError(f"{path} needs a non-empty {key!r} string")
    return cfg


def chat_body(cfg: dict, messages: list[dict[str, str]], stream: bool) -> bytes:
    return json.dumps({
        "model": cfg["model"],
        "stream": stream,
        "think": cfg.get("think", False),
        "options": cfg.get("options", {}),  # e.g. [options] temperature = 0
        "messages": messages,
    }).encode()


def post(body: bytes) -> urllib.request.addinfourl:
    """POST to Ollama, turning connection failures into a clear AgentError."""
    req = urllib.request.Request(OLLAMA_URL, body, {"Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=TIMEOUT)
    except urllib.error.HTTPError as e:
        raise AgentError(f"Ollama rejected the request ({e.code}): {e.read().decode()[:200]}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AgentError(f"Cannot reach Ollama at {OLLAMA_URL} - is it running? ({e})") from e


def ask(name: str, prompt: str, profile: str = DEFAULT_PROFILE) -> str:
    """Send prompt to agent `name` and return its reply. Importable from anywhere."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise AgentError(f"{name}: prompt must be a non-empty string")
    cfg = load(name, profile)
    log.info("%s <- %d chars", name, len(prompt))
    body = chat_body(cfg, [
        {"role": "system", "content": cfg["instructions"].strip()},
        {"role": "user", "content": prompt},
    ], stream=False)
    with post(body) as r:
        try:
            reply = json.load(r)["message"]["content"]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise AgentError(f"{name}: unexpected reply from Ollama: {e}") from e
    log.info("%s -> %s", name, reply.replace("\n", " ")[:300])
    return reply


def ask_all(prompts: dict[str, str], profile: str = DEFAULT_PROFILE) -> dict[str, str]:
    """Run agents in parallel, each on its own prompt. A failing agent returns its error text."""
    if not prompts:
        raise AgentError("ask_all needs at least one {agent: prompt} pair")

    def safe(name: str, prompt: str) -> str:
        try:
            return ask(name, prompt, profile)
        except AgentError as e:  # one dead agent must not stop the other five
            log.exception("%s failed", name)
            return f"ERROR: {e}"

    with ThreadPoolExecutor(len(prompts)) as pool:
        return dict(zip(prompts, pool.map(safe, prompts, prompts.values())))


def verdict(reply: str, name: str = "", profile: str = DEFAULT_PROFILE) -> str:
    """The verdict an agent ends on. With `name`, flags one that is not an allowed option."""
    if not isinstance(reply, str) or "verdict" not in reply.lower():
        return "?"
    tail = re.split(r"verdict", reply, flags=re.I)[-1].lower()  # text after the last "VERDICT"
    if name:  # take whichever allowed option the agent actually named, longest first
        for opt in sorted(options(name, profile), key=len, reverse=True):
            if re.search(rf"\b{re.escape(opt)}\b", tail):
                return opt
    m = re.search(r"[a-z][a-z -]{2,}", tail)
    v = m.group(0).strip() if m else "?"
    if name:
        log.warning("%s gave %r, not one of %s", name, v, options(name, profile))
        return f"{v} (not an option)"
    return v


def route(question: str) -> str:
    """Ask GOD which panel fits this question. Falls back to the default profile."""
    picked = verdict(ask("GOD", question, "router"), "GOD", "router")
    if picked not in profiles():
        log.warning("router picked %r, falling back to %s", picked, DEFAULT_PROFILE)
        return DEFAULT_PROFILE
    log.info("ROUTED to %s", picked)
    return picked


def lens(name: str, profile: str = DEFAULT_PROFILE) -> str:
    """What an agent looks for, e.g. 'truth and evidence'. Falls back to its name."""
    return load(name, profile).get("lens", name)


def flags(name: str, profile: str = DEFAULT_PROFILE) -> list[str]:
    """Verdicts from this agent that are worth stopping for, e.g. ['unsupported']."""
    return load(name, profile).get("flags", [])


def veto(name: str, profile: str = DEFAULT_PROFILE) -> list[str]:
    """Verdicts that force a rewrite on their own - no appeal to GOD."""
    return load(name, profile).get("veto", [])


def options(name: str, profile: str = DEFAULT_PROFILE) -> list[str]:
    """The verdicts an agent's config allows, e.g. ['fair', 'somewhat one-sided', 'strawman']."""
    m = re.search(r"VERDICT:([^\n]*)", load(name, profile)["instructions"])
    if not m:
        raise AgentError(f"{name}/{profile}.toml has no 'VERDICT: a / b' line in its instructions")
    return [v.strip(" .") for v in m.group(1).split("/")]
