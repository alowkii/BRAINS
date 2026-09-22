"""Live test of agents M1-M6 against Ollama. Run: uv run python tests/test_agents.py"""
import sys

from brains.agents import AGENTS, ask_all, options, verdict

# One obvious case per agent, and the verdict a working agent should reach.
CASES = {
    "TRUTH": ("The moon is made of cheese.", "unsupported"),
    "LOGIC": ("It is raining. It is not raining.", "contradictory"),
    "FIT": ("Q: What is 2 + 2? A: Dogs like to run.", "off target"),
    "SELF": ("I am 100% sure I will win the lottery tomorrow.", "overconfident"),
    "VALUE": ("Wear a seatbelt. It can save your life in a crash.", "high value"),
    "FAIRNESS": ("Everyone who disagrees with me is an idiot.", "strawman"),
}


def check(name: str, reply: str) -> list[str]:
    errors = []
    if not reply.strip():
        return ["empty reply"]
    v = verdict(reply)
    if v == "?":
        return ["no VERDICT line"]
    if v not in options(name):  # options come from the agent's own config, no drift
        errors.append(f"verdict {v!r} not in {options(name)}")
    expected = CASES[name][1]
    if v != expected:
        errors.append(f"expected {expected!r}, got {v!r}")
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
