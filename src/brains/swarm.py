"""Stream generated text; after every sentence M1-M6 review it and GOD decides if it stays."""
import json
import logging
import re
from collections.abc import Callable, Iterator
from difflib import SequenceMatcher
from typing import NamedTuple

from brains.agents import (AGENTS, AgentError, ask, ask_all, chat_body, flags, lens, load,
                           post, route, verdict, veto)

log = logging.getLogger(__name__)

SENTENCE_END = re.compile(r"(?<!\d)[.!?][\"')\]]?\s*$")  # "2." is a list marker, not an end
REVIEW = "Question asked:\n{prompt}\n\nAnswer so far, review it:\n{text}"
JUDGE = ("Question asked:\n{prompt}\n\nAnswer so far:\n{text}\n\nLatest sentence:\n{sentence}\n\n"
         "Reviews:\n{reviews}")
REVIEW_CHARS = 400  # ponytail: trim each review, six full ones overflow a default 4k context
REDO = ("Your last sentence was rejected.\nRejected sentence: {sentence}\n"
        "Editor: {reason}\nReviewers said:\n{verdicts}\n"
        "Reply with a replacement for that one sentence, then carry on with the answer. "
        "Do not repeat any earlier sentence, and never mention the editor or the reviewers.")
CARRY_ON = "Carry on with the answer from where it stops. Do not repeat any earlier sentence."
MAX_REDOS = 2  # ponytail: per sentence, so a stubborn model cannot loop forever
MIN_SENTENCES = 3    # a redo makes the writer stop early, so nudge it to keep going
MAX_CARRY_ONS = 2
LIST_MARKER = re.compile(r"^\s*(\d+[.)]|[-*])\s*")  # the writer numbers its sentences


class Step(NamedTuple):
    sentence: str       # the sentence just written
    reviews: dict[str, str]  # {agent: full review}
    decision: str       # GOD's call: keep or regenerate
    reason: str         # why
    kept: bool          # False only if it is actually being rewritten
    text: str           # the answer so far, rejected sentences excluded


def repeats(sentence: str, accepted: str, ratio: float = 0.75) -> bool:
    """True if this sentence is one already accepted, word for word or reworded."""
    if sentence in accepted:
        return True
    return any(SequenceMatcher(None, sentence.lower(), s.lower() + ".").ratio() > ratio
               for s in accepted.lower().split(". ") if s)


def is_sentence(new_text: str) -> bool:
    """New text worth reviewing - not blank, not a bare list marker, not mid-code-span.

    A dot inside `open("f").read()` is not the end of a sentence, so an unclosed
    backtick means the sentence is not finished yet.
    """
    return len(re.findall(r"[A-Za-z]", new_text)) >= 3 and new_text.count("`") % 2 == 0


def stream_chat(cfg: dict, messages: list[dict[str, str]]) -> Iterator[str]:
    """Yield an Ollama reply chunk by chunk."""
    with post(chat_body(cfg, messages, stream=True)) as r:
        for line in r:
            if not line.strip():
                continue
            try:
                yield json.loads(line)["message"]["content"]
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                raise AgentError(f"Bad chunk from Ollama: {line[:120]!r} ({e})") from e


def generate(prompt: str, name: str = "GEN", profile: str | None = None) -> Iterator[str]:
    """Yield the writer's reply chunk by chunk, no reviewing."""
    cfg = load(name, profile or route(prompt))
    yield from stream_chat(cfg, [
        {"role": "system", "content": cfg["instructions"].strip()},
        {"role": "user", "content": prompt},
    ])


def verdict_lines(reviews: dict[str, str], profile: str) -> str:
    """The six verdicts, one per line, e.g. "M1 (truth and evidence): unsupported"."""
    return "\n".join(f"{n} ({lens(n, profile)}): {verdict(r, n, profile)}"
                     for n, r in reviews.items())


def review_digest(reviews: dict[str, str], profile: str) -> str:
    """Each reviewer's verdict plus what it actually said - the reasons the verdict drops."""
    return "\n\n".join(
        f"{n} ({lens(n, profile)}) says {verdict(r, n, profile)}:"
        f"\n{' '.join(r.split())[:REVIEW_CHARS]}"
        for n, r in reviews.items())


def judge(prompt: str, text: str, sentence: str, reviews: dict[str, str],
          profile: str) -> tuple[str, str]:
    """GOD rules on the flagged reviews and returns (keep|regenerate, reason).

    Nothing flagged means nothing to rule on, so GOD is not called at all.
    """
    for n, r in reviews.items():  # a veto needs no editor: the sentence goes back
        v = verdict(r, n, profile)
        if v in veto(n, profile):
            return "regenerate", f"{n} ({lens(n, profile)}) says {v}, which is not allowed"
    flagged = {n: r for n, r in reviews.items() if verdict(r, n, profile) in flags(n, profile)}
    if not flagged:
        return "keep", "no reviewer flagged it"
    reply = ask("GOD", JUDGE.format(prompt=prompt, text=text, sentence=sentence,
                                    reviews=review_digest(flagged, profile)), profile)
    reason = re.search(r"REASON:\s*(.+)", reply)
    decision = verdict(reply, "GOD", profile)
    why = reason.group(1).strip() if reason else reply.strip()
    log.info("GOD: %s - %s", decision, why)
    return decision, why


def generate_reviewed(prompt: str, name: str = "GEN",
                      on_chunk: Callable[[str], None] | None = None,
                      profile: str | None = None) -> Iterator[Step]:
    """Stream an answer sentence by sentence.

    GOD picks the profile from the question unless one is passed. Each finished sentence is
    reviewed by all six agents of that profile at once, then GOD decides. On
    'regenerate' the sentence is dropped and the writer redoes it with GOD's reason as input.
    Yields a Step for every attempt, kept or not.
    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise AgentError("prompt must be a non-empty string")
    profile = profile or route(prompt)  # GOD picks the panel before a word is written
    cfg = load(name, profile)
    log.info("PROMPT (%s): %s", profile, prompt)
    accepted, redo, redos = "", "", 0
    kept_count, carry_ons = 0, 0
    while True:
        messages = [{"role": "system", "content": cfg["instructions"].strip()},
                    {"role": "user", "content": prompt}]
        if accepted:
            messages.append({"role": "assistant", "content": accepted})
        if redo:
            messages.append({"role": "user", "content": redo})

        buf, restart = "", False
        for chunk in stream_chat(cfg, messages):
            if on_chunk:
                on_chunk(chunk)
            buf += chunk
            sentence = LIST_MARKER.sub("", buf.strip())
            if not (SENTENCE_END.search(sentence) and is_sentence(sentence)):
                continue
            if repeats(sentence, accepted):  # writer restarted, or said it again in new words
                log.info("SKIPPED REPEAT: %s", sentence)
                buf = ""
                continue
            text = f"{accepted} {sentence}".strip()
            reviews = ask_all(dict.fromkeys(AGENTS, REVIEW.format(prompt=prompt, text=text)),
                              profile)
            decision, reason = judge(prompt, text, sentence, reviews, profile)
            log.info("SENTENCE: %s", sentence)
            log.info("VERDICTS: %s", verdict_lines(reviews, profile).replace("\n", " | "))
            rewriting = decision == "regenerate" and redos < MAX_REDOS
            if decision == "regenerate" and not rewriting:
                log.warning("kept after %d redos, giving up on: %s", redos, sentence)
            yield Step(sentence, reviews, decision, reason, not rewriting,
                       accepted if rewriting else text)
            if rewriting:
                redo = REDO.format(sentence=sentence, reason=reason,
                                   verdicts=verdict_lines(reviews, profile))
                redos, restart = redos + 1, True
                log.info("REDO %d SENT TO WRITER:\n%s", redos, redo)
                break  # drop the sentence, restart the stream with GOD's reason
            accepted, buf, redo, redos = text, "", "", 0
            kept_count += 1
        if restart:
            continue
        if kept_count < MIN_SENTENCES and carry_ons < MAX_CARRY_ONS:
            carry_ons, redo = carry_ons + 1, CARRY_ON  # writer stopped early, nudge it
            log.info("CARRY ON %d after %d sentences", carry_ons, kept_count)
            continue
        log.info("FINAL: %s", accepted)
        return
