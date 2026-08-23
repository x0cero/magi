"""Intake classifier. Routes questions to the right deliberation mode."""

import os
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
            "noise: NOT a question — greetings ('hi', 'hello', 'sup'), tests ('test', 'asdf'), pure punctuation ('???'), acknowledgements ('ok thanks'). "
            "If the input has ANY question structure (a '?', a 'should', 'or', 'what', 'will', 'how'), it is NOT noise."
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
noise       — NOT a question. Greetings, tests, gibberish, acknowledgements. The council has nothing to deliberate. Examples: "hello", "hi", "hey", "yo", "sup", "test", "testing", "asdf", "???", "ok thanks", "got it", "cool", "helllo" (typo'd greeting), single ambiguous words with no question mark ("water", "money").

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

Return only the classification. Do not explain.
"""


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
        return Classification.model_validate_json(_strip_thinking(_sanitize_llm_output(raw)))


async def classify_safe(question: str) -> Classification:
    """classify() but never raises. Falls back to DECISION on error."""
    try:
        return await classify(question)
    except Exception:
        return Classification(question_class=QuestionClass.DECISION, options=[])
