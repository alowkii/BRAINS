import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from brains.agents import AGENTS, AgentError, ask, ask_all, route, verdict
from brains.swarm import context_of, generate_reviewed

LOG_FILE = Path("brains.log")      # diagnostics: requests, replies, failures
THINKING_FILE = Path("thinking.txt")  # the current run's thought process, readable
CHATS = Path("chats")                 # one file per thread, so conversations stay apart


def setup_logging(path: Path = LOG_FILE) -> None:
    logging.basicConfig(filename=path, filemode="w", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")


def write_thinking(text: str, path: Path = THINKING_FILE) -> None:
    """Append to the thought-process file. Written every run, shown or not."""
    with path.open("a", encoding="utf-8") as f:
        f.write(text + "\n")


def thread_path(thread: str) -> Path:
    if not re.fullmatch(r"[\w-]{1,64}", thread):  # it becomes a filename
        raise AgentError(f"Thread id {thread!r} must be letters, digits, - or _")
    return CHATS / f"{thread}.json"


def new_thread() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def sessions() -> list[Path]:
    """Saved sessions, most recently used first."""
    return sorted(CHATS.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)


def pick_session() -> str:
    """Offer the saved sessions and take one. Enter, or nothing saved, starts a new one."""
    saved = sessions()
    if not saved:
        return new_thread()
    print("sessions:")
    for i, f in enumerate(saved, 1):
        turns = len(load_history(f.stem)) // 2
        when = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {i}) {f.stem:24} {turns:3} turn{'s' * (turns != 1):1}  {when}")
    try:
        choice = input("session number, or Enter for a new one: ").strip()
    except (KeyboardInterrupt, EOFError):
        choice = ""
    if choice.isdigit() and 1 <= int(choice) <= len(saved):
        return saved[int(choice) - 1].stem
    return choice or new_thread()  # a name typed instead of a number starts or resumes it


def load_history(thread: str) -> list[dict[str, str]]:
    """The saved conversation, or nothing if the thread is new or unreadable."""
    try:
        return json.loads(thread_path(thread).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def save_history(thread: str, history: list[dict[str, str]]) -> None:
    CHATS.mkdir(exist_ok=True)
    thread_path(thread).write_text(json.dumps(history, indent=1), encoding="utf-8")


def main() -> None:
    argv, thinking, session = [], False, ""
    args = iter(sys.argv[1:])
    for a in args:
        if a == "--show-thinking":
            thinking = True
        elif a in ("--session_id", "--session-id"):
            session = next(args, "")
        else:
            argv.append(a)
    if not argv or (len(argv) < 2 and argv[0] != "chat"):
        sys.exit(f"usage: brains <{'|'.join(AGENTS)}|all|gen> <prompt> [--show-thinking]\n"
                 f"       brains chat [--show-thinking]")
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console chokes on non-ASCII replies
    setup_logging()
    name, prompt = argv[0], " ".join(argv[1:])
    try:
        chat(thinking, session) if name == "chat" else run(name, prompt, thinking)
    except AgentError as e:
        logging.exception("failed")
        sys.exit(f"error: {e}")
    except (KeyboardInterrupt, EOFError):
        sys.exit("\nbye")


GREETINGS = {"hi", "hello", "hey", "yo", "hiya", "sup", "good morning", "good evening",
             "good afternoon", "thanks", "thank you", "ok", "okay", "cool", "bye now"}


def small_talk(prompt: str) -> str:
    """A greeting has nothing to review, so it never reaches the panel."""
    bare = prompt.strip().strip("!.?,").lower()
    if bare in GREETINGS:
        return ("Hello. What is on your mind?" if bare not in ("thanks", "thank you")
                else "You are welcome.")
    return ""


def answer(prompt: str, thinking: bool, history: list[dict[str, str]] | None = None) -> str:
    """One turn: route it, write it sentence by sentence, record the thinking."""
    if reply := small_talk(prompt):
        write_thinking(f"\nQ: {prompt}\nsmall talk, no panel\nFINAL: {reply}")
        return reply
    profile = route(prompt, context_of(history))
    if profile == "clarify":  # too little to answer, so ask instead of guessing
        reply = ask("GEN", context_of(history) + prompt, "clarify").strip()
        write_thinking(f"\nQ: {prompt}\nProfile: clarify (asked instead of answering)"
                       f"\nFINAL: {reply}")
        return reply
    if thinking:
        print(f"[profile: {profile}]")
    write_thinking(f"\nQ: {prompt}\nProfile: {profile}")
    write = (lambda chunk: print(chunk, end="", flush=True)) if thinking else None
    text = ""
    for step in generate_reviewed(prompt, on_chunk=write, profile=profile, history=history):
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
    return text


def chat(thinking: bool = False, thread: str = "") -> None:
    """Keep talking in one thread. Every agent sees it; the panel is picked per turn."""
    thread = thread or pick_session()
    THINKING_FILE.write_text("", encoding="utf-8")
    history = load_history(thread)
    turns = len(history) // 2
    print(f"brains chat [{thread}] - 'bye' to leave, 'new' to forget this thread"
          + (f" (carrying on, {turns} turn{'s' * (turns != 1)} so far)" if turns else ""))
    while True:
        try:
            said = input("\nyou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nbye")
            return
        if not said:
            continue
        if said.lower() in ("bye", "exit", "quit"):
            print("bye")
            return
        if said.lower() in ("new", "forget", "reset"):
            history = []
            save_history(thread, history)
            print("forgotten - starting fresh")
            continue
        reply = answer(said, thinking, history)
        print(f"\nbrains: {reply}" if thinking else f"brains: {reply}")
        history += [{"role": "user", "content": said},
                    {"role": "assistant", "content": reply}]
        save_history(thread, history)


def run(name: str, prompt: str, thinking: bool) -> None:
    if name == "gen":
        THINKING_FILE.write_text("", encoding="utf-8")  # fresh each run
        text = answer(prompt, thinking)
        print(f"\n{text}" if thinking else text)
        print(f"\n[thinking: {THINKING_FILE}, log: {LOG_FILE}]", file=sys.stderr)
        return
    profile = route(prompt)
    if name == "all":
        for n, reply in ask_all(dict.fromkeys(AGENTS, prompt), profile).items():
            print(f"--- {n} ---\n{reply}\n")
    else:
        print(ask(name, prompt, profile))
