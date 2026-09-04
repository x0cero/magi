"""Newline-delimited JSON events, for a front end that is not a terminal.

The Mac app drives this rather than reimplementing the council, so there is one
copy of the personas, the validators and the grounding rules, and the eval
harness measures the same code the app runs. That only holds if this module
stays a thin translation of the generators in `core`: no decisions are made
here, and nothing is scored here.

The contract, one JSON object per line on stdout, flushed as it happens:

    {"event": "council",  "models": {NAME: model_id}, "version": "0.14.0"}
    {"event": "turn",     "thread": str, "turn": int, "text": str}
    {"event": "warming",  "member": NAME, "state": "loading"|"ready"|"failed"}
    {"event": "intake",   "mode": "decision"|"choice"|"open"|"noise", "decision": str,
                          "options": [str]}
    {"event": "round",    "round": int}
    {"event": "vote",     "member": NAME, "round": 1, ...position}
    {"event": "revote",   "member": NAME, ...position}
    {"event": "rebuttal", "member": NAME, "round": int, ...position,
                          "response": str, "changed": bool}
    {"event": "verdict",  "outcome": str, "synthesis": str,
                          "positions": {NAME: position}, "entry": str}
    {"event": "thread",   "thread": str, "turns": [journal entries]}
    {"event": "error",    "message": str}
    {"event": "end"}

A `position` carries whichever of `verdict`, `option` or `recommendation`
applies to the mode, plus `reasoning`, `finding`, `confidence` and `condition`.
Front ends should ignore event types and keys they do not know: this stream
gains fields over time and the app must not break when it does.

`magi stream "question"` runs one turn and exits. `magi stream` with no
question is a session: one line on stdin per turn, the thread kept between
them so a follow-up is evidence for the running argument rather than a new
question. Two control lines: `/new` starts a fresh thread, `/resume <thread>`
rebuilds one from the journal and replays it as a `thread` event. `end` is
emitted once, at EOF.
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


class StreamSession:
    """One council, many turns. Holds the thread between questions."""

    def __init__(self, models: dict[str, str]) -> None:
        self.models = models
        self.deliberation: Deliberation | None = None
        self.thread: str | None = None
        self.turn = 0

    async def warm(self) -> bool:
        from magi.warmup import warmup_models

        try:
            async for member, model_id, failure in warmup_models(self.models):
                emit("warming", member=member, model=model_id,
                     state="failed" if failure else "ready",
                     error=type(failure).__name__ if failure else None)
        except OllamaUnavailable as exc:
            emit("error", message=str(exc))
            return False
        return True

    def new_thread(self) -> None:
        self.deliberation = None
        self.thread = None
        self.turn = 0

    def resume(self, thread_id: str) -> bool:
        from magi import journal

        turns = journal.load_thread(thread_id)
        if not turns:
            emit("error", message=f"no thread {thread_id} in the journal")
            return False
        self.deliberation = Deliberation.from_journal(list(self.models.keys()), turns)
        self.thread = thread_id
        self.turn = len(turns)
        emit("thread", thread=thread_id, turns=turns)
        return True

    async def run_turn(self, question: str) -> int:
        from magi import journal

        if self.deliberation is None:
            self.deliberation = Deliberation(list(self.models.keys()))
        deliberation = self.deliberation
        deliberation.add_user_message(question)
        self.turn += 1
        if self.thread is None:
            self.thread = journal.new_thread_id()
        emit("turn", thread=self.thread, turn=self.turn, text=question)

        # A follow-up is evidence for the running argument. Sending it back
        # through intake bounced "i have a tested rollback" as noise once.
        is_followup = self.turn > 1 and deliberation.mode is not None
        if is_followup:
            mode = deliberation.mode
            options = list(deliberation.options)
            decision = ""
        else:
            try:
                classification = await classify_safe(question)
            except OllamaUnavailable as exc:
                emit("error", message=str(exc))
                return 2
            mode = classification.question_class.value
            options = list(classification.options)
            decision = classification.decision
            deliberation.frame(decision)
        emit("intake", mode=mode, options=options, decision=decision)

        if mode == QuestionClass.NOISE.value:
            emit("verdict", outcome="noise", synthesis="NOISE: not a question", positions={})
            # Roll it back so the next real question does not see "hello"
            # sitting in every member's history.
            for hist in deliberation.histories.values():
                if hist and hist[-1]["role"] == "user":
                    hist.pop()
            self.turn -= 1
            if self.turn == 0:
                self.new_thread()
            return 0

        deliberation.mode = mode
        deliberation.options = options
        models = self.models

        if mode == QuestionClass.CHOICE.value and len(options) >= 2:
            generator = iterative_choose(deliberation, models, options)
            finish = lambda pos, outcome: synthesize_choice(pos, outcome, options)  # noqa: E731
        elif mode == QuestionClass.OPEN.value:
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
            return 2

        synthesis = finish(positions, outcome)
        flat = {name: position(name, value) for name, value in positions.items()}
        entry_id = ""
        if flat:
            try:
                entry_id = journal.save_entry(
                    question=question,
                    members=list(positions.keys()),
                    rounds=round_num,
                    outcome=outcome,
                    synthesis=synthesis,
                    final_verdicts={name: _stance(data) for name, data in flat.items()},
                    thread=self.thread,
                    turn=self.turn,
                    mode=mode,
                    options=options,
                    decision=decision,
                    positions={name: value.model_dump(mode="json")
                               for name, value in positions.items()
                               if hasattr(value, "model_dump")},
                )
            except Exception as exc:  # the journal must never take the answer down with it
                emit("error", message=f"journal write failed: {type(exc).__name__}")
        emit("verdict", outcome=outcome, synthesis=synthesis, positions=flat,
             thread=self.thread, entry=entry_id)
        return 0


async def stream_question(question: str, models: dict[str, str], warm: bool = True) -> int:
    """Run one question, emitting events. Returns a process exit code."""
    from magi import __version__

    emit("council", models=dict(models), version=__version__, protocol=PROTOCOL_VERSION)
    session = StreamSession(models)
    if warm and not await session.warm():
        emit("end")
        return 2
    code = await session.run_turn(question)
    emit("end")
    return code


async def stream_session(models: dict[str, str], warm: bool = True) -> int:
    """Read turns from stdin until EOF, keeping the thread between them."""
    import asyncio

    from magi import __version__

    emit("council", models=dict(models), version=__version__, protocol=PROTOCOL_VERSION)
    session = StreamSession(models)
    if warm and not await session.warm():
        emit("end")
        return 2

    loop = asyncio.get_running_loop()
    code = 0
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        text = line.strip()
        if not text:
            continue
        if text == "/new":
            session.new_thread()
            continue
        if text.startswith("/resume "):
            session.resume(text.split(None, 1)[1].strip())
            continue
        code = await session.run_turn(text)
    emit("end")
    return code


def _stance(data: dict) -> str:
    return str(data.get("verdict") or data.get("option") or data.get("recommendation") or "")
