"""Tiny text-similarity helpers.

Used at runtime to catch council members making each other's arguments, and by
the eval harness to score how distinct the lenses actually are. No
dependencies on purpose: this runs inside every deliberation.
"""

import re

_STOPWORDS = frozenset({
    "a", "an", "and", "the", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "in", "on", "for", "with", "without", "at", "by", "from", "as", "into",
    "it", "its", "this", "that", "these", "those", "there", "their", "them", "they",
    "you", "your", "yours", "he", "she", "his", "her", "we", "our", "us", "i", "my",
    "not", "no", "but", "or", "if", "then", "than", "so", "too", "very", "just", "only",
    "will", "would", "can", "could", "should", "shall", "may", "might", "must", "do",
    "does", "did", "done", "have", "has", "had", "having", "get", "gets", "got",
    "more", "most", "less", "least", "much", "many", "any", "all", "some", "each",
    "what", "which", "who", "whom", "when", "where", "why", "how", "while", "about",
    "over", "under", "before", "after", "up", "down", "out", "off", "again", "here",
    "one", "two", "both", "other", "another", "such", "own", "same", "now",
})

_WORD = re.compile(r"[a-z0-9']+")


def content_words(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2]


def overlap(a: str, b: str) -> float:
    """Jaccard similarity of the two texts' content vocabularies."""
    sa, sb = set(content_words(a)), set(content_words(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def longest_shared_phrase(a: str, b: str) -> int:
    """Words in the longest contiguous run of content words shared by both."""
    wa, wb = content_words(a), content_words(b)
    if not wa or not wb:
        return 0
    prev = [0] * (len(wb) + 1)
    best = 0
    for i in range(1, len(wa) + 1):
        cur = [0] * (len(wb) + 1)
        for j in range(1, len(wb) + 1):
            if wa[i - 1] == wb[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


# Calibrated against real v0.12 output. The observed collapse case — two
# members both answering "two months of savings is insufficient runway" —
# scores 0.30 overlap with a 4-word shared run, while genuinely distinct
# lenses on the same question land under 0.20.
ECHO_OVERLAP = 0.28
ECHO_PHRASE_WORDS = 4


def is_echo(a: str, b: str) -> bool:
    """True when two members are making the same argument in different words."""
    if not a or not b:
        return False
    return overlap(a, b) >= ECHO_OVERLAP or longest_shared_phrase(a, b) >= ECHO_PHRASE_WORDS
