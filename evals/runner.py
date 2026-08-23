"""Runs the suite through the real MAGI pipeline and records everything.

Deliberately uses the same code paths the REPL uses (intake classifier +
iterative_* generators) so an eval measures the product, not a stub of it.
"""

import json
import time
from pathlib import Path

from magi.core import (
    Deliberation,
    iterative_choose,
    iterative_deliberate,
    iterative_recommend,
    synthesize,
    synthesize_choice,
    synthesize_recommend,
)
from magi.intake import QuestionClass, classify_safe


def _dump(position) -> dict:
    if isinstance(position, Exception):
        return {"error": f"{type(position).__name__}: {position}"}
    if hasattr(position, "model_dump"):
        data = position.model_dump()
        return {k: (v.value if hasattr(v, "value") else v) for k, v in data.items()}
    return {"value": str(position)}


async def run_question(q: dict, models: dict[str, str]) -> dict:
    """Run one question end to end. Never raises — failures land in 'error'."""
    started = time.monotonic()
    record: dict = {
        "id": q["id"],
        "text": q["text"],
        "expect_mode": q["expect_mode"],
        "divergent": q["divergent"],
        "models": dict(models),
        "round1_positions": {},
        "final_positions": {},
        "rounds": 0,
        "outcome": None,
        "synthesis": None,
        "mode": None,
        "error": None,
    }

    try:
        classification = await classify_safe(q["text"])
        mode = classification.question_class.value
        record["mode"] = mode
        record["options"] = list(classification.options)

        if classification.question_class == QuestionClass.NOISE:
            record["outcome"] = "noise"
            record["synthesis"] = "NOISE: not a question"
            record["elapsed"] = time.monotonic() - started
            return record

        deliberation = Deliberation(list(models.keys()))
        deliberation.add_user_message(q["text"])

        is_choice = (
            classification.question_class == QuestionClass.CHOICE
            and len(classification.options) >= 2
        )
        if is_choice:
            stream = iterative_choose(deliberation, models, classification.options)
        elif classification.question_class == QuestionClass.OPEN:
            stream = iterative_recommend(deliberation, models)
        else:
            stream = iterative_deliberate(deliberation, models)

        round_num = 0
        finals: dict = {}
        async for event in stream:
            kind = event[0]
            if kind == "round_start":
                round_num = event[1]
                record["rounds"] = max(record["rounds"], round_num)
            elif kind == "vote":
                record["round1_positions"][event[1]] = _dump(event[2])
            elif kind == "revote":
                # A member was sent back for echoing, arguing from another
                # lens, or asserting a fact the question never gave. The
                # corrected answer is what the user actually sees, so that is
                # what gets scored; the original is kept so retries can be
                # measured rather than assumed.
                name = event[1]
                record.setdefault("pre_retry_positions", {})[name] = \
                    record["round1_positions"].get(name)
                record["round1_positions"][name] = _dump(event[2])
            elif kind == "rebuttal":
                record.setdefault("rebuttals", {}).setdefault(str(round_num), {})[event[1]] = _dump(event[2])
            elif kind == "done":
                record["outcome"] = event[1]
                finals = event[2]
                record["final_positions"] = {n: _dump(p) for n, p in finals.items()}

        if is_choice:
            record["synthesis"] = synthesize_choice(finals, record["outcome"], classification.options)
        elif classification.question_class == QuestionClass.OPEN:
            record["synthesis"] = synthesize_recommend(finals)
        else:
            record["synthesis"] = synthesize(finals, outcome=record["outcome"] or "auto")

    except Exception as e:  # a broken run is data, not a crash
        record["error"] = f"{type(e).__name__}: {e}"

    record["elapsed"] = time.monotonic() - started
    return record


async def run_suite(questions: list[dict], models: dict[str, str], out_path: Path,
                    progress=None) -> list[dict]:
    """Sequential on purpose: concurrent questions would contend for the same
    Ollama GPU and make the latency numbers meaningless."""
    results = []
    out_path.parent.mkdir(parents=True, exist_ok=True)
    for i, q in enumerate(questions, 1):
        if progress:
            progress(i, len(questions), q)
        result = await run_question(q, models)
        results.append(result)
        # write after every question so a long run is never lost
        out_path.write_text(json.dumps(
            {"models": models, "results": results}, indent=2, default=str
        ))
    return results
