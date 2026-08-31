import asyncio
import re
from enum import Enum
from typing import AsyncIterator

import httpx
from pydantic import BaseModel, Field, model_validator

from magi import providers
from magi.grounding import figures, premise_hits, stems
from magi.personas import (
    get_choice_prompt,
    get_decision_prompt,
    get_recommend_prompt,
    lens_field_description,
    off_limits_term,
)
from magi.providers import MAX_RESPONSE_BYTES, OllamaUnavailable
from magi.textsim import is_echo

# Measured, not guessed: across the eval suite on v0.12, three rounds changed
# zero verdicts. Every question was already decided after round 1, and rounds
# 2-3 burned two thirds of the wall clock restating. One debate round keeps the
# part that earns its cost — members answering each other by name — and drops
# the part that does not. Raise it in config.toml under [options] max_rounds.
MAX_DELIBERATION_ROUNDS = 2
KEEP_ALIVE = "30m"
MAX_INPUT_CHARS = 10_000


def _wrap_connect_error(exc: Exception) -> Exception:
    if isinstance(exc, httpx.ConnectError):
        return OllamaUnavailable()
    return exc


# Measured on an M1 Max, all three warm and resident: one round of the council.
#
#   qwen3:14b + phi4 + hermes3:8b   (~25GB)   87s
#   qwen3:4b + dolphin3:8b + hermes3:8b (~15GB)  6.4s
#
# Three members run concurrently against one GPU, so they contend rather than
# parallelise: the round costs what the slowest member costs, and a 14B seat
# taxes every question. The council is a thing you ask on the way out the door.
# Anything that takes three minutes to answer "should I have coffee at 8pm" is
# not that, however good the answer is.
DEFAULT_MODELS = {
    "MELCHIOR": "qwen3:4b",
    "BALTHASAR": "dolphin3:8b",
    "CASPER": "hermes3:8b",
}


class Verdict(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    CONDITIONAL = "CONDITIONAL"


_BANNED_CONDITION_PHRASES = (
    "clear plan", "clear vision", "manageable scope", "sufficient resources",
    "realistic timeline", "long-term goals", "personal values",
    "regularly reassess", "explore additional resources",
    "concise mission statement", "balance ambition", "specific aspects",
    "core values", "well-defined goals", "proper preparation",
    "adequate funding", "solid foundation", "strong commitment",
    "careful consideration", "thorough research", "good understanding",
    "appropriate measures", "reasonable expectations",
)


_LENS_FINDING_FALLBACK = (
    "The ONE finding only YOUR lens produces, in under 20 words. Specific to THIS question. "
    "If another council member could have written it, it is wrong."
)

_CONFIDENCE_DESC = (
    "1-5: how hard you would defend this against the rest of the room. "
    "5 = you would stake the deliberation on it. 3 = you lean. 1 = a coin flip you had to call. "
    "Do not default to 4."
)


def resolve_max_rounds(explicit: int | None = None) -> int:
    """Explicit argument wins, then [options] max_rounds, then the default."""
    if explicit is not None:
        return explicit
    from magi.config import max_rounds as configured_max_rounds

    return configured_max_rounds(MAX_DELIBERATION_ROUNDS)


# The prompts ask for 1-3 sentences. Prompts alone do not hold: a chatty model
# runs to the token cap, and the tail is where sign-offs, encouragement and
# invented personal experience live. Trimming is deterministic and, unlike a
# max_length on the field, can never fail a member's whole response.
MAX_REASONING_SENTENCES = 3
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


# The finding is meant to be the one line you remember. "Under 20 words" in the
# schema is a suggestion a small model ignores; this makes it true.
MAX_FINDING_WORDS = 28


MIN_FINDING_WORDS = 5

# Where a long finding can be cut and still read as a finished thought.
# Punctuation first, then the subordinators that introduce an elaboration the
# line does not need.
_CLAUSE_BREAK = re.compile(
    r",|;|:|\s+—\s+|\s+-\s+"
    r"|\s+(?:which|that|because|since|so\s+that|whereas|while|unless|although|though)\s+",
    re.IGNORECASE,
)


def _trim_finding(text: str) -> str:
    """Cut a rambling finding down to its first claim.

    Only ever shortens something already too long, and prefers to stop
    somewhere the sentence was going to pause anyway. Cutting purely on a word
    count strands the line mid-phrase — a live run produced "...results in a
    prolonged outage or data integrity..." where the clean cut was the comma
    fifteen words earlier.

    Sentence splitting alone is also wrong here: "Target income per hour vs.
    client acquisition rate" looks like two sentences to any period-based
    splitter and gets guillotined into "Target income per hour vs."
    """
    text = (text or "").strip()
    words = text.split()
    if len(words) <= MAX_FINDING_WORDS:
        return text

    first = _trim_to_sentences(text, limit=1)
    first_words = first.split()
    if MIN_FINDING_WORDS <= len(first_words) <= MAX_FINDING_WORDS:
        return first

    capped = " ".join(words[:MAX_FINDING_WORDS])
    breaks = [m.start() for m in _CLAUSE_BREAK.finditer(capped)]
    for position in reversed(breaks):
        clause = capped[:position].strip().rstrip(",;:-—")
        if len(clause.split()) >= MIN_FINDING_WORDS:
            return clause

    return capped.rstrip(",;:-—") + "..."


def _trim_to_sentences(text: str, limit: int = MAX_REASONING_SENTENCES) -> str:
    text = (text or "").strip()
    if not text:
        return text
    sentences = _SENTENCE_SPLIT.split(text)
    if len(sentences) <= limit:
        return text
    return " ".join(sentences[:limit]).strip()


def _condition_is_vague(condition: str) -> bool:
    if not condition.strip():
        return True
    low = condition.lower()
    return any(phrase in low for phrase in _BANNED_CONDITION_PHRASES)


class PersonaResponse(BaseModel):
    verdict: Verdict
    reasoning: str = Field(
        ...,
        min_length=20,
        description="1-3 sharp DECLARATIVE sentences about the user's situation. State your read. Never end a sentence with '?'. Never ask the user clarifying questions. Minimum one complete sentence.",
    )
    lens_finding: str = Field(
        ...,
        min_length=3,
        description=_LENS_FINDING_FALLBACK,
    )
    confidence: int = Field(
        default=3,
        ge=1,
        le=5,
        description=_CONFIDENCE_DESC,
    )
    condition: str = Field(
        default="",
        description="REQUIRED when verdict=CONDITIONAL: ONE concrete blocker tied to specifics in THIS user's question (their actual numbers, people, constraints, situation). NOT a generic life-advice template. Banned vague phrases: 'clear plan', 'clear vision', 'manageable scope', 'sufficient resources', 'realistic timeline', 'long-term goals', 'mission statement', 'balance ambition', 'core values'. If you cannot name a blocker tied to real specifics, vote ACCEPT or REJECT instead. Empty string when verdict is ACCEPT or REJECT.",
    )

    @model_validator(mode="after")
    def _coerce_hedged_conditional(self):
        self.reasoning = _trim_to_sentences(self.reasoning)
        self.lens_finding = _trim_finding(self.lens_finding)
        if self.verdict == Verdict.CONDITIONAL and _condition_is_vague(self.condition):
            self.verdict = Verdict.ACCEPT
            self.condition = ""
        return self


class Rebuttal(BaseModel):
    response: str = Field(
        ...,
        min_length=20,
        description="1-3 DECLARATIVE sentences responding to the others by name. Push back, hold your line. Never address the user with questions. Never end a sentence with '?'. Minimum one complete sentence.",
    )
    final_verdict: Verdict
    confidence: int = Field(default=3, ge=1, le=5, description=_CONFIDENCE_DESC)
    condition: str = Field(
        default="",
        description="REQUIRED when final_verdict=CONDITIONAL: same rules as initial vote. A concrete blocker tied to specifics in THIS question, not a generic template. Banned vague phrases: same list as initial vote. Empty string for ACCEPT or REJECT.",
    )

    @model_validator(mode="after")
    def _coerce_hedged_conditional(self):
        # Small models narrate their own name into the rebuttal: dolphin3 opened
        # one with the literal string "BALTHASAR:". The stripper existed but was
        # only wired into recommend mode.
        self.response = _trim_to_sentences(_strip_persona_prefixes(self.response))
        if self.final_verdict == Verdict.CONDITIONAL and _condition_is_vague(self.condition):
            self.final_verdict = Verdict.ACCEPT
            self.condition = ""
        return self


class ChoiceResponse(BaseModel):
    chosen_option: str = Field(
        ...,
        min_length=1,
        description="The option you pick. Must EXACTLY match one of the options provided in the question (case-insensitive). Pick exactly one — no 'depends', no combining, no 'both'.",
    )
    reasoning: str = Field(
        ...,
        min_length=20,
        description="1-3 sharp DECLARATIVE sentences for why you picked this option over the others. State your read from your lens. Never address the user with questions. Never end a sentence with '?'.",
    )
    lens_finding: str = Field(..., min_length=3, description=_LENS_FINDING_FALLBACK)
    confidence: int = Field(default=3, ge=1, le=5, description=_CONFIDENCE_DESC)

    @model_validator(mode="after")
    def _trim(self):
        self.reasoning = _trim_to_sentences(self.reasoning)
        self.lens_finding = _trim_finding(self.lens_finding)
        return self


class ChoiceRebuttal(BaseModel):
    response: str = Field(
        ...,
        min_length=20,
        description="1-3 DECLARATIVE sentences responding to the others by name. Push back if their pick is wrong, hold your line. Never address the user with questions.",
    )
    final_choice: str = Field(
        ...,
        min_length=1,
        description="Your final pick this round. Same option as before OR changed only if a real argument moved you.",
    )
    confidence: int = Field(default=3, ge=1, le=5, description=_CONFIDENCE_DESC)

    @model_validator(mode="after")
    def _trim(self):
        self.response = _trim_to_sentences(_strip_persona_prefixes(self.response))
        return self


_BANNED_RECOMMENDATION_PHRASES = (
    "something you're passionate about", "something you are passionate about",
    "what aligns with your values", "aligns with your values",
    "a project that excites you", "what excites you most",
    "follow your heart", "follow your passion",
    "what feels right", "what resonates with you",
    "find your purpose", "discover your purpose",
    "anything that interests you", "whatever you want",
    "trust your gut",
    "consider building", "consider creating", "consider developing",
    "consider starting", "consider exploring", "consider pursuing",
    "consider trying", "consider playing", "consider reading",
    "consider watching", "consider learning", "consider taking",
    "look into", "explore options", "explore opportunities",
    "explore a ", "try a ", "play a ",
    "a project that addresses", "a project that solves",
    "a game with ", "a book with ", "a tool with ",
    "something that combines", "something that leverages",
    "something with a ", "an initiative that", "a venture that",
)


def _recommendation_is_vague(rec: str) -> bool:
    if len(rec.strip()) < 10:
        return True
    low = rec.lower()
    return any(phrase in low for phrase in _BANNED_RECOMMENDATION_PHRASES)


class RecommendResponse(BaseModel):
    recommendation: str = Field(
        ...,
        min_length=10,
        description=(
            "ONE concrete, specific recommendation. NAME IT. "
            "If the user asks for a game, name the game (e.g. 'Hades'). If they ask for a project, name the project. "
            "A category ('a game with X') is NOT a recommendation. A specific name IS. "
            "Do NOT start with 'Consider', 'Explore', 'Try', or 'A game with'. Just name the thing directly."
        ),
    )
    reasoning: str = Field(
        ...,
        min_length=20,
        description="1-3 sharp DECLARATIVE sentences for why YOUR LENS picks this. Never end a sentence with '?'. Never interview the user.",
    )

    @model_validator(mode="after")
    def _reject_vague(self):
        self.reasoning = _trim_to_sentences(self.reasoning)
        if _recommendation_is_vague(self.recommendation):
            raise ValueError(f"recommendation is too vague: {self.recommendation!r}")
        return self


class RecommendRebuttal(BaseModel):
    response: str = Field(
        ...,
        min_length=20,
        description="1-3 DECLARATIVE sentences responding to the others by name. Hold your line unless a real argument moved you.",
    )
    final_recommendation: str = Field(
        ...,
        min_length=10,
        description="Your final concrete recommendation this round. Same as before OR refined/changed only if persuaded. Same vagueness rules.",
    )

    @model_validator(mode="after")
    def _reject_vague(self):
        self.response = _trim_to_sentences(self.response)
        if _recommendation_is_vague(self.final_recommendation):
            raise ValueError(f"final_recommendation is too vague: {self.final_recommendation!r}")
        return self


class Deliberation:
    """Per-member message history across deliberation turns."""

    def __init__(self, member_names: list[str]) -> None:
        self.histories: dict[str, list[dict]] = {name: [] for name in member_names}
        # Set when the opening question is classified. Follow-up turns inherit
        # it: "i have a tested rollback and the team is on call" is new
        # evidence for a live thread, not a new question to be re-routed.
        self.mode: str | None = None
        self.options: list[str] = []

    def add_user_message(self, content: str) -> None:
        if len(content) > MAX_INPUT_CHARS:
            content = content[:MAX_INPUT_CHARS]
        for name in self.histories:
            self.histories[name].append({"role": "user", "content": content})

    def commit_response(self, name: str, response: PersonaResponse) -> None:
        self.histories[name].append({"role": "assistant", "content": response.model_dump_json()})

    def add_member(self, name: str) -> None:
        if name in self.histories:
            return
        if self.histories:
            sample = next(iter(self.histories.values()))
            self.histories[name] = [m for m in sample if m["role"] == "user"]
        else:
            self.histories[name] = []

    def remove_member(self, name: str) -> None:
        self.histories.pop(name, None)

    @property
    def question_text(self) -> str:
        """Everything the user actually said, which is the whole factual record.

        Read from the histories rather than kept alongside them, because the
        REPL rewrites the last user message in place to inject council memory.
        Anything in here was genuinely given to the members; anything outside
        it they made up.
        """
        if not self.histories:
            return ""
        hist = next(iter(self.histories.values()))
        return " ".join(m["content"] for m in hist if m["role"] == "user")

    @property
    def turn(self) -> int:
        if "MELCHIOR" in self.histories:
            return sum(1 for m in self.histories["MELCHIOR"] if m["role"] == "user")
        if self.histories:
            return sum(1 for m in next(iter(self.histories.values())) if m["role"] == "user")
        return 0


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)
_NAME_PREFIX = re.compile(
    r"^(MELCHIOR|BALTHASAR|CASPER|BANKER|THERAPIST|LAWYER|COACH|DOCTOR)(?:'s|s')?"
    r"(?:\s+(?:final\s+|my\s+)?(?:recommendation|recommends|pick|picks|verdict|votes|vote|choice|chooses|chose|says|said|decides|decided|answers|answer))?"
    r"\s*[:\-—]\s*",
    re.IGNORECASE,
)
_VERDICT_PREFIX = re.compile(r"^(ACCEPT|REJECT|CONDITIONAL)\s*[-—:]\s*", re.IGNORECASE)


# Cloud models that ignore schema-constrained decoding often wrap the JSON
# in markdown fences; local schema-constrained output never does.
_JSON_FENCE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def _strip_thinking(text: str) -> str:
    text = _THINK_BLOCK.sub("", text).strip()
    m = _JSON_FENCE.match(text)
    return m.group(1).strip() if m else text


def _strip_persona_prefixes(text: str) -> str:
    s = _sanitize_llm_output(text.strip())
    for _ in range(3):
        before = s
        s = _NAME_PREFIX.sub("", s).strip()
        s = _VERDICT_PREFIX.sub("", s).strip()
        if s == before:
            break
    return s


_REC_FILLER_PREFIX = re.compile(
    r"^(?:try|play|explore|check out|look into|consider(?: trying)?)\s+",
    re.IGNORECASE,
)


def _clean_recommendation(rec: str) -> str:
    rec = _sanitize_llm_output(rec.strip())
    rec = _strip_persona_prefixes(rec)
    rec = _REC_FILLER_PREFIX.sub("", rec).strip()
    return rec


def _check_response_size(response: httpx.Response) -> None:
    content_length = response.headers.get("content-length")
    if content_length and int(content_length) > MAX_RESPONSE_BYTES:
        raise ValueError(f"Ollama response too large ({content_length} bytes, cap {MAX_RESPONSE_BYTES})")
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise ValueError(f"Ollama response too large ({len(response.content)} bytes, cap {MAX_RESPONSE_BYTES})")


def _check_content_type(response: httpx.Response) -> None:
    ct = response.headers.get("content-type", "")
    if ct and "json" not in ct and "text" not in ct:
        raise ValueError(f"unexpected content-type from Ollama: {ct[:60]}")


_ANSI_ESCAPE = re.compile(
    r"\x1b\[[0-9;]*[A-Za-z]"       # CSI sequences
    r"|\x1b\][^\x07\x1b]*\x07"     # OSC terminated by BEL
    r"|\x1b\][^\x07\x1b]*\x1b\\"   # OSC terminated by ST
    r"|\x1b[^[(\n]"                 # other ESC sequences
)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_UNICODE_HAZARDS = re.compile(
    "["
    "\u200b-\u200f"
    "\u202a-\u202e"
    "\u2060-\u2069"
    "\ufeff"
    "\ufff9-\ufffc"
    "]"
)


def _sanitize_llm_output(text: str) -> str:
    text = _ANSI_ESCAPE.sub("", text)
    text = _CONTROL_CHARS.sub("", text)
    text = _UNICODE_HAZARDS.sub("", text)
    return text


def _validate_response(response: httpx.Response) -> None:
    _check_response_size(response)
    _check_content_type(response)


def _member_schema(model_cls: type[BaseModel], member: str) -> dict:
    """The member's own schema, with lens_finding described in that member's
    voice so constrained decoding enforces a lens-specific answer."""
    schema = model_cls.model_json_schema()
    props = schema.get("properties", {})
    if "lens_finding" in props:
        props["lens_finding"] = dict(props["lens_finding"])
        props["lens_finding"]["description"] = lens_field_description(member)
    return schema


async def _consult(
    client: httpx.AsyncClient,
    model: str,
    system: str,
    messages: list[dict],
    member: str,
) -> PersonaResponse:
    schema = _member_schema(PersonaResponse, member)
    raw = await providers.chat(client, model, system, messages, schema,
                               temperature=0.7, keep_alive=KEEP_ALIVE)
    content = _sanitize_llm_output(raw)
    return PersonaResponse.model_validate_json(_strip_thinking(content))


_ECHO_INSTRUCTION = (
    "STOP. {other} already made your exact argument:\n\n"
    '  "{other_text}"\n\n'
    "That is {other}'s lens, not yours. Restating it adds nothing to this council — "
    "the user already has that read. Answer again with the argument ONLY YOUR LENS can make. "
    "Different substance, not different wording.\n\n"
    "Keep your verdict if you still hold it. Only your reasoning and lens_finding must change."
)


async def _reconsult_without_echo(
    client: httpx.AsyncClient,
    model: str,
    system: str,
    messages: list[dict],
    member: str,
    own,
    other_name: str,
    other_text: str,
    response_cls=PersonaResponse,
    options: list[str] | None = None,
    nudge: str | None = None,
):
    """One corrective pass when a member restated somebody else's point.

    Temperature is raised for this call: the first answer was the obvious one,
    and asking the same model for a different argument at the same temperature
    tends to return the same argument.
    """
    nudge = nudge or _ECHO_INSTRUCTION.format(other=other_name, other_text=other_text)
    convo = (
        messages
        + [{"role": "assistant", "content": own.model_dump_json()}]
        + [{"role": "user", "content": nudge}]
    )
    schema = _member_schema(response_cls, member)
    raw = await providers.chat(client, model, system, convo, schema,
                               temperature=0.9, keep_alive=KEEP_ALIVE)
    content = _sanitize_llm_output(raw)
    parsed = response_cls.model_validate_json(_strip_thinking(content))
    if options and hasattr(parsed, "chosen_option"):
        parsed.chosen_option = _normalize_option(parsed.chosen_option, options)
    return parsed


async def _rebut(
    client: httpx.AsyncClient,
    model: str,
    system: str,
    messages: list[dict],
    own_position: PersonaResponse,
    others: dict[str, PersonaResponse],
    round_num: int,
    member: str = "",
    question: str = "",
    unverified: list[str] | None = None,
) -> Rebuttal:
    others_text = "\n\n".join(
        f"{name}: {r.verdict.value} (confidence {r.confidence}/5) — {r.reasoning}"
        + (f"\n  their {name.lower()} finding: {r.lens_finding}" if r.lens_finding else "")
        for name, r in others.items()
    )

    identity_anchor = (
        "REMEMBER: you are speaking ABOUT the user's situation. "
        "Use 'they' / 'the user' / 'their'. Never 'I' / 'my' / 'we'. "
        "The facts in this question belong to the user, not you."
    )

    if round_num == 2:
        opener = "The other council members have just voted. Here is what they said:"
        closer = (
            "Address them by name. Push back on what you disagree with. Point out "
            "what they missed. Stay in your lens. 1-3 sentences.\n\n"
            "Then give your final verdict for this round. HOLD YOUR LINE unless a "
            "real argument was made that exposed new information or a flaw in your "
            "reasoning. Convergence for its own sake is failure — if you still "
            "believe your verdict, keep it. Drifting to CONDITIONAL because others "
            "did is hedging, not deliberating. If you do vote CONDITIONAL, you must "
            "name ONE concrete blocker — no vague hedges."
        )
    else:
        opener = (
            f"This is round {round_num} of the deliberation. The other members' "
            "latest positions:"
        )
        closer = (
            "Respond to the latest points. HOLD YOUR LINE unless a real argument "
            "exposed new information or a flaw. Convergence for its own sake is "
            "failure. Stay in your lens. 1-3 sentences.\n\n"
            "Final verdict: same as last round OR updated only if you were "
            "genuinely persuaded by a specific argument. If CONDITIONAL, name ONE "
            "concrete blocker."
        )

    # Laundering is the harmful step and it happens here: in the live failure a
    # member invented a rollback window in round 1, then in round 2 cited its
    # own invention as something another member had "missed". Costs no extra
    # call, because this generation is already being made.
    known = ""
    if question:
        known = (
            "KNOWN FACTS — the user's question, complete:\n\n  "
            + question
            + "\n\nNothing outside that text is a fact about this user."
        )
        if unverified:
            known += (
                f" NOT ESTABLISHED: {', '.join(unverified)}. Nobody in this room has those "
                "facts, including you. If a member argues from one, say it was never stated "
                "and do not build on it."
            )
        known += "\n\n"

    debate_prompt = f"{known}{identity_anchor}\n\n{opener}\n\n{others_text}\n\n{closer}"

    schema = _member_schema(Rebuttal, member)
    debate_messages = (
        messages
        + [{"role": "assistant", "content": own_position.model_dump_json()}]
        + [{"role": "user", "content": debate_prompt}]
    )

    raw = await providers.chat(client, model, system, debate_messages, schema,
                               temperature=0.7, keep_alive=KEEP_ALIVE)
    content = _sanitize_llm_output(raw)
    return Rebuttal.model_validate_json(_strip_thinking(content))


def _position_text(position) -> str:
    """The substance of a position, for echo comparison."""
    reasoning = getattr(position, "reasoning", "") or ""
    finding = getattr(position, "lens_finding", "") or ""
    return f"{reasoning} {finding}".strip()


_OFF_LENS_INSTRUCTION = (
    'STOP. Your argument is built on "{term}", and money, runway and risk belong to '
    "MELCHIOR. He is already making that argument, so yours adds nothing.\n\n"
    "Answer again using only what YOUR lens sees. Do not mention {term} or anything "
    "like it. Keep your verdict if you still hold it — only the argument has to change."
)


def _find_off_lens(positions: dict) -> dict[str, str]:
    """Members arguing from territory their lens does not own."""
    found = {}
    for name, position in positions.items():
        term = off_limits_term(name, _position_text(position))
        if term:
            found[name] = term
    return found


_UNGROUNDED_INSTRUCTION = (
    'STOP. You stated something about the user that their question never said:\n\n'
    '  "{span}"\n\n'
    "Here is their question, complete and verbatim:\n\n  {question}\n\n"
    "That is the whole record. Anything outside it is absent, so vote on the situation as "
    "actually described; when the action is hard to undo, an absent safeguard counts against it.\n\n"
    "Answer again. Keep your verdict if you still hold it. Do not move the invented fact into "
    "`condition` — a blocker that supplies the missing fact is the same error in another field. "
    "Decide either way; refusing to decide is the worst outcome."
)


def _find_ungrounded(positions: dict, question: str) -> dict[str, str]:
    """Members asserting a specific about the user that the question never gave.

    Requires a novel *specific* (a figure, or a situational noun inside a
    factive frame), not merely novel vocabulary — a lens is supposed to bring
    words the question does not contain. Naming a fact as missing is the job;
    assuming it is the failure.
    """
    if len(question.split()) < 3:
        return {}
    q_stems, q_figs = stems(question), figures(question)
    found: dict[str, str] = {}
    for name, p in positions.items():
        for field in ("reasoning", "lens_finding", "condition"):
            for sent in _SENTENCE_SPLIT.split(str(getattr(p, field, "") or "").strip()):
                if sent and premise_hits(sent, q_stems, q_figs)[0]:
                    found[name] = sent.strip()
                    break
            if name in found:
                break
    return found


MAX_UNVERIFIED_TERMS = 5


# Members are consulted concurrently and collected as they finish, so the dict
# that comes back is in arrival order: whichever model happened to be fastest
# that millisecond. Downstream, that order is not cosmetic. The round-2 prompt
# lists the other two members in it, and _unverified_terms truncates to the
# first MAX_UNVERIFIED_TERMS it sees, so a different finishing order names a
# different set of invented specifics back to the council. Identical code
# scored 12, 13 and 17 fabricated premises across three runs, which made every
# A/B a coin flip. Council order is the canonical order everywhere past
# collection; specialists, which are not seated in DEFAULT_MODELS, follow in
# name order so they are stable too.
def _in_council_order(positions: dict, models: dict[str, str]) -> dict:
    ordered = {n: positions[n] for n in models if n in positions}
    rest = sorted(n for n in positions if n not in ordered)
    ordered.update({n: positions[n] for n in rest})
    return ordered


def _canonically_ordered(positions: dict) -> dict:
    """Order by the default seating when the caller has not already done it."""
    return _in_council_order(positions, DEFAULT_MODELS)


def _unverified_terms(positions: dict, question: str) -> list[str]:
    """Specifics the council floated in round 1 that the user never gave.

    Named in the round-2 prompt so a guess cannot quietly become the room's
    shared premise.
    """
    if not question:
        return []
    q_stems, q_figs = stems(question), figures(question)
    terms: list[str] = []
    # Council order, not arrival order: this list is truncated below, so who
    # gets read first decides which invented specifics the round-2 prompt names.
    for position in _canonically_ordered(positions).values():
        for field in ("reasoning", "lens_finding", "condition"):
            asserted, _ = premise_hits(str(getattr(position, field, "") or ""), q_stems, q_figs)
            for term in asserted:
                if term not in terms:
                    terms.append(term)
    return terms[:MAX_UNVERIFIED_TERMS]


def _find_echoes(
    positions: dict, order: list[str]
) -> dict[str, tuple[str, str]]:
    """Members who restated an earlier member's argument.

    Returns {echoing_member: (source_member, source_text)}. Precedence follows
    `order`, so the member who spoke first in council order keeps the point and
    later members are the ones asked to find their own.
    """
    echoes: dict[str, tuple[str, str]] = {}
    ranked = [n for n in order if n in positions]
    for i, name in enumerate(ranked):
        mine = _position_text(positions[name])
        for earlier in ranked[:i]:
            if earlier in echoes:
                continue  # compare against originals, not echoes
            theirs = _position_text(positions[earlier])
            if is_echo(mine, theirs):
                echoes[name] = (earlier, theirs)
                break
    return echoes


async def _vote_round(
    deliberation: Deliberation, models: dict[str, str]
) -> AsyncIterator[tuple[str, PersonaResponse | Exception]]:
    async with httpx.AsyncClient() as client:
        async def wrap(name: str):
            try:
                return name, await _consult(client, models[name], get_decision_prompt(name), deliberation.histories[name], name)
            except Exception as e:
                return name, e

        tasks = [asyncio.create_task(wrap(n)) for n in models.keys()]
        try:
            for coro in asyncio.as_completed(tasks):
                yield await coro
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()


async def _break_echoes(
    deliberation: Deliberation,
    models: dict[str, str],
    positions: dict,
    response_cls=PersonaResponse,
    prompt_for=get_decision_prompt,
    options: list[str] | None = None,
    question: str = "",
) -> AsyncIterator[tuple[str, object]]:
    """Send a member back when it made somebody else's argument — either by
    restating it (echo) or by reaching into territory its lens does not own.
    One pass, one retry each; a failed retry leaves the original standing."""
    echoes = _find_echoes(positions, list(models.keys()))
    off_lens = {n: t for n, t in _find_off_lens(positions).items() if n not in echoes}
    ungrounded = {
        n: span for n, span in _find_ungrounded(positions, question).items()
        if n not in echoes and n not in off_lens
    }
    if not echoes and not off_lens and not ungrounded:
        return
    async with httpx.AsyncClient() as client:
        async def redo(name: str):
            if name in echoes:
                source, source_text = echoes[name]
                nudge = None
            elif name in off_lens:
                source, source_text = "MELCHIOR", ""
                nudge = _OFF_LENS_INSTRUCTION.format(term=off_lens[name])
            else:
                source, source_text = "", ""
                nudge = _UNGROUNDED_INSTRUCTION.format(
                    span=ungrounded[name], question=question
                )
            try:
                fresh = await _reconsult_without_echo(
                    client, models[name], prompt_for(name),
                    deliberation.histories[name], name, positions[name],
                    source, source_text, response_cls, options, nudge,
                )
            except Exception:
                return name, None
            # keep the retry only if it actually fixed what it was sent back for
            fresh_text = _position_text(fresh)
            if name in echoes and is_echo(fresh_text, source_text):
                return name, None
            if name in off_lens and off_limits_term(name, fresh_text):
                return name, None
            if name in ungrounded and _find_ungrounded({name: fresh}, question):
                return name, None
            return name, fresh

        tasks = [asyncio.create_task(redo(n)) for n in (*echoes, *off_lens, *ungrounded)]
        try:
            for coro in asyncio.as_completed(tasks):
                name, fresh = await coro
                if fresh is not None:
                    yield name, fresh
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()


async def _debate_round(
    deliberation: Deliberation,
    models: dict[str, str],
    current_positions: dict[str, PersonaResponse],
    round_num: int,
    question: str = "",
    unverified: list[str] | None = None,
) -> AsyncIterator[tuple[str, Rebuttal | Exception]]:
    async with httpx.AsyncClient() as client:
        async def rebut(name: str):
            own = current_positions[name]
            others = {n: v for n, v in current_positions.items() if n != name}
            try:
                return name, await _rebut(
                    client, models[name], get_decision_prompt(name),
                    deliberation.histories[name], own, others, round_num, name,
                    question, unverified,
                )
            except Exception as e:
                return name, e

        tasks = [asyncio.create_task(rebut(n)) for n in current_positions.keys()]
        try:
            for coro in asyncio.as_completed(tasks):
                yield await coro
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()


def _is_consensus(positions: dict[str, PersonaResponse]) -> bool:
    verdicts = [p.verdict for p in positions.values()]
    return len(verdicts) >= 2 and len(set(verdicts)) == 1


# The council decides. A 2-1 vote is a decision, not a hung jury — reporting it
# as DEADLOCK was the system-level version of refusing to vote. Genuine ties go
# to total conviction, and a tie on conviction too goes to the desire lens: when
# the arguments are exactly balanced, what the person wants is the deciding fact.
TIEBREAK_MEMBER = "CASPER"


def _resolve(positions: dict) -> tuple[str, object]:
    """Return (outcome, winning_stance).

    outcome ∈ {"consensus", "majority", "conviction", "tiebreak", "incomplete"}.
    Works for any position type exposing a stance attribute and `confidence`.
    """
    stances: dict = {}
    weights: dict = {}
    for name, p in positions.items():
        stance = getattr(p, "verdict", None) or getattr(p, "chosen_option", None)
        if stance is None:
            continue
        stances[stance] = stances.get(stance, 0) + 1
        weights[stance] = weights.get(stance, 0) + int(getattr(p, "confidence", 3) or 3)

    if not stances:
        return "incomplete", None
    if len(stances) == 1:
        return "consensus", next(iter(stances))

    top = max(stances.values())
    leaders = [s for s, c in stances.items() if c == top]
    if len(leaders) == 1:
        return "majority", leaders[0]

    # tied on headcount — decide on total conviction
    best_weight = max(weights[s] for s in leaders)
    by_weight = [s for s in leaders if weights[s] == best_weight]
    if len(by_weight) == 1:
        return "conviction", by_weight[0]

    # still tied — the desire lens breaks it
    for name, p in positions.items():
        if name == TIEBREAK_MEMBER:
            stance = getattr(p, "verdict", None) or getattr(p, "chosen_option", None)
            if stance in by_weight:
                return "tiebreak", stance
    return "tiebreak", sorted(by_weight, key=str)[0]


def _stance_map(positions: dict) -> dict:
    return {
        n: (getattr(p, "verdict", None) or getattr(p, "chosen_option", None))
        for n, p in positions.items()
    }


async def iterative_deliberate(
    deliberation: Deliberation, models: dict[str, str], max_rounds: int | None = None
) -> AsyncIterator[tuple]:
    """Yields ("round_start", n), ("vote", name, result), ("rebuttal", name, result),
    ("done", outcome, positions)."""
    max_rounds = resolve_max_rounds(max_rounds)
    yield ("round_start", 1)
    initial_votes: dict[str, PersonaResponse | Exception] = {}
    async for name, result in _vote_round(deliberation, models):
        initial_votes[name] = result
        yield ("vote", name, result)

    valid: dict[str, PersonaResponse] = _in_council_order(
        {n: v for n, v in initial_votes.items() if isinstance(v, PersonaResponse)}, models)

    if len(valid) < 2:
        for name, response in valid.items():
            deliberation.commit_response(name, response)
        yield ("done", "incomplete", valid)
        return

    # Three lenses that produced one argument are not three lenses.
    async for name, fresh in _break_echoes(
        deliberation, models, valid, question=deliberation.question_text
    ):
        valid[name] = fresh
        yield ("revote", name, fresh)

    current_positions = dict(valid)  # already in council order

    def finish(outcome: str):
        for member, response in current_positions.items():
            deliberation.commit_response(member, response)
        return ("done", outcome, current_positions)

    if _is_consensus(current_positions):
        yield finish("consensus")
        return

    question_text = deliberation.question_text
    unverified = _unverified_terms(current_positions, question_text)

    for round_num in range(2, max_rounds + 1):
        yield ("round_start", round_num)
        before = _stance_map(current_positions)
        async for name, rebuttal in _debate_round(
            deliberation, models, current_positions, round_num, question_text, unverified
        ):
            yield ("rebuttal", name, rebuttal)
            if isinstance(rebuttal, Rebuttal):
                prev = current_positions[name]
                new_condition = rebuttal.condition if rebuttal.final_verdict == Verdict.CONDITIONAL else ""
                current_positions[name] = PersonaResponse(
                    verdict=rebuttal.final_verdict,
                    reasoning=prev.reasoning,
                    lens_finding=prev.lens_finding,
                    confidence=rebuttal.confidence,
                    condition=new_condition,
                )

        if _is_consensus(current_positions):
            yield finish("consensus")
            return

        # Nobody moved. Another round is three models restating themselves.
        if _stance_map(current_positions) == before:
            break

    outcome, _winner = _resolve(current_positions)
    yield finish(outcome)


OPTION_MATCH_RATIO = 0.72


def _normalize_option(value: str, options: list[str]) -> str:
    """Snap a member's pick back onto one of the named options.

    Exact, then containment, then nearest. The fuzzy step exists because a
    single typo used to mint a phantom option: a member picked "magi on p:pyi"
    and the tally reported it as a fourth candidate alongside "magi on pypi".
    """
    if not value:
        return value
    low = value.strip().lower()
    for opt in options:
        if low == opt.lower():
            return opt
    for opt in options:
        if low in opt.lower() or opt.lower() in low:
            return opt

    from difflib import SequenceMatcher

    scored = [(SequenceMatcher(None, low, opt.lower()).ratio(), opt) for opt in options]
    if scored:
        best_ratio, best = max(scored, key=lambda pair: pair[0])
        if best_ratio >= OPTION_MATCH_RATIO:
            return best
    return value.strip()


async def _consult_choice(
    client: httpx.AsyncClient,
    model: str,
    system: str,
    messages: list[dict],
    options: list[str],
    member: str = "",
) -> ChoiceResponse:
    options_block = f"\n\n== OPTIONS FOR THIS QUESTION ==\nPick ONE of: {', '.join(options)}.\nchosen_option must EXACTLY match one of those names."
    schema = _member_schema(ChoiceResponse, member)
    raw = await providers.chat(client, model, system + options_block, messages, schema,
                               temperature=0.7, keep_alive=KEEP_ALIVE)
    content = _sanitize_llm_output(raw)
    parsed = ChoiceResponse.model_validate_json(_strip_thinking(content))
    parsed.chosen_option = _normalize_option(parsed.chosen_option, options)
    return parsed


async def _rebut_choice(
    client: httpx.AsyncClient,
    model: str,
    system: str,
    messages: list[dict],
    own_position: ChoiceResponse,
    others: dict[str, ChoiceResponse],
    options: list[str],
    round_num: int,
    member: str = "",
) -> ChoiceRebuttal:
    others_text = "\n\n".join(
        f"{name} picked {r.chosen_option} (confidence {r.confidence}/5) — {r.reasoning}"
        + (f"\n  their finding: {r.lens_finding}" if r.lens_finding else "")
        for name, r in others.items()
    )

    identity_anchor = (
        "REMEMBER: you are speaking ABOUT the user's situation. "
        "Use 'they' / 'the user' / 'their'. Never 'I' / 'my' / 'we'. "
        "The choice belongs to the user, not you."
    )

    options_reminder = (
        f"You must pick from these options: {', '.join(options)}. "
        "final_choice must EXACTLY match one of them."
    )

    if round_num == 2:
        opener = "The other council members have just picked. Here is what they said:"
        closer = (
            "Address them by name. Push back if their pick is wrong from your lens. "
            "1-3 sentences. Then give your final_choice for this round. HOLD YOUR LINE "
            "unless a real argument exposed new information or a flaw. Convergence for its "
            "own sake is failure."
        )
    else:
        opener = (
            f"This is round {round_num} of the deliberation. The other members' "
            "latest picks:"
        )
        closer = (
            "Respond to the latest points. HOLD YOUR LINE unless a real argument "
            "exposed new information or a flaw. 1-3 sentences. Final pick: same as "
            "last round OR updated only if you were genuinely persuaded."
        )

    debate_prompt = f"{identity_anchor}\n\n{options_reminder}\n\n{opener}\n\n{others_text}\n\n{closer}"

    schema = _member_schema(ChoiceRebuttal, member)
    debate_messages = (
        messages
        + [{"role": "assistant", "content": own_position.model_dump_json()}]
        + [{"role": "user", "content": debate_prompt}]
    )
    raw = await providers.chat(client, model, system, debate_messages, schema,
                               temperature=0.7, keep_alive=KEEP_ALIVE)
    content = _sanitize_llm_output(raw)
    parsed = ChoiceRebuttal.model_validate_json(_strip_thinking(content))
    parsed.final_choice = _normalize_option(parsed.final_choice, options)
    return parsed


async def _vote_choice_round(
    deliberation: Deliberation, models: dict[str, str], options: list[str]
) -> AsyncIterator[tuple[str, ChoiceResponse | Exception]]:
    async with httpx.AsyncClient() as client:
        async def wrap(name: str):
            try:
                return name, await _consult_choice(client, models[name], get_choice_prompt(name), deliberation.histories[name], options, name)
            except Exception as e:
                return name, e
        tasks = [asyncio.create_task(wrap(n)) for n in models.keys()]
        try:
            for coro in asyncio.as_completed(tasks):
                yield await coro
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()


async def _debate_choice_round(
    deliberation: Deliberation,
    models: dict[str, str],
    current_positions: dict[str, ChoiceResponse],
    options: list[str],
    round_num: int,
) -> AsyncIterator[tuple[str, ChoiceRebuttal | Exception]]:
    async with httpx.AsyncClient() as client:
        async def rebut(name: str):
            own = current_positions[name]
            others = {n: v for n, v in current_positions.items() if n != name}
            try:
                return name, await _rebut_choice(client, models[name], get_choice_prompt(name), deliberation.histories[name], own, others, options, round_num, name)
            except Exception as e:
                return name, e
        tasks = [asyncio.create_task(rebut(n)) for n in current_positions.keys()]
        try:
            for coro in asyncio.as_completed(tasks):
                yield await coro
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()


def _is_choice_consensus(positions: dict[str, ChoiceResponse]) -> bool:
    choices = [p.chosen_option for p in positions.values()]
    return len(choices) >= 2 and len(set(choices)) == 1


async def iterative_choose(
    deliberation: Deliberation,
    models: dict[str, str],
    options: list[str],
    max_rounds: int | None = None,
) -> AsyncIterator[tuple]:
    """Same event shape as iterative_deliberate but with ChoiceResponse/ChoiceRebuttal."""
    max_rounds = resolve_max_rounds(max_rounds)
    yield ("round_start", 1)
    initial: dict[str, ChoiceResponse | Exception] = {}
    async for name, result in _vote_choice_round(deliberation, models, options):
        initial[name] = result
        yield ("vote", name, result)

    valid: dict[str, ChoiceResponse] = _in_council_order(
        {n: v for n, v in initial.items() if isinstance(v, ChoiceResponse)}, models)
    if len(valid) < 2:
        yield ("done", "incomplete", valid)
        return

    async for name, fresh in _break_echoes(
        deliberation, models, valid,
        response_cls=ChoiceResponse, prompt_for=get_choice_prompt, options=options,
    ):
        valid[name] = fresh
        yield ("revote", name, fresh)

    current = dict(valid)  # already in council order
    if _is_choice_consensus(current):
        yield ("done", "consensus", current)
        return

    for round_num in range(2, max_rounds + 1):
        yield ("round_start", round_num)
        before = _stance_map(current)
        async for name, rebuttal in _debate_choice_round(deliberation, models, current, options, round_num):
            yield ("rebuttal", name, rebuttal)
            if isinstance(rebuttal, ChoiceRebuttal):
                prev = current[name]
                current[name] = ChoiceResponse(
                    chosen_option=rebuttal.final_choice,
                    reasoning=prev.reasoning,
                    lens_finding=prev.lens_finding,
                    confidence=rebuttal.confidence,
                )
        if _is_choice_consensus(current):
            yield ("done", "consensus", current)
            return
        if _stance_map(current) == before:
            break

    outcome, _winner = _resolve(current)
    yield ("done", outcome, current)


_VAGUE_RECOMMENDATION_NUDGE = (
    'That is not a recommendation, it is a category: "{attempt}"\n\n'
    "Name ONE real thing that exists and has a name. A specific game, a specific book, "
    "a specific project with a title, a specific place. If you recommended a kind of thing, "
    "pick the single best example of that kind and name it instead.\n\n"
    'Do not begin with "Consider", "Explore", "Try", "Look into", or "Something that".'
)


async def _consult_recommend(
    client: httpx.AsyncClient,
    model: str,
    system: str,
    messages: list[dict],
) -> RecommendResponse:
    """The vagueness validator rejects category-shaped answers like "a project
    that solves a real problem". Without a retry the member simply drops out of
    the council, which is how the data lens went missing from every open
    question. One corrective pass, then give up."""
    schema = RecommendResponse.model_json_schema()
    convo = messages
    last_error: Exception | None = None

    for attempt in range(2):
        raw = await providers.chat(client, model, system, convo, schema,
                                   temperature=0.8 + 0.1 * attempt, num_predict=800,
                                   keep_alive=KEEP_ALIVE)
        content = _strip_thinking(_sanitize_llm_output(raw))
        try:
            parsed = RecommendResponse.model_validate_json(content)
        except Exception as e:
            last_error = e
            if attempt == 0:
                convo = messages + [
                    {"role": "assistant", "content": content[:600]},
                    {"role": "user", "content": _VAGUE_RECOMMENDATION_NUDGE.format(
                        attempt=_first_recommendation(content)
                    )},
                ]
                continue
            raise
        parsed.recommendation = _clean_recommendation(parsed.recommendation)
        return parsed

    raise last_error  # unreachable, kept for type clarity


def _first_recommendation(content: str) -> str:
    """Pull the rejected recommendation back out of the raw JSON so the retry
    can quote it. Best effort — the nudge still works without it."""
    import json as _json

    try:
        value = _json.loads(content).get("recommendation", "")
        return str(value)[:120] if value else "(nothing concrete)"
    except Exception:
        return "(nothing concrete)"


async def _rebut_recommend(
    client: httpx.AsyncClient,
    model: str,
    system: str,
    messages: list[dict],
    own_position: RecommendResponse,
    others: dict[str, RecommendResponse],
    round_num: int,
) -> RecommendRebuttal:
    others_text = "\n\n".join(
        f"{name} recommends: {r.recommendation} — {r.reasoning}"
        for name, r in others.items()
    )

    identity_anchor = (
        "REMEMBER: you are speaking ABOUT the user's situation. "
        "Use 'they' / 'the user' / 'their'. Never 'I' / 'my' / 'we'."
    )

    closer = (
        "Address the others by name if you push back. Stay in your lens — your job is NOT to converge "
        "on a single answer; three different concrete recommendations is a valid result. Hold your "
        "recommendation unless a real argument exposed a flaw OR sparked a sharper version. 1-3 sentences. "
        "Then give your final_recommendation: same as before, refined, or replaced. Must remain concrete — "
        "no platitudes."
    )

    if round_num == 2:
        opener = "The other council members have just given their recommendations:"
    else:
        opener = f"This is round {round_num} of the deliberation. Latest recommendations:"

    debate_prompt = f"{identity_anchor}\n\n{opener}\n\n{others_text}\n\n{closer}"

    schema = RecommendRebuttal.model_json_schema()
    debate_messages = (
        messages
        + [{"role": "assistant", "content": own_position.model_dump_json()}]
        + [{"role": "user", "content": debate_prompt}]
    )
    raw = await providers.chat(client, model, system, debate_messages, schema,
                               temperature=0.8, num_predict=800, keep_alive=KEEP_ALIVE)
    content = _sanitize_llm_output(raw)
    parsed = RecommendRebuttal.model_validate_json(_strip_thinking(content))
    parsed.final_recommendation = _clean_recommendation(parsed.final_recommendation)
    parsed.response = _strip_persona_prefixes(parsed.response)
    return parsed


async def _vote_recommend_round(
    deliberation: Deliberation, models: dict[str, str]
) -> AsyncIterator[tuple[str, RecommendResponse | Exception]]:
    async with httpx.AsyncClient() as client:
        async def wrap(name: str):
            try:
                return name, await _consult_recommend(client, models[name], get_recommend_prompt(name), deliberation.histories[name])
            except Exception as e:
                return name, e
        tasks = [asyncio.create_task(wrap(n)) for n in models.keys()]
        try:
            for coro in asyncio.as_completed(tasks):
                yield await coro
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()


async def _debate_recommend_round(
    deliberation: Deliberation,
    models: dict[str, str],
    current_positions: dict[str, RecommendResponse],
    round_num: int,
) -> AsyncIterator[tuple[str, RecommendRebuttal | Exception]]:
    async with httpx.AsyncClient() as client:
        async def rebut(name: str):
            own = current_positions[name]
            others = {n: v for n, v in current_positions.items() if n != name}
            try:
                return name, await _rebut_recommend(client, models[name], get_recommend_prompt(name), deliberation.histories[name], own, others, round_num)
            except Exception as e:
                return name, e
        tasks = [asyncio.create_task(rebut(n)) for n in current_positions.keys()]
        try:
            for coro in asyncio.as_completed(tasks):
                yield await coro
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()


async def iterative_recommend(
    deliberation: Deliberation,
    models: dict[str, str],
) -> AsyncIterator[tuple]:
    """Single round, no rebuttal. Three independent picks from three lenses."""
    yield ("round_start", 1)
    initial: dict[str, RecommendResponse | Exception] = {}
    async for name, result in _vote_recommend_round(deliberation, models):
        initial[name] = result
        yield ("vote", name, result)

    valid: dict[str, RecommendResponse] = _in_council_order(
        {n: v for n, v in initial.items() if isinstance(v, RecommendResponse)}, models)
    outcome = "picks" if len(valid) >= 2 else "incomplete"
    yield ("done", outcome, valid)


def synthesize_recommend(responses: dict[str, RecommendResponse | Exception]) -> str:
    valid = [(n, r) for n, r in responses.items() if isinstance(r, RecommendResponse)]
    n = len(valid)
    if n < 2:
        return f"INCOMPLETE — only {n} council member(s) responded"

    rec_to_names: dict[str, list[str]] = {}
    for name, r in valid:
        rec_to_names.setdefault(r.recommendation.lower().strip(), []).append(name)

    if len(rec_to_names) == 1:
        return f"CONSENSUS — all {n} picked the same direction  →  your call to commit"
    if len(rec_to_names) < n:
        overlaps = [(rec, names) for rec, names in rec_to_names.items() if len(names) > 1]
        if overlaps:
            rec, names = overlaps[0]
            return f"PARTIAL OVERLAP — {len(names)}/{n} agree on one pick  →  your call between {n - len(names) + 1} options"
    return f"{n} DISTINCT PICKS — your call: pick the lens that speaks to you"


def synthesize_choice(
    responses: dict[str, ChoiceResponse | Exception],
    outcome: str,
    options: list[str],
) -> str:
    """Tally choice votes. A tie on headcount is decided on conviction, then by
    the desire lens — the council never hands the pick back."""
    valid = {n: r for n, r in responses.items() if isinstance(r, ChoiceResponse)}
    n = len(valid)
    if n < 2:
        return f"INCOMPLETE — only {n} council member(s) responded"

    tally: dict[str, int] = {opt: 0 for opt in options}
    for r in valid.values():
        tally[r.chosen_option] = tally.get(r.chosen_option, 0) + 1

    sorted_tally = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
    breakdown = "  ".join(f"{opt}:{c}" for opt, c in sorted_tally if c > 0)

    resolved, winner = _resolve(valid)
    if outcome in ("auto", "split", "deadlock", None):
        outcome = resolved
    if winner is None:
        winner = sorted_tally[0][0]

    if outcome == "consensus":
        return f"CONSENSUS — {winner}  ({breakdown})"
    if outcome == "conviction":
        return f"CALL — {winner}  ({breakdown})  ·  tied, decided on conviction"
    if outcome == "tiebreak":
        return f"CALL — {winner}  ({breakdown})  ·  dead even, {TIEBREAK_MEMBER} breaks the tie"
    return f"WINNER — {winner}  ({breakdown})"




_VERDICT_WORD = {
    Verdict.ACCEPT: "YES",
    Verdict.REJECT: "NO",
    Verdict.CONDITIONAL: "ONLY IF",
}


def synthesize(
    responses: dict[str, PersonaResponse | Exception],
    outcome: str = "auto",
) -> str:
    """outcome ∈ {"consensus", "majority", "conviction", "tiebreak",
    "incomplete", "auto"}. 'auto' resolves from the verdicts themselves.

    There is no outcome that hands the question back. A 2-1 vote is a decision;
    a dead tie is decided on conviction, then by the desire lens.
    """
    valid = {n: r for n, r in responses.items() if isinstance(r, PersonaResponse)}
    n = len(valid)

    if n < 2:
        return f"INCOMPLETE — only {n} council member(s) responded"

    verdicts = [r.verdict for r in valid.values()]
    accept = verdicts.count(Verdict.ACCEPT)
    reject = verdicts.count(Verdict.REJECT)
    conditional = verdicts.count(Verdict.CONDITIONAL)
    tally = f"{accept}A · {conditional}C · {reject}R"

    resolved, winner = _resolve(valid)
    if outcome in ("auto", "deadlock", "split", None):
        outcome = resolved
    if winner is None:
        winner = verdicts[0]

    word = _VERDICT_WORD.get(winner, str(winner))

    if outcome == "consensus":
        return f"CONSENSUS — {word}  ({tally})"
    if outcome == "majority":
        return f"MAJORITY — {word}  ({tally})"
    if outcome == "conviction":
        return f"CALL — {word}  ({tally})  ·  split evenly, decided on conviction"
    if outcome == "tiebreak":
        return f"CALL — {word}  ({tally})  ·  dead even, {TIEBREAK_MEMBER} breaks the tie"
    return f"MAJORITY — {word}  ({tally})"
