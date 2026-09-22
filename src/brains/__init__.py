import sys

from brains.agents import AGENTS, ask, ask_all


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(f"usage: brains <{'|'.join(AGENTS)}|all> <prompt>")
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console chokes on non-ASCII replies
    name, prompt = sys.argv[1], " ".join(sys.argv[2:])
    if name == "all":
        for n, reply in ask_all(dict.fromkeys(AGENTS, prompt)).items():
            print(f"--- {n} ---\n{reply}\n")
    else:
        print(ask(name, prompt))
