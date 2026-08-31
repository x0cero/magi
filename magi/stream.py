"""Newline-delimited JSON events, for a front end that is not a terminal.

The Mac app drives this rather than reimplementing the council, so there is one
copy of the personas, the validators and the grounding rules, and the eval
harness measures the same code the app runs. That only holds if this module
stays a thin translation of the generators in `core`: no decisions are made
here, and nothing is scored here.

The contract, one JSON object per line on stdout, flushed as it happens:

    {"event": "council",  "models": {NAME: model_id}, "version": "0.14.0"}
    {"event": "warming",  "member": NAME, "state": "loading"|"ready"|"failed"}
    {"event": "intake",   "mode": "decision"|"choice"|"open"|"noise",
                          "options": [str]}
    {"event": "round",    "round": int}
    {"event": "vote",     "member": NAME, "round": 1, ...position}
    {"event": "revote",   "member": NAME, ...position}
    {"event": "rebuttal", "member": NAME, "round": int, ...position,
                          "response": str, "changed": bool}
    {"event": "verdict",  "outcome": str, "synthesis": str,
                          "positions": {NAME: position}}
    {"event": "error",    "message": str}
    {"event": "end"}

A `position` carries whichever of `verdict`, `option` or `recommendation`
applies to the mode, plus `reasoning`, `finding`, `confidence` and `condition`.
Front ends should ignore event types and keys they do not know: this stream
gains fields over time and the app must not break when it does.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from magi.core import (
    Deliberation,
    OllamaUnavailable,
    iterative_choose,
    iterative_deliberate,
    iterative_recommend,
    synthesize,
    synthesize_choice,
    synthesize_recommend,
)
from magi.intake import QuestionClass, classify_safe
from magi.personas import lens_field_label

PROTOCOL_VERSION = 1


def emit(event: str, **fields: Any) -> None:
    """One line, flushed. The app renders as events land, so a buffered stream
    would arrive as a single burst at the end and lose the whole point."""
    payload = {"event": event, **fields}
    sys.stdout.write(json.dumps(payload, default=str) + "\n")
    sys.stdout.flush()


def position(member: str, result: Any) -> dict:
    """Flatten one member's stance into the shape the front end draws.

    Deliberately not `model_dump()`: that leaks pydantic's field names and
    would tie the app's rendering to the schema's internals, so adding a
    validator field would silently change the wire format.
    """
    if isinstance(result, Exception):
        return {"failed": True, "error": type(result).__name__}

    verdict = getattr(result, "verdict", None) or getattr(result, "final_verdict", None)
    out: dict = {
        "reasoning": getattr(result, "reasoning", "") or "",
        "finding": getattr(result, "lens_finding", "") or "",
        "lens": lens_field_label(member),
        "confidence": getattr(result, "confidence", None),
    }
    if verdict is not None:
        out["verdict"] = getattr(verdict, "value", str(verdict))
        out["verdict_key"] = getattr(verdict, "name", "")
    option = getattr(result, "chosen_option", None) or getattr(result, "final_choice", None)
    if option:
        out["option"] = option
    recommendation = getattr(result, "recommendation", None)
    if recommendation:
        out["recommendation"] = recommendation
    condition = getattr(result, "condition", "") or ""
    if condition:
        out["condition"] = condition
    return out


async def stream_question(question: str, models: dict[str, str], warm: bool = True) -> int:
    """Run one question, emitting events. Returns a process exit code."""
    from magi import __version__

    emit("council", models=dict(models), version=__version__, protocol=PROTOCOL_VERSION)

    if warm:
        from magi.warmup import warmup_models

        try:
            async for member, model_id, failure in warmup_models(models):
                emit("warming", member=member, model=model_id,
                     state="failed" if failure else "ready",
                     error=type(failure).__name__ if failure else None)
        except OllamaUnavailable as exc:
            emit("error", message=str(exc))
            emit("end")
            return 2

    deliberation = Deliberation(list(models.keys()))
    deliberation.add_user_message(question)

    try:
        classification = await classify_safe(question)
    except OllamaUnavailable as exc:
        emit("error", message=str(exc))
        emit("end")
        return 2

    mode = classification.question_class.value
    options = list(classification.options)
    emit("intake", mode=mode, options=options)

    if classification.question_class == QuestionClass.NOISE:
        emit("verdict", outcome="noise", synthesis="NOISE: not a question", positions={})
        emit("end")
        return 0

    if classification.question_class == QuestionClass.CHOICE and len(options) >= 2:
        generator = iterative_choose(deliberation, models, options)
        finish = lambda pos, outcome: synthesize_choice(pos, outcome, options)  # noqa: E731
    elif classification.question_class == QuestionClass.OPEN:
        generator = iterative_recommend(deliberation, models)
        finish = lambda pos, _outcome: synthesize_recommend(pos)  # noqa: E731
    else:
        generator = iterative_deliberate(deliberation, models)
        finish = lambda pos, outcome: synthesize(pos, outcome=outcome)  # noqa: E731

    round_num = 1
    stances: dict[str, str] = {}
    outcome, positions = "incomplete", {}

    try:
        async for event in generator:
            kind = event[0]
            if kind == "round_start":
                round_num = event[1]
                emit("round", round=round_num)
            elif kind in ("vote", "revote"):
                _, member, payload = event
                data = position(member, payload)
                stances[member] = _stance(data)
                emit(kind, member=member, round=round_num, **data)
            elif kind == "rebuttal":
                _, member, payload = event
                data = position(member, payload)
                # `changed` is the thing the display animates on, and only this
                # layer knows the previous stance, so it is computed here rather
                # than left for the front end to track.
                data["changed"] = member in stances and _stance(data) != stances[member]
                data["response"] = getattr(payload, "response", "") or ""
                stances[member] = _stance(data)
                emit("rebuttal", member=member, round=round_num, **data)
            elif kind == "done":
                _, outcome, positions = event
    except OllamaUnavailable as exc:
        emit("error", message=str(exc))
        emit("end")
        return 2

    emit(
        "verdict",
        outcome=outcome,
        synthesis=finish(positions, outcome),
        positions={name: position(name, value) for name, value in positions.items()},
    )
    emit("end")
    return 0


def _stance(data: dict) -> str:
    return str(data.get("verdict") or data.get("option") or data.get("recommendation") or "")
