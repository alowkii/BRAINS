"""Live test of agents M1-M6 against Ollama. Run: uv run python tests/test_agents.py"""
import re
import sys

from brains.agents import AGENTS, ask_all, load

# One obvious case per agent, and the verdict a working agent should reach.
CASES = {
    "M1": ("The moon is made of cheese.", "unsupported"),
    "M2": ("It is raining. It is not raining.", "contradictory"),
    "M3": ("Q: What is 2 + 2? A: Dogs like to run.", "off target"),
    "M4": ("I am 100% sure I will win the lottery tomorrow.", "overconfident"),
    "M5": ("Wear a seatbelt. It can save your life in a crash.", "high value"),
    "M6": ("Everyone who disagrees with me is an idiot.", "strawman"),
}


def allowed_verdicts(name: str) -> list[str]:
    # Read the options from the agent's own config so the test never drifts from it.
    line = re.search(r"VERDICT:(.*)\.", load(name)["instructions"]).group(1)
    return [v.strip() for v in line.split("/")]


def check(name: str, reply: str) -> list[str]:
    errors = []
    if not reply.strip():
        return ["empty reply"]
    m = re.search(r"VERDICT:\s*\**\s*([a-z -]+)", reply, re.I)
    if not m:
        return ["no VERDICT line"]
    verdict = m.group(1).strip().lower()
    options = allowed_verdicts(name)
    if verdict not in options:
        errors.append(f"verdict {verdict!r} not in {options}")
    expected = CASES[name][1]
    if verdict != expected:
        errors.append(f"expected {expected!r}, got {verdict!r}")
    return errors


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    replies = ask_all({n: CASES[n][0] for n in AGENTS})
    failed = 0
    for name in AGENTS:
        errors = check(name, replies[name])
        failed += bool(errors)
        print(f"{'PASS' if not errors else 'FAIL'} {name}" + "".join(f"\n     - {e}" for e in errors))
        if errors:
            print("     reply:", replies[name][-300:].replace("\n", " "))
    print(f"\n{len(AGENTS) - failed}/{len(AGENTS)} passed")
    sys.exit(bool(failed))


if __name__ == "__main__":
    main()
