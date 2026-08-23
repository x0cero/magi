"""Deterministic scoring. No LLM judge — every metric here is mechanical so
two runs are comparable and nothing drifts between evaluations."""

import re
from itertools import combinations

from magi.core import _BANNED_CONDITION_PHRASES, _BANNED_RECOMMENDATION_PHRASES
from magi.grounding import figures, novel_terms, premise_hits, stems
from magi.textsim import ECHO_OVERLAP
from magi.textsim import content_words as _content_words
from magi.textsim import longest_shared_phrase as _longest_shared_phrase
from magi.textsim import overlap as _overlap

# The runtime uses these same measures to catch echoing mid-deliberation, so
# the eval scores exactly what the product enforces.
content_words = _content_words
jaccard = _overlap
longest_shared_phrase = _longest_shared_phrase


def echo(texts: list[str]) -> dict:
    """How much the council repeated itself. Lower is better on every field."""
    pairs = list(combinations([t for t in texts if t], 2))
    if not pairs:
        return {"mean_overlap": 0.0, "max_overlap": 0.0, "longest_shared_phrase": 0}
    overlaps = [jaccard(a, b) for a, b in pairs]
    phrases = [longest_shared_phrase(a, b) for a, b in pairs]
    return {
        "mean_overlap": sum(overlaps) / len(overlaps),
        "max_overlap": max(overlaps),
        "longest_shared_phrase": max(phrases),
    }


_EXTRA_VAGUE = (
    "it depends", "depends on", "weigh the pros", "pros and cons",
    "do your research", "make sure you", "important to consider",
    "carefully evaluate", "take the time to", "at the end of the day",
    "ultimately, the decision", "only you can decide", "there is no right answer",
)

_VAGUE_PHRASES = tuple(
    set(_BANNED_CONDITION_PHRASES) | set(_BANNED_RECOMMENDATION_PHRASES) | set(_EXTRA_VAGUE)
)

# First person referring to the user's own situation: the identity leak the
# persona prompts exist to prevent.
_FIRST_PERSON = re.compile(r"\b(i|i'm|i've|i'd|i'll|my|mine|we|we're|our|ours|us)\b", re.IGNORECASE)

_INTERROGATIVE = re.compile(r"\?")

_HEDGE_OPENERS = re.compile(
    r"\b(have you considered|are you prepared|what if you|how will you|"
    r"what's holding you|it might be worth|you may want to|perhaps you should)\b",
    re.IGNORECASE,
)


def count_vague(text: str) -> int:
    low = text.lower()
    return sum(1 for p in _VAGUE_PHRASES if p in low)


# A member quoting the user's own inner voice — "just to 'improve my resume'" —
# is doing its job, not leaking. Only unquoted first person counts.
_QUOTED = re.compile(r"[\"'“”‘’]([^\"'“”‘’]{3,120})[\"'“”‘’]")


def count_identity_leak(text: str) -> int:
    return len(_FIRST_PERSON.findall(_QUOTED.sub(" ", text)))


def count_interrogation(text: str) -> int:
    return len(_INTERROGATIVE.findall(text)) + len(_HEDGE_OPENERS.findall(text))


def _positions_text(positions: dict) -> list[str]:
    """The substance of each member's position — the same text the runtime
    compares when it checks for one member making another's argument."""
    out = []
    for p in positions.values():
        if not isinstance(p, dict):
            continue
        for key in ("reasoning", "response", "recommendation"):
            if p.get(key):
                out.append(f"{p[key]} {p.get('lens_finding', '')}".strip())
                break
    return out


def _stances(positions: dict) -> list[str]:
    out = []
    for p in positions.values():
        if not isinstance(p, dict):
            continue
        for key in ("verdict", "chosen_option", "recommendation"):
            if p.get(key):
                out.append(str(p[key]).lower().strip())
                break
    return out


# Outcomes where the council named an answer. "deadlock" and "split" are the
# pre-0.13 outcomes that handed the question back to the user.
DECISIVE_OUTCOMES = frozenset({"consensus", "majority", "conviction", "tiebreak"})
CLEAN_OUTCOMES = frozenset({"consensus", "majority"})


def is_decisive(result: dict) -> bool | None:
    """True when the council landed somewhere the user can act on.
    None for modes where decisiveness isn't the point (open, noise)."""
    mode = result.get("mode")
    if mode in ("open", "noise") or result.get("error"):
        return None
    outcome = result.get("outcome")
    if outcome in DECISIVE_OUTCOMES:
        return True
    if outcome in ("deadlock", "split"):
        return False
    stances = _stances(result.get("final_positions", {}))
    if len(stances) < 2:
        return False
    counts: dict[str, int] = {}
    for s in stances:
        counts[s] = counts.get(s, 0) + 1
    top = max(counts.values())
    return len([s for s, c in counts.items() if c == top]) == 1


def is_clean(result: dict) -> bool | None:
    """Decisive without needing a tiebreak: unanimous or a clear majority."""
    if is_decisive(result) is None:
        return None
    return result.get("outcome") in CLEAN_OUTCOMES


# --- fabricated premises -----------------------------------------------------
# The Friday-migration failure scored clean on every metric above: distinct
# lenses, decisive, fast, no vague phrases. Nothing measured whether the
# argument was about the question the user actually asked. See magi/grounding.py.


def _authored_units(result: dict) -> list[tuple[str, int, str]]:
    """(member, round, text) for text a member actually wrote. final_positions
    is skipped: core.py copies round-1 reasoning into it verbatim."""
    units: list[tuple[str, int, str]] = []
    for name, p in (result.get("round1_positions") or {}).items():
        if not isinstance(p, dict):
            continue
        for key in ("reasoning", "response", "recommendation", "lens_finding", "condition"):
            if p.get(key):
                units.append((name, 1, str(p[key])))
    for rnd, members in (result.get("rebuttals") or {}).items():
        for name, p in (members or {}).items():
            if not isinstance(p, dict):
                continue
            for key in ("response", "final_recommendation", "condition"):
                if p.get(key):
                    units.append((name, int(rnd), str(p[key])))
    return sorted(units, key=lambda u: u[1])


def _stance_by_member(positions: dict) -> dict[str, str]:
    out = {}
    for name, p in (positions or {}).items():
        if not isinstance(p, dict):
            continue
        for key in ("verdict", "chosen_option", "recommendation"):
            if p.get(key):
                out[name] = str(p[key]).lower().strip()
                break
    return out


TIEBREAK_MEMBER = "CASPER"


def winning_stance(positions: dict) -> str | None:
    """Mirrors core._resolve: headcount, then total conviction, then the desire
    lens. Whoever holds this stance is what the user was actually told."""
    stances = _stance_by_member(positions)
    if not stances:
        return None
    counts: dict[str, int] = {}
    weights: dict[str, int] = {}
    for name, s in stances.items():
        counts[s] = counts.get(s, 0) + 1
        p = positions.get(name) or {}
        weights[s] = weights.get(s, 0) + int(p.get("confidence") or 3)
    top = max(counts.values())
    leaders = [s for s, c in counts.items() if c == top]
    if len(leaders) == 1:
        return leaders[0]
    best = max(weights[s] for s in leaders)
    leaders = [s for s in leaders if weights[s] == best]
    if len(leaders) == 1:
        return leaders[0]
    if stances.get(TIEBREAK_MEMBER) in leaders:
        return stances[TIEBREAK_MEMBER]
    return sorted(leaders)[0]


def grounding(result: dict) -> dict:
    """Per-question fabrication report.

    fabricated  - novel specifics asserted as facts about the user
    demanded    - novel specifics named as missing or required (healthy)
    laundered   - something introduced in round 1 restated as established fact
                  later, which is how one guess becomes the council's premise
    decided_on  - the winning stance was held by a member who fabricated
    """
    question = result.get("text", "")
    q_stems, q_figures = stems(question), figures(question)

    by_member: dict[str, list[str]] = {}
    seen_round1: dict[str, str] = {}
    fabricated = demanded = laundered = 0

    for name, rnd, text in _authored_units(result):
        asserted, missing = premise_hits(text, q_stems, q_figures)
        fabricated += len(asserted)
        demanded += len(missing)
        if asserted:
            by_member.setdefault(name, []).extend(asserted)
        if rnd == 1:
            for item in novel_terms(text, q_stems, q_figures):
                seen_round1.setdefault(item, name)
        else:
            laundered += sum(1 for item in set(asserted) if item in seen_round1)

    winner = winning_stance(result.get("final_positions", {}))
    stances = _stance_by_member(result.get("final_positions", {}))
    decided_on = bool(winner and any(stances.get(n) == winner for n in by_member))

    return {
        "fabricated": fabricated,
        "demanded": demanded,
        "laundered": laundered,
        "fabricated_by": {n: sorted(set(v)) for n, v in by_member.items()},
        "decided_on_fabrication": decided_on,
    }


def score_result(result: dict) -> dict:
    """Per-question metrics."""
    r1_texts = _positions_text(result.get("round1_positions", {}))
    final_texts = _positions_text(result.get("final_positions", {}))
    texts = final_texts or r1_texts
    blob = " ".join(texts)

    r1_stances = _stances(result.get("round1_positions", {}))
    final_stances = _stances(result.get("final_positions", {}))
    changed = sum(1 for a, b in zip(r1_stances, final_stances) if a != b)
    ground = grounding(result)

    return {
        "id": result.get("id"),
        "mode": result.get("mode"),
        "expect_mode": result.get("expect_mode"),
        "mode_ok": result.get("mode") == result.get("expect_mode"),
        "divergent": result.get("divergent"),
        "echo": echo(texts),
        "unique_stances": len(set(final_stances)),
        "members": len(final_stances),
        "decisive": is_decisive(result),
        "clean": is_clean(result),
        "vague_hits": count_vague(blob),
        "identity_leaks": count_identity_leak(blob),
        "interrogations": count_interrogation(blob),
        "rounds": result.get("rounds"),
        "stance_changes": changed,
        "fabricated": ground["fabricated"],
        "laundered": ground["laundered"],
        "demanded": ground["demanded"],
        "fabricated_by": ground["fabricated_by"],
        "decided_on_fabrication": ground["decided_on_fabrication"],
        "retries": len(result.get("pre_retry_positions") or {}),
        "elapsed": result.get("elapsed"),
        "error": result.get("error"),
        "outcome": result.get("outcome"),
    }


def _mean(values: list[float]) -> float:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


def score_run(results: list[dict]) -> dict:
    """Aggregate scorecard for a whole run."""
    per = [score_result(r) for r in results]
    ok = [p for p in per if not p["error"]]
    graded = [p for p in ok if p["mode"] != "noise"]
    divergent = [p for p in graded if p["divergent"]]
    decisive_applicable = [p for p in graded if p["decisive"] is not None]

    return {
        "n": len(per),
        "errors": sum(1 for p in per if p["error"]),
        "mode_accuracy": _mean([1.0 if p["mode_ok"] else 0.0 for p in ok]),
        "mean_overlap": _mean([p["echo"]["mean_overlap"] for p in graded]),
        "worst_overlap": max([p["echo"]["max_overlap"] for p in graded], default=0.0),
        "shared_phrase_max": max([p["echo"]["longest_shared_phrase"] for p in graded], default=0),
        "echo_questions": sum(1 for p in graded if p["echo"]["max_overlap"] >= ECHO_OVERLAP),
        "decisive_rate": _mean([1.0 if p["decisive"] else 0.0 for p in decisive_applicable]),
        "clean_rate": _mean([1.0 if p["clean"] else 0.0 for p in decisive_applicable]),
        "divergent_unanimous": sum(1 for p in divergent if p["unique_stances"] <= 1),
        "divergent_n": len(divergent),
        "vague_total": sum(p["vague_hits"] for p in graded),
        "identity_leaks": sum(p["identity_leaks"] for p in graded),
        "interrogations": sum(p["interrogations"] for p in graded),
        "stance_changes": sum(p["stance_changes"] for p in graded),
        "fabrication_rate": _mean([1.0 if p["fabricated"] else 0.0 for p in graded]),
        "fabricated_total": sum(p["fabricated"] for p in graded),
        "laundered_total": sum(p["laundered"] for p in graded),
        "decided_on_fabrication": sum(1 for p in graded if p["decided_on_fabrication"]),
        "demanded_total": sum(p["demanded"] for p in graded),
        "retries_total": sum(p["retries"] for p in graded),
        "mean_elapsed": _mean([p["elapsed"] for p in ok]),
        "max_elapsed": max([p["elapsed"] or 0 for p in ok], default=0.0),
        "total_elapsed": sum(p["elapsed"] or 0 for p in per),
        "per_question": per,
    }
