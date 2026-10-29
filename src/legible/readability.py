"""Deterministic text measurement. No model, no network, no randomness.

Every number this program shows a teacher is computed here, in code they can
read. A language model is never asked how readable something is, because the
answer has to be the same twice and has to be auditable when a teacher
disagrees with it.

The syllable counter is a heuristic, and the tests say so out loud: see
`tests/test_readability.py`, which pins the words it gets wrong. Flesch
scores built on it are therefore approximate, which is why the reading view
reports a *change* in score between two versions of the same text rather
than presenting an absolute grade level as a fact about a child.
"""
from __future__ import annotations

import re
from typing import Dict, List, NamedTuple, Sequence

# Thresholds. The evidence tier for each is recorded in evidence.py; these
# are the numbers, kept in one place so the tests and the UI agree.
LONG_SENTENCE_WORDS = 20       # flag at
SPLIT_SENTENCE_WORDS = 25      # try to split at
LONG_PARAGRAPH_WORDS = 50      # flag at
TARGET_LINE_CHARS = 66         # middle of the BDA's 60-70

# Words that end in a period without ending a sentence.
ABBREVIATIONS = frozenset("""
mr mrs ms dr prof sr jr st rev hon capt sgt
etc vs cf al ca approx est fig figs no nos vol pp
e.g i.e a.m p.m u.s u.k
jan feb mar apr jun jul aug sep sept oct nov dec
mon tue tues wed thu thurs fri sat sun
""".split())

_WORD = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)*")
_TOKEN = re.compile(r"\S+")
_VOWEL_RUN = re.compile(r"[aeiouy]+")

# A sentence ends at . ! ? or an ellipsis, optionally followed by a closing
# quote or bracket, then whitespace. The lookahead avoids splitting decimals
# (3.5) and initials (J. Smith) by requiring whitespace after the mark.
_SENTENCE_END = re.compile(r'([.!?]+|…)(["”\')\]]*)(\s+|$)')


class Metrics(NamedTuple):
    """Everything measurable about a piece of text, with no interpretation."""

    characters: int
    words: int
    sentences: int
    syllables: int
    paragraphs: int
    mean_sentence_words: float
    longest_sentence_words: int
    long_sentences: int            # at or over LONG_SENTENCE_WORDS
    long_paragraphs: int           # at or over LONG_PARAGRAPH_WORDS
    longest_line_chars: int
    polysyllable_words: int        # three or more syllables
    flesch_reading_ease: float
    flesch_kincaid_grade: float

    def as_dict(self) -> Dict[str, object]:
        return dict(self._asdict())


def paragraphs(text: str) -> List[str]:
    """Split on blank lines. A single newline is a soft wrap, not a break."""
    chunks = re.split(r"\n[ \t]*\n+", text.replace("\r\n", "\n").replace("\r", "\n"))
    return [c.strip() for c in chunks if c.strip()]


def sentences(text: str) -> List[str]:
    """Split into sentences, keeping the terminating punctuation.

    Deliberately simple and deliberately documented: it splits on sentence
    punctuation followed by whitespace, and refuses to split after a known
    abbreviation or a single initial. It will still be wrong on text that
    writes "Dr" without a period or abbreviates something we have not listed,
    which is why nothing downstream assumes the split is perfect -- the
    transformations only ever reorder or break text, never delete it.
    """
    flat = " ".join(text.split())
    if not flat:
        return []

    out: List[str] = []
    start = 0
    for m in _SENTENCE_END.finditer(flat):
        head = flat[start:m.end(2)]
        if _ends_in_abbreviation(head):
            continue
        out.append(head.strip())
        start = m.end()
    tail = flat[start:].strip()
    if tail:
        out.append(tail)
    return out


def _ends_in_abbreviation(chunk: str) -> bool:
    """True when the final period belongs to an abbreviation, not a sentence."""
    if not chunk.endswith("."):
        return False
    last = chunk.rstrip(".").split()
    if not last:
        return False
    word = last[-1].lower().strip("([\"'“")
    if word in ABBREVIATIONS:
        return True
    # A single letter is an initial: "J. Smith", "H. pylori".
    return len(word) == 1 and word.isalpha()


def words(text: str) -> List[str]:
    return _WORD.findall(text)


def syllables(word: str) -> int:
    """Count syllables in an English word. A heuristic, and known to be one.

    Rules, in order: strip a silent trailing 'e', count runs of vowels, add
    one back for a '-le' ending after a consonant, and never return zero.
    Tested against a list of words it gets right and a list it gets wrong.
    """
    w = word.lower().strip("'’")
    if not any(c.isalpha() for c in w):
        return 0          # punctuation and bare digits are not syllables
    if len(w) <= 3:
        return 1

    # 'ly' and 'es'/'ed' endings often add no vowel run of their own.
    stem = re.sub(r"(?:[^laeiouy]es|[^laeiouy]ed)$", "", w)
    stem = re.sub(r"e$", "", stem) or w

    count = len(_VOWEL_RUN.findall(stem))
    if re.search(r"[^aeiouy]le$", w):
        count += 1
    if w.endswith("ism") or w.endswith("sms"):
        count += 1
    return max(1, count)


def measure(text: str) -> Metrics:
    """Measure a whole document."""
    paras = paragraphs(text)
    sents = [s for p in paras for s in sentences(p)]
    all_words = words(text)

    per_sentence = [len(words(s)) for s in sents]
    per_paragraph = [len(words(p)) for p in paras]
    syl = [syllables(w) for w in all_words]
    total_syl = sum(syl)

    lines = text.replace("\r\n", "\n").split("\n")

    n_words = len(all_words)
    n_sents = len(sents)
    return Metrics(
        characters=len(text),
        words=n_words,
        sentences=n_sents,
        syllables=total_syl,
        paragraphs=len(paras),
        mean_sentence_words=(n_words / n_sents) if n_sents else 0.0,
        longest_sentence_words=max(per_sentence) if per_sentence else 0,
        long_sentences=sum(1 for n in per_sentence if n >= LONG_SENTENCE_WORDS),
        long_paragraphs=sum(1 for n in per_paragraph if n >= LONG_PARAGRAPH_WORDS),
        longest_line_chars=max((len(l) for l in lines), default=0),
        polysyllable_words=sum(1 for n in syl if n >= 3),
        flesch_reading_ease=_flesch_reading_ease(n_words, n_sents, total_syl),
        flesch_kincaid_grade=_flesch_kincaid_grade(n_words, n_sents, total_syl),
    )


def _flesch_reading_ease(n_words: int, n_sents: int, n_syl: int) -> float:
    """Higher is easier. 0 and below, and 100 and above, both happen."""
    if not n_words or not n_sents:
        return 0.0
    return round(
        206.835 - 1.015 * (n_words / n_sents) - 84.6 * (n_syl / n_words), 1
    )


def _flesch_kincaid_grade(n_words: int, n_sents: int, n_syl: int) -> float:
    """US school grade. Can go negative on very short text; we do not clamp."""
    if not n_words or not n_sents:
        return 0.0
    return round(0.39 * (n_words / n_sents) + 11.8 * (n_syl / n_words) - 15.59, 1)


def delta(before: Metrics, after: Metrics) -> Dict[str, float]:
    """What changed, for the fields where a change means something.

    Reported as a change rather than an absolute, because the absolute rests
    on a heuristic syllable count. A change computed the same way on both
    sides is the honest number.
    """
    return {
        "flesch_reading_ease": round(
            after.flesch_reading_ease - before.flesch_reading_ease, 1),
        "flesch_kincaid_grade": round(
            after.flesch_kincaid_grade - before.flesch_kincaid_grade, 1),
        "mean_sentence_words": round(
            after.mean_sentence_words - before.mean_sentence_words, 1),
        "long_sentences": after.long_sentences - before.long_sentences,
        "long_paragraphs": after.long_paragraphs - before.long_paragraphs,
        "longest_sentence_words": (
            after.longest_sentence_words - before.longest_sentence_words),
        "words": after.words - before.words,
    }


def distribution(sentence_lengths: Sequence[int]) -> Dict[str, int]:
    """Buckets for the reading view's little histogram."""
    buckets = {"1-10": 0, "11-20": 0, "21-30": 0, "31+": 0}
    for n in sentence_lengths:
        if n <= 10:
            buckets["1-10"] += 1
        elif n <= 20:
            buckets["11-20"] += 1
        elif n <= 30:
            buckets["21-30"] += 1
        else:
            buckets["31+"] += 1
    return buckets
