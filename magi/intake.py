"""Intake classifier. Routes questions to the right deliberation mode."""

import os
import re
from enum import Enum

import httpx
from pydantic import BaseModel, Field

from magi import providers

CLASSIFIER_MODEL = os.environ.get("MAGI_CLASSIFIER_MODEL", "qwen3:4b")


class QuestionClass(str, Enum):
    DECISION = "decision"
    CHOICE = "choice"
    OPEN = "open"
    PREDICTION = "prediction"
    NOISE = "noise"


class Classification(BaseModel):
    question_class: QuestionClass = Field(
        ...,
        description=(
            "decision: a yes/no question about ONE specific action ('should I take the job?', 'should I open source X?'). "
            "choice: pick between TWO OR MORE named options ('Swift or React Native?', 'Miami or Austin?'). "
            "open: open-ended request for direction with no fixed options ('what should I build?', 'i wanna make something cool'). "
            "prediction: a question about whether something WILL happen ('will my startup hit profitability?', 'am I going to get accepted?'). "
            "A STATEMENT is not noise: 'i keep putting off the dentist', 'im thinking about quitting', 'i cant decide on the car' are DECISIONS with the action implied. "
            "noise: ONLY greetings ('hi', 'hello', 'sup'), tests ('test', 'asdf'), pure punctuation ('???'), acknowledgements ('ok thanks'). "
            "If the input has ANY question structure (a '?', a 'should', 'or', 'what', 'will', 'how'), it is NOT noise."
        ),
    )
    decision: str = Field(
        default="",
        description=(
            "ONLY when the input is a statement rather than a question: the yes/no decision hiding in it, "
            "as one short 'should I ...' line built from the user's OWN words. Add nothing they did not say. "
            "Empty string when the input is already a question, or is noise."
        ),
    )
    options: list[str] = Field(
        default_factory=list,
        description=(
            "ONLY for choice questions: the named options the user is choosing between, in the order mentioned. "
            "Each option is a short noun/phrase (e.g. ['Swift', 'React Native']). "
            "Empty list for decision/open/prediction/noise."
        ),
    )


_CLASSIFIER_SYSTEM = """You classify a user's input into ONE of five shapes so a downstream system knows how to handle it.

decision    — yes/no question about ONE specific action. Examples: "should I take the job?", "should I move out?", "should we ship this?"
choice      — pick between two or more named options. Examples: "Swift or React Native?", "Miami, Austin, or Denver?", "should I go to MIT or Stanford?"
open        — open-ended ask for direction with no fixed options. Examples: "what should I build?", "i wanna make a new project something cool", "what do I do with my life?"
prediction  — will X happen / forecast. Examples: "will my startup hit profitability?", "am I going to get accepted?", "is the market going to crash?"
noise       — ONLY greetings, tests, gibberish, acknowledgements. Examples: "hello", "hi", "hey", "yo", "sup", "test", "testing", "asdf", "???", "ok thanks", "got it", "cool", "helllo" (typo'd greeting), single ambiguous words with no question mark ("water", "money").

STATEMENTS ARE NOT NOISE. People who cannot decide rarely ask a clean question; they describe the mess. Any statement about something the user is doing, avoiding, wanting, or stuck on is a DECISION (or a CHOICE if it names options). Fill `decision` with the yes/no action hiding in it, in the user's own words:
- "i keep putting off calling the dentist" — DECISION, decision: "should I call the dentist"
- "im thinking about quitting my job" — DECISION, decision: "should I quit my job"
- "i cant decide between the civic and the corolla" — CHOICE, options: [civic, corolla]
- "my landlord raised rent again" — DECISION, decision: "should I move out"
- "i want to build something cool" — OPEN

For choice questions ONLY, also extract the named options. Keep each option short (a single noun or short phrase). Order them as the user mentioned them.

Edge cases:
- "should I do A or B" — that's CHOICE (options: [A, B]), not decision, even though it starts with 'should'.
- "what should I do, A or B" — also CHOICE (options: [A, B]).
- "should I do anything" / "what should I do" with no options — OPEN, not decision.
- "should I bet on X" — DECISION, not prediction (already framed as a decision).
- Vague pitches like "i wanna build something cool" — OPEN, not noise.
- "hi, should I take the job?" — DECISION. A greeting prefix doesn't make a real question into noise.
- "water?" — DECISION (single-word question with '?' is a real ask, NOT noise).
- "hello" / "helllo" / "hi" with no other content — NOISE.
- ANY input with a '?', 'should', 'or', 'what', 'will', 'how', 'is it' — NOT noise.
- Anything three words or longer that is not a greeting — NOT noise. When in doubt, DECISION.

Return only the classification. Do not explain.
"""


_GREETINGS = {
    "hi", "hello", "hey", "yo", "sup", "hiya", "howdy", "test", "testing",
    "ok", "okay", "thanks", "thank", "you", "got", "it", "cool", "nice",
    "lol", "k", "kk", "yes", "no", "yep", "nope", "asdf", "hmm", "hm",
}


def looks_like_noise(text: str) -> bool:
    """Whether the input could possibly be noise.

    The classifier used to bounce statements like "i keep putting off the
    dentist" as noise, which is exactly how an undecided person talks. The
    model's NOISE verdict is now only honoured for inputs this guard also
    accepts: two words or fewer, or every word a greeting/acknowledgement.
    """
    words = [w for w in re.findall(r"[a-z']+", text.lower())]
    if len(words) <= 2:
        return True
    return all(w in _GREETINGS for w in words)


def _framing_is_grounded(decision: str, question: str) -> bool:
    """The framing may only restate the user. A figure they never gave is
    an invented premise before the council has even spoken."""
    from magi.grounding import figures
    return not (figures(decision) - figures(question))


def _settle(classification: Classification, question: str) -> Classification:
    if classification.question_class == QuestionClass.NOISE and not looks_like_noise(question):
        classification.question_class = QuestionClass.DECISION
    if classification.question_class == QuestionClass.NOISE:
        classification.decision = ""
    decision = classification.decision.strip().strip('"')
    if decision and not _framing_is_grounded(decision, question):
        decision = ""
    classification.decision = decision
    return classification


async def classify(question: str) -> Classification:
    """Classify a user's question. Returns Classification or raises on failure
    (caller should fall back to DECISION on exception)."""
    schema = Classification.model_json_schema()
    async with httpx.AsyncClient() as client:
        raw = await providers.chat(
            client,
            CLASSIFIER_MODEL,
            _CLASSIFIER_SYSTEM,
            [{"role": "user", "content": question}],
            schema,
            temperature=0.1,
            timeout=30.0,
        )
        from magi.core import _sanitize_llm_output, _strip_thinking
        parsed = Classification.model_validate_json(_strip_thinking(_sanitize_llm_output(raw)))
        return _settle(parsed, question)


async def classify_safe(question: str) -> Classification:
    """classify() but never raises. Falls back to DECISION on error."""
    try:
        return await classify(question)
    except Exception:
        return Classification(question_class=QuestionClass.DECISION, options=[])
