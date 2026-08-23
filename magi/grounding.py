"""Detecting facts the council invented and then voted on.

The failure this exists for, from a live v0.13 session. The user asked, with no
other detail, "should i push a database migration to prod at 5pm on friday".
MELCHIOR voted ACCEPT because "the mechanism for success is a 24-hour rollback
window with pre-migration testing in staging", and in the next round cited its
own invention as something BALTHASAR had missed. Nothing in the question
mentions staging, rollback windows, or testing. Two members voted yes on a
Friday production migration by making up the conditions under which that would
be fine.

That transcript scored clean on every other measure the project had: distinct
lenses, decisive, fast, no vague phrases. A confident answer built on invented
premises is worse than a hedge, and nothing could see it.

The discriminator is NOT novel vocabulary. A lens is supposed to bring words the
question does not contain. It is whether a novel SPECIFIC is ASSERTED as an
existing fact about the user. The run that got this same question right used the
very same nouns under negation: "There's no mention of rollback plans, testing,
or timing details." Naming a missing fact is the job. Assuming it is the failure.
So every novel specific sorts into asserted or demanded, and only asserted counts.

Lives in magi/ rather than evals/ because the runtime uses it to catch members
mid-deliberation and the eval harness imports it to score runs. magi never
imports evals.
"""

import re

from magi.textsim import content_words


def _stem(word: str) -> str:
    """Crude, deterministic, and enough: testing/tested/tests -> test."""
    for suffix in ("ings", "ing", "ies", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def stems(text: str) -> set[str]:
    return {_stem(w) for w in content_words(text)}


# Situational artifacts a decision can hinge on. Curated like OFF_LIMITS and
# _BANNED_CONDITION_PHRASES: the list IS the specificity filter, so "their
# situation" is ignored and "their rollback plan" is not.
PREMISE_LEXICON = frozenset("""
staging rollback backup snapshot restore testing tests test suite coverage
pipeline runbook monitoring alerting oncall pager replica failover
maintenance checklist approval signoff reviewer deploy deployment
release freeze sla team teammate colleague manager support
savings runway salary raise offer contract lease mortgage visa insurance
mentor therapist partner spouse kids children family degree portfolio
clients customers investor cofounder employer references funding
break vacation pto leave sabbatical holiday deadline notice severance
""".split())
_LEXICON_STEMS = frozenset(_stem(w) for w in PREMISE_LEXICON)

_NUM_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "twelve": "12",
    "fifteen": "15", "twenty": "20", "thirty": "30", "twentyfour": "24",
}
_UNIT = r"(?:second|minute|hour|day|week|weekend|month|quarter|year|sprint)"
_NUMWORD = "|".join(_NUM_WORDS)
_JOIN = r"(?:\s*-\s*|\s+(?:a|an|per|each)\s+|\s*/\s*|\s+|)"

# Clock times, money, percentages, durations. Needs no lexicon, so this channel
# works in domains the lexicon has never seen.
_FIGURE = re.compile(
    r"\b\d{1,2}:\d{2}\s*(?:am|pm)?"
    r"|\b\d{1,2}\s*(?:am|pm)\b"
    rf"|\$\s?\d[\d,]*(?:\.\d+)?(?:\s*k)?(?:{_JOIN}{_UNIT}s?)?"
    r"|\b\d[\d,]*(?:\.\d+)?\s*k\b"
    r"|\b\d[\d,]*(?:\.\d+)?\s*(?:%|percent)"
    rf"|\b\d[\d,]*(?:\.\d+)?{_JOIN}{_UNIT}s?\b"
    rf"|\b(?:{_NUMWORD}|twenty-four){_JOIN}{_UNIT}s?\b",
    re.IGNORECASE,
)
_FIGURE_PARTS = re.compile(
    rf"(\d[\d,]*(?:\.\d+)?|{_NUMWORD}|twentyfour)\s*(:\d{{2}})?\s*"
    rf"(am|pm|%|percent|k|{_UNIT})?",
    re.IGNORECASE,
)

# "in five years" is BALTHASAR's lens, not a claim about today. A figure inside
# a forward-looking horizon is a projection; only present figures are premises.
_HORIZON = re.compile(
    rf"\b(?:in|within|over\s+the\s+next|for\s+the\s+next|after|by)\s+(?:the\s+)?(?:next\s+)?"
    rf"(?:\d[\d,]*|{_NUMWORD})\s*-?\s*{_UNIT}s?\b",
    re.IGNORECASE,
)


# Word boundaries matter: without them "per" matches inside "percent".
_FILLER = re.compile(r"\s*(?:/|\b(?:per|each|a|an)\b)\s*", re.IGNORECASE)


def _normalize_figure(raw: str) -> str:
    """'99 a month', '$99/month' and '99 months' all compare equal.

    They have to. The user writes "price my saas at 29 a month or 99 a month"
    and a member answers "$99/month"; if those normalise differently the
    member gets flagged for inventing a number it was handed.
    """
    s = raw.lower().replace(",", "").replace("$", "").replace("-", "").strip()
    s = _FILLER.sub(" ", s).strip()
    m = _FIGURE_PARTS.match(s)
    if not m:
        return re.sub(r"[^a-z0-9:.%]", "", s)
    number = _NUM_WORDS.get(m.group(1), m.group(1))
    unit = m.group(3) or ""
    return f"{number}{m.group(2) or ''}{'%' if unit == 'percent' else unit}"


def figures(text: str) -> set[str]:
    """Every figure in the text. The question is inventoried this way, so
    "after 8 months of dating" is a fact the user gave us."""
    return {_normalize_figure(m.group(0)) for m in _FIGURE.finditer(text or "")}


def asserted_figures(text: str) -> set[str]:
    """Figures claimed as present fact. Projections are dropped."""
    return figures(_HORIZON.sub(" ", text or ""))


# Frames that attribute a state or possession to the user. Desire verbs are
# deliberately absent: "you want this done" is CASPER doing its job, while
# "when you're back from a planned break" invents a circumstance.
_FACTIVE = re.compile(
    r"\b(?:"
    r"(?:the\s+user|they|you|user)\s*(?:'ve|'re|\s+(?:have|has|had|already))"
    r"|(?:the\s+user's|their|your)"
    r"|(?:with|given|since|assuming|thanks\s+to|now\s+that|back\s+from|during)\s+"
    r"(?:a|an|the|their|your)"
    r")\b",
    re.IGNORECASE,
)

# Anywhere in the sentence, these turn an assertion into a demand, a hypothesis
# or a proposal, which is exactly what a member SHOULD do with a fact it lacks.
# "when" is absent on purpose: "next week when you're back from a planned break"
# is a fabrication, not a hedge.
_NOT_ASSERTED = re.compile(
    r"\b(?:no|not|never|none|nothing|neither|nor|without|lack|lacks|lacking|"
    r"missing|absent|unspecified|unstated|unclear|unknown|"
    r"if|whether|unless|until|would|could|should|shall|may|might|must|can|"
    r"need|needs|needed|require|requires|required|assuming|suppose|"
    r"instead|rather|hasn't|haven't|hadn't|isn't|aren't|didn't|doesn't|don't|won't)\b",
    re.IGNORECASE,
)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_SPAN_END = re.compile(r"[.,;:!?]")
_SPAN_CHARS = 90


def _framed_spans(sentence: str) -> list[str]:
    spans = []
    for m in _FACTIVE.finditer(sentence):
        tail = sentence[m.end(): m.end() + _SPAN_CHARS]
        cut = _SPAN_END.search(tail)
        spans.append(tail[: cut.start()] if cut else tail)
    return spans


def _negated_before(text: str, position: int) -> bool:
    """Is this specific inside the scope of a negation?

    Scoped per term rather than per sentence. Sentence-wide scope let the
    live failure through: "The user has already confirmed the migration is
    ready for deployment with no pending rollbacks" is an assertion with a
    negation hanging off the end, and one "no" anywhere used to suppress the
    whole thing. A negation only neutralises what comes after it, so only
    text before the term counts.
    """
    for m in _NOT_ASSERTED.finditer(text):
        if m.start() < position:
            return True
    return False


def premise_hits(text: str, question_stems: set[str],
                 question_figures: set[str]) -> tuple[list[str], list[str]]:
    """(asserted, demanded) novel specifics. Asserted ones are fabrications."""
    asserted: set[str] = set()
    demanded: set[str] = set()

    for sentence in _SENTENCE.split((text or "").strip()):
        if not sentence:
            continue

        # figures, positioned within the sentence
        stripped = _HORIZON.sub(lambda m: " " * len(m.group(0)), sentence)
        for m in _FIGURE.finditer(stripped):
            figure = _normalize_figure(m.group(0))
            if figure in question_figures:
                continue
            (demanded if _negated_before(sentence, m.start()) else asserted).add(figure)

        # situational nouns, but only inside a frame that attributes them to
        # the user, and only when the question never supplied them
        for frame in _FACTIVE.finditer(sentence):
            tail = sentence[frame.end(): frame.end() + _SPAN_CHARS]
            cut = _SPAN_END.search(tail)
            span = tail[: cut.start()] if cut else tail
            for word_match in re.finditer(r"[A-Za-z0-9']+", span):
                s = _stem(word_match.group(0).lower())
                if s not in _LEXICON_STEMS or s in question_stems:
                    continue
                at = frame.end() + word_match.start()
                (demanded if _negated_before(sentence, at) else asserted).add(s)

    return sorted(asserted), sorted(demanded - asserted)


def novel_terms(text: str, question_stems: set[str],
                question_figures: set[str]) -> set[str]:
    """Every novel specific the text touches, framed or not. Seeds the
    laundering check: a term floated in round 1 and then stated as established
    fact in round 2 is how one member's guess becomes the council's premise."""
    novel = {f for f in asserted_figures(text) if f not in question_figures}
    for word in content_words(text or ""):
        s = _stem(word)
        if s in _LEXICON_STEMS and s not in question_stems:
            novel.add(s)
    return novel
