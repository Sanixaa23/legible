"""The transformations, in two tiers, and the reason the tiers exist.

**Layout tier** (always on). Changes how text is presented and never which
words it contains: spacing, line width, paragraph chunking at sentence
boundaries, clause-per-line segmentation, an extracted cue sentence, and
flags on hard words. Fact retention here is 1.0 by construction, not by
measurement -- these operations cannot delete a token, and a test asserts it
over the whole corpus.

**Rewrite tier** (opt-in). Splits over-long sentences into real sentences.
It is still deterministic and still keeps every token: when it breaks a
sentence at "and", "but" or "so", the connective moves to the front of the
new sentence instead of being dropped. "But the pressure fell" is a
perfectly good sentence, and keeping the word means the contrast the author
wrote survives.

That leaves exactly one place where meaning can be lost: the optional
language-model rewrite in `ai.py`, which is off by default. Its output goes
through `facts.retention` before a reader ever sees it, and a paragraph that
fails is thrown away in favour of the original. The design goal is that the
failure mode of this program is "this paragraph is harder than it could be",
never "this paragraph says something the lesson did not".
"""
from __future__ import annotations

import re
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

from . import evidence, facts, readability

LAYOUT = "layout"
REWRITE = "rewrite"


class Operation(NamedTuple):
    """One transformation, and what it rests on."""

    key: str
    title: str
    tier: str              # LAYOUT or REWRITE
    evidence_key: str      # must exist in evidence.BY_KEY
    default_on: bool
    changes_words: bool    # LAYOUT operations must all be False
    note: str


OPERATIONS: Tuple[Operation, ...] = (
    Operation(
        key="spacing",
        title="Wider letter and line spacing",
        tier=LAYOUT,
        evidence_key="letter_spacing",
        default_on=True,
        changes_words=False,
        note="The one setting here with a measured effect on dyslexic "
             "readers. On by default, and first in the list for that reason.",
    ),
    Operation(
        key="line_width",
        title="Narrow the line to about 66 characters",
        tier=LAYOUT,
        evidence_key="line_length",
        default_on=True,
        changes_words=False,
        note="A convention, not a measurement. Adjustable, because the "
             "number is not sacred.",
    ),
    Operation(
        key="chunk",
        title="Break long paragraphs at sentence boundaries",
        tier=LAYOUT,
        evidence_key="paragraph_length",
        default_on=True,
        changes_words=False,
        note="Splits only where the author already ended a sentence, so the "
             "text is untouched and only the white space is new.",
    ),
    Operation(
        key="clause_lines",
        title="One clause per line inside long sentences",
        tier=LAYOUT,
        evidence_key="sentence_length",
        default_on=True,
        changes_words=False,
        note="Gives a long sentence the shape of a short one without "
             "rewriting it. Nothing is added or removed; the line breaks "
             "fall at commas and connectives.",
    ),
    Operation(
        key="anchor",
        title="Show the paragraph's own key sentence first",
        tier=LAYOUT,
        evidence_key="anchor_sentence",
        default_on=True,
        changes_words=False,
        note="Extracted from the paragraph, never written. A generated cue "
             "could state something the lesson does not say, so we do not "
             "generate one.",
    ),
    Operation(
        key="flag_hard_words",
        title="Mark words likely to need explaining",
        tier=LAYOUT,
        evidence_key="sentence_length",
        default_on=True,
        changes_words=False,
        note="Three or more syllables and not in the common-word list. A "
             "flag is a prompt for the teacher, not a claim about the word.",
    ),
    Operation(
        key="split_sentences",
        title="Split sentences over 25 words into separate sentences",
        tier=REWRITE,
        evidence_key="sentence_length",
        default_on=False,
        changes_words=False,
        note="Deterministic and token-preserving: the connective starts the "
             "new sentence instead of being deleted. Off by default because "
             "it changes the author's punctuation, which is a teacher's call.",
    ),
)

BY_KEY: Dict[str, Operation] = {o.key: o for o in OPERATIONS}

DEFAULTS: Dict[str, bool] = {o.key: o.default_on for o in OPERATIONS}

# Connectives we are willing to break a sentence at. Subordinators such as
# "because", "although" and "which" are absent on purpose: breaking there
# leaves a fragment that only reads as a sentence if you add words, and
# adding words is how meaning gets changed.
SPLIT_CONNECTIVES = ("and", "but", "so", "yet", "or", "however", "therefore")

# Where a clause line may break. Same logic, lower stakes: these only
# introduce a line break, never a sentence boundary.
_CLAUSE_BREAK = re.compile(
    r"(?<=,)\s+(?=(?:and|but|so|yet|or|which|who|that|because|although|"
    r"while|when|if|where|whereas|since|after|before|unless|until)\b)",
    re.IGNORECASE,
)
_ALSO_BREAK = re.compile(r"(?<=[;:])\s+")

COMMON_WORDS = frozenset("""
the be to of and a in that have i it for not on with he as you do at this but
his by from they we say her she or an will my one all would there their what
so up out if about who get which go me when make can like time no just him
know take people into year your good some could them see other than then now
look only come its over think also back after use two how our work first well
way even new want because any these give day most us is are was were been
being has had did does doing very much many more less little big small
water energy plant plants animal animals cell cells body earth sun light heat
air food plan change part number system group area line number different
important example used using called means made both each every
""".split())


class Flag(NamedTuple):
    word: str
    syllables: int
    reason: str


class Sentence(NamedTuple):
    text: str
    word_count: int
    lines: List[str]        # clause lines; one entry when not segmented
    is_long: bool


class Paragraph(NamedTuple):
    index: int
    anchor: Optional[str]
    sentences: List[Sentence]
    word_count: int
    flags: List[Flag]
    was_chunked: bool


def apply_layout(text: str, settings: Dict[str, bool]) -> List[Paragraph]:
    """Lay the text out. Returns paragraphs; never alters a word."""
    on = dict(DEFAULTS)
    on.update(settings or {})

    raw_paragraphs = readability.paragraphs(text)
    out: List[Paragraph] = []
    index = 0

    for raw in raw_paragraphs:
        pieces = _chunk(raw) if on.get("chunk", True) else [raw]
        for piece_i, piece in enumerate(pieces):
            sents = readability.sentences(piece)
            sentences = []
            for s in sents:
                n = len(readability.words(s))
                long = n >= readability.LONG_SENTENCE_WORDS
                lines = (
                    clause_lines(s) if (long and on.get("clause_lines", True))
                    else [s]
                )
                sentences.append(Sentence(s, n, lines, long))

            out.append(Paragraph(
                index=index,
                anchor=(_anchor(sents) if on.get("anchor", True) else None),
                sentences=sentences,
                word_count=len(readability.words(piece)),
                flags=(hard_words(piece) if on.get("flag_hard_words", True) else []),
                was_chunked=len(pieces) > 1,
            ))
            index += 1

    return out


def _chunk(paragraph: str) -> List[str]:
    """Break a long paragraph at sentence boundaries, nowhere else."""
    sents = readability.sentences(paragraph)
    total = len(readability.words(paragraph))
    if total < readability.LONG_PARAGRAPH_WORDS or len(sents) < 2:
        return [paragraph]

    # Aim for pieces under the threshold without ever splitting a sentence.
    pieces: List[str] = []
    current: List[str] = []
    count = 0
    for s in sents:
        n = len(readability.words(s))
        if current and count + n > readability.LONG_PARAGRAPH_WORDS:
            pieces.append(" ".join(current))
            current, count = [s], n
        else:
            current.append(s)
            count += n
    if current:
        pieces.append(" ".join(current))
    return pieces


def clause_lines(sentence: str) -> List[str]:
    """Break one sentence into clause lines. Adds and removes nothing."""
    parts = _ALSO_BREAK.split(sentence)
    lines: List[str] = []
    for part in parts:
        lines.extend(p for p in _CLAUSE_BREAK.split(part) if p)

    # Merge away slivers: a three-word line is noise, not structure.
    merged: List[str] = []
    for line in lines:
        if merged and len(readability.words(line)) < 4:
            merged[-1] = merged[-1] + " " + line
        else:
            merged.append(line)
    return merged or [sentence]


def _anchor(sents: Sequence[str]) -> Optional[str]:
    """Pick the paragraph's most representative existing sentence.

    Scored on how much of the paragraph's own repeated vocabulary a sentence
    carries, divided by its length so a long sentence does not win by
    covering everything. Extractive by design: see the note on the `anchor`
    operation.
    """
    # Three sentences up. Picking 1 of 2 as "the key one" is noise, not a
    # cue, and it makes the reader read the same line twice for nothing.
    if len(sents) < 3:
        return None

    freq: Dict[str, int] = {}
    for s in sents:
        for w in readability.words(s):
            lw = w.lower()
            if lw not in COMMON_WORDS and len(lw) > 3:
                freq[lw] = freq.get(lw, 0) + 1
    if not freq:
        return None

    best, best_score = None, -1.0
    for s in sents:
        ws = [w.lower() for w in readability.words(s)]
        if not ws:
            continue
        score = sum(freq.get(w, 0) for w in set(ws)) / (len(ws) ** 0.5)
        if score > best_score:
            best, best_score = s, score
    return best


def hard_words(text: str) -> List[Flag]:
    """Words that probably need explaining. A prompt, not a judgement.

    Proper nouns are skipped. "Iceland" is long and uncommon but a glossary
    entry for it helps nobody, while "photosynthesis" -- capitalised only
    because it opens the sentence -- is exactly the word to flag. The
    position-based name test in `facts` separates the two, which is the
    second job that one heuristic turned out to do.
    """
    names = {f.value for f in facts.extract(text) if f.kind == facts.NAME}
    seen = set()
    flags: List[Flag] = []
    for w in readability.words(text):
        lw = w.lower()
        if lw in seen or lw in COMMON_WORDS or len(lw) < 7:
            continue
        if lw in names:
            continue
        syl = readability.syllables(lw)
        if syl >= 3:
            seen.add(lw)
            flags.append(Flag(w, syl, "%d syllables, not a common word" % syl))
    return flags


def split_sentences(text: str) -> str:
    """Rewrite tier: split over-long sentences, keeping every token.

    The connective is not deleted; it starts the new sentence. That is what
    makes this operation safe enough to be deterministic, and it is why
    `tests/test_retention.py` can assert 1.0 retention for it over the
    corpus rather than merely checking it.
    """
    out_paragraphs = []
    for para in readability.paragraphs(text):
        rebuilt = []
        for s in readability.sentences(para):
            rebuilt.extend(_split_one(s))
        out_paragraphs.append(" ".join(rebuilt))
    return "\n\n".join(out_paragraphs)


def _split_one(sentence: str) -> List[str]:
    n = len(readability.words(sentence))
    if n < readability.SPLIT_SENTENCE_WORDS:
        return [sentence]

    pattern = re.compile(
        r",\s+(%s)\s+" % "|".join(SPLIT_CONNECTIVES), re.IGNORECASE)

    best = None
    for m in pattern.finditer(sentence):
        left = sentence[:m.start()]
        right = sentence[m.end():]
        if _would_strand_a_fragment(left, right):
            continue
        if (len(readability.words(left)) >= 5
                and len(readability.words(right)) >= 5):
            # Prefer a break near the middle: the goal is two readable
            # halves, not one short sentence and one long one.
            offset = abs(m.start() - len(sentence) // 2)
            if best is None or offset < best[0]:
                best = (offset, m)

    if best is None:
        return [sentence]

    m = best[1]
    left = sentence[:m.start()].rstrip(" ,")
    connective = m.group(1)
    right = sentence[m.end():]

    if not re.search(r"[.!?…][\"'”)\]]*$", left):
        left += "."
    head = connective[:1].upper() + connective[1:]
    right = head + " " + right

    # Recurse: a 60-word sentence needs more than one break.
    return _split_one(left) + _split_one(right)


# The two shapes where ", and" continues a list instead of joining clauses.
# Found by running the splitter over corpus/01: the biology paragraph says
# "it has two stages: the light-dependent stage, which ..., and the
# light-independent stage, which ...". Splitting at that last "and" produced
# "And the light-independent stage, which uses ..." -- a noun phrase with no
# main verb, presented to a child as a sentence. Neither rule needs a parser.
_LIST_ITEM = re.compile(
    r"^(?:the|a|an|its|their)\s+[\w-]+(?:\s+[\w-]+){0,2},\s+"
    r"(?:which|who|that)",
    re.IGNORECASE,
)


def _would_strand_a_fragment(left: str, right: str) -> bool:
    """True when breaking here leaves something that is not a sentence.

    Two cases, both about lists rather than grammar in general:

    1. The left half opens a list with a colon. Everything after it is an
       item of that list, so no break inside it stands alone.
    2. The right half has the shape of a list item: a determiner, a short
       noun phrase, then a relative clause. "The light-independent stage,
       which uses ..." has no main verb for its subject.

    A real parser would do better. This catches the shape that actually
    appeared in the corpus, and when it is unsure it declines to split --
    which costs a reader one long sentence, not a wrong one.
    """
    if ":" in left:
        return True
    return bool(_LIST_ITEM.match(right.strip()))


def validate_operations() -> List[str]:
    """Self-check used by the tests. Returns a list of problems, empty is good."""
    problems = []
    for op in OPERATIONS:
        try:
            evidence.finding(op.evidence_key)
        except KeyError as exc:
            problems.append(str(exc))
        if op.tier == LAYOUT and op.changes_words:
            problems.append(
                "%s is in the layout tier but declares changes_words=True"
                % op.key)
        if op.tier not in (LAYOUT, REWRITE):
            problems.append("%s has unknown tier %r" % (op.key, op.tier))
    return problems
