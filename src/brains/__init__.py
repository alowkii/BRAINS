import logging
import sys
from pathlib import Path

from brains.agents import AGENTS, AgentError, ask, ask_all, route, verdict
from brains.swarm import generate_reviewed

LOG_FILE = Path("brains.log")      # diagnostics: requests, replies, failures
THINKING_FILE = Path("thinking.txt")  # the current run's thought process, readable


def setup_logging(path: Path = LOG_FILE) -> None:
    logging.basicConfig(filename=path, filemode="w", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")


def write_thinking(text: str, path: Path = THINKING_FILE) -> None:
    """Append to the thought-process file. Written every run, shown or not."""
    with path.open("a", encoding="utf-8") as f:
        f.write(text + "\n")


def main() -> None:
    argv = [a for a in sys.argv[1:] if a != "--show-thinking"]
    thinking = len(argv) < len(sys.argv) - 1
    if len(argv) < 2:
        sys.exit(f"usage: brains <{'|'.join(AGENTS)}|all|gen> <prompt> [--show-thinking]")
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console chokes on non-ASCII replies
    setup_logging()
    name, prompt = argv[0], " ".join(argv[1:])
    try:
        run(name, prompt, thinking)
    except AgentError as e:
        logging.exception("failed")
        sys.exit(f"error: {e}")
    except KeyboardInterrupt:
        sys.exit("\nstopped")


def run(name: str, prompt: str, thinking: bool) -> None:
    profile = route(prompt)  # GOD picks the panel; nothing for the user to choose
    if thinking:
        print(f"[profile: {profile}]")
    if name == "all":
        for n, reply in ask_all(dict.fromkeys(AGENTS, prompt), profile).items():
            print(f"--- {n} ---\n{reply}\n")
    elif name == "gen":
        write = (lambda chunk: print(chunk, end="", flush=True)) if thinking else None
        THINKING_FILE.write_text(f"Q: {prompt}\n", encoding="utf-8")  # fresh each run
        text = ""
        for step in generate_reviewed(prompt, on_chunk=write, profile=profile):
            text = step.text
            verdicts = " | ".join(f"{n}: {verdict(r, n, profile)}" for n, r in step.reviews.items())
            mark = "REDO" if not step.kept else (
                "KEPT ANYWAY, out of redos" if step.decision == "regenerate" else "KEPT")
            write_thinking(f"\n[{mark}] {step.sentence}\n{verdicts}\nGOD: {step.decision}"
                           f" - {step.reason}")
            if thinking:
                print(f"\n{verdicts}")
                print(f"GOD: {step.decision} - {step.reason}\n")
        write_thinking(f"\nFINAL: {text}")
        print(f"\n{text}" if thinking else text)
        print(f"\n[thinking: {THINKING_FILE}, log: {LOG_FILE}]", file=sys.stderr)
    else:
        print(ask(name, prompt, profile))
