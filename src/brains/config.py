"""Settings shared by every agent, read once from config.toml."""
import tomllib
from pathlib import Path

HERE = Path(__file__).parent
_CONFIG = tomllib.loads((HERE / "config.toml").read_text(encoding="utf-8"))

# Anything not in a [table] is an agent default, merged under each profile's own file.
DEFAULTS = {k: v for k, v in _CONFIG.items() if not isinstance(v, dict)}
OLLAMA_URL = _CONFIG["ollama"]["url"]
TIMEOUT = _CONFIG["ollama"]["timeout"]
SWARM = _CONFIG["swarm"]
