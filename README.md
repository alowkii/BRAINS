# BRAINS

**B**ehavioral **R**easoning & **A**daptive **I**ntelligence **N**etwork **S**warm.

Six review agents (M1–M6) that check a piece of text from six different angles.
All run locally on `qwen3.5:0.8b-q4_K_S` via Ollama. Each ends its reply with a one-line `VERDICT:`.

| Agent | Lens | Asks | Verdict options |
|---|---|---|---|
| M1 | Truth and evidence | Is it so? Correctness, justification, source reliability, plausibility. | supported / partly supported / unsupported |
| M2 | Internal logic | Does it hang together? Consistency, validity, implication. | sound / has gaps / contradictory |
| M3 | Fit to the question | Is it on target? Relevance, completeness, precision. | on target / partly on target / off target |
| M4 | Self-monitoring | How well is this known? Confidence calibration, feeling of knowing, bias. | well calibrated / overconfident / underconfident |
| M5 | Practical value | Does it matter? Significance, actionability, cost of being wrong. | high value / some value / low value |
| M6 | Fairness | Is the other side treated properly? Charity, symmetry. | fair / somewhat one-sided / strawman |

## Configuring

Each agent has its own folder with a `config.toml` holding its model and instructions —
edit the file to change what the agent does, no code changes needed:

```toml
model = "qwen3.5:0.8b-q4_K_S"
think = false          # qwen3.5 otherwise spends the whole reply thinking
instructions = """
You are the Truth and Evidence checker. ...
"""
```

## Using

```python
from brains.agents import ask, ask_all

ask("M1", "The moon is made of cheese.")            # one agent, returns the reply

ask_all({                                            # any agents, each with its own
    "M1": "The moon is made of cheese.",             # prompt, all run in parallel
    "M6": "Everyone who disagrees with me is an idiot.",
})                                                   # -> {"M1": "...", "M6": "..."}
```

Command line: `uv run brains M1 "<text>"`, or `uv run brains all "<text>"` to send the
same text to all six.

## Testing

`uv run python tests/test_agents.py` gives each agent one obvious case and checks it
returns a valid, correct verdict. Expect failures: at 0.8b the model often reaches the
wrong verdict, and results vary between runs. Point `model` at a larger Qwen to fix that.

## Requirements

Ollama running locally with the model pulled. For all six to run at once rather than
queue, set `OLLAMA_NUM_PARALLEL=6` and restart Ollama.
