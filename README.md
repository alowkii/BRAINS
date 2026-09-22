# BRAINS

**B**ehavioral **R**easoning & **A**daptive **I**ntelligence **N**etwork **S**warm.

A small model writes an answer one sentence at a time. After every sentence, six reviewers
read the answer so far and give a verdict, and an editor decides whether the sentence stays
or goes back to be rewritten with the criticism as input.

Everything runs locally on `qwen3.5:0.8b-q4_K_S` through Ollama. No dependencies beyond the
standard library.

**This is a proof of concept.** It exists to find out whether a panel of small, narrow
critics can improve what a small model writes, and to make that reasoning inspectable. It is
not a product, the answers are not trustworthy, and nothing here should be relied on. See
[what it does and does not catch](#what-it-does-and-does-not-catch) for where it fails.

## Methodology

**The loop.** One question produces this cycle, repeated per sentence:

```
question ──▶ GOD picks a panel (one call, before anything is written)
              │
              ▼
           GEN writes a sentence ──▶ TRUTH LOGIC FIT SELF VALUE FAIRNESS
              ▲                      (six reviews, in parallel, of the answer so far)
              │                              │
              │                              ▼
              │                      any veto verdict? ──▶ rewrite, no appeal
              │                      any flag verdict? ──▶ GOD rules: keep or rewrite
              │                      neither?          ──▶ keep, GOD not called
              └──── rewrite, with the rejected sentence and the reason ◀──┘
```

**Why sentence by sentence.** A whole answer is hard to fix and easy to wave through. One
sentence can be rejected and rewritten while the rest of the answer stands, and the reviewers
see each new sentence in the context of everything already accepted.

**Why six reviewers.** Each has one job and one vocabulary of verdicts, so a verdict is a
signal rather than an essay. Six cheap specialised calls beat one call asking a small model
to hold six concerns at once.

**Why an editor.** Reviewers are paid to find fault, and six of them will always find
something. GOD is asked only when a reviewer raises a flag, and sees only the flagged
reviews — otherwise the answer is kept for free. Some verdicts are too serious to argue
about: a `veto` skips GOD entirely and sends the sentence back.

**Why profiles.** "Is it true?" is the wrong question for a poem and "is it fair?" is the
wrong question for a bug fix. Each of the six slots means something different per profile,
and the writer and editor change with it.

**Why the criticism goes back to the writer.** A rejected sentence returns as a note in the
writer's system prompt, quoting the sentence and the reason, so the rewrite is informed
rather than a reroll.

## The six, per profile

| Profile | TRUTH | LOGIC | FIT | SELF | VALUE | FAIRNESS |
|---|---|---|---|---|---|---|
| **factual** | truth and evidence | internal logic | fit to the question | self-monitoring | practical value | fairness |
| **emotional** | attunement | timing and order | fit to their situation | agency and respect | concreteness | safety |
| **advice** | assumptions | options | tradeoffs | confidence | actionability | cost of being wrong |
| **technical** | correctness | completeness | fit to the question | edge cases | simplicity | safety |
| **opinion** | factual basis | logic | charity | symmetry | fact vs judgement | specificity |
| **creative** | voice | freshness | fit to the brief | rhythm | showing | momentum |

Each reviewer ends on one line, `VERDICT: a / b / c`, benign first. Its config names which
verdicts `flags` (ask the editor) and which `veto` (rewrite immediately).

Routing is done by GOD from a seventh config, `GOD/router.toml`, at temperature 0. In a
conversation it sees the previous turns, so a follow-up stays in the panel the conversation
is already in.

## Using it

```
uv run brains gen "why do cats purr?"                    # answer only
uv run brains gen "why do cats purr?" --show-thinking    # live text, verdicts, rulings

uv run brains chat                                       # lists sessions, pick or start new
uv run brains chat --session_id mystartup                # straight into one session

uv run brains TRUTH "The moon is made of cheese."        # one reviewer, no loop
uv run brains all "Remote work is always less productive."   # all six, full reviews
```

In a chat, `bye` leaves and `new` forgets that session. Sessions are files in `chats/`.

From Python:

```python
from brains.agents import ask, ask_all
from brains.swarm import generate_reviewed

ask("TRUTH", "some claim")                    # one reviewer
ask_all({"TRUTH": "...", "LOGIC": "..."})     # several, in parallel
for step in generate_reviewed("why is the sky blue?"):
    step.sentence, step.reviews, step.decision, step.reason, step.kept, step.text
```

`generate_reviewed(prompt, profile="technical")` skips routing; `history=[...]` continues a
conversation.

## Files

```
src/brains/
  agents.py     one call to Ollama, verdict parsing, routing
  swarm.py      the write - review - judge loop
  config.py     reads the shared settings
  config.toml   model, Ollama url, loop thresholds
  prompts/
    TRUTH/ LOGIC/ FIT/ SELF/ VALUE/ FAIRNESS/   six reviewers
    GEN/ GOD/                                   writer, editor and router
      factual.toml emotional.toml advice.toml technical.toml opinion.toml creative.toml
```

Every run writes `thinking.txt` (readable: each sentence, its verdicts, the ruling, the final
answer) and `brains.log` (every request and reply, plus failures). Both are overwritten each
run and both are gitignored.

## Configuring

To change what an agent does, edit its prompt: `prompts/<AGENT>/<profile>.toml`. To change
anything shared, edit [config.toml](src/brains/config.toml):

```toml
model = "qwen3.5:0.8b-q4_K_S"   # any profile file can override this for one agent
think = false                   # qwen3.5 otherwise spends the whole reply thinking

[swarm]
max_redos = 2          # rewrites per sentence
min_words = 45         # below this, nudge the writer to carry on
max_carry_ons = 2
review_chars = 400     # per review sent to the editor
duplicate_ratio = 0.55 # above this, a new sentence counts as one already said
```

Configs are cached, so restart the process after editing one.

Needs Ollama running with the model pulled. For all six reviewers to run at once rather than
queue, set `OLLAMA_NUM_PARALLEL=6` and restart Ollama.

## Testing

```
uv run python tests/test_agents.py
```

Gives each reviewer one obvious case and checks it returns a valid, correct verdict. Expect
failures: at 0.8b the model often reaches the wrong verdict, and results vary between runs.

## What it does and does not catch

The loop reliably catches faults that are visible **in the text itself**: contradiction,
repetition, invented numbers, orders and minimising in emotional replies, unstated
assumptions, prompt fragments leaking into prose, sentences that never answer the question.

It does **not** reliably catch external falsehood. The reviewers run the same 0.8b model as
the writer, so a wrong fact the writer believes is usually a wrong fact the reviewers
believe. `git branch -m` has been passed as a way to delete a branch, and the seasons have
been blamed on the Earth's spin. Closing that gap needs either a larger model for TRUTH in
the factual and technical profiles, or a tool the panel can check against.
