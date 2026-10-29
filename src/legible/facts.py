"""The things a rewrite is not allowed to lose.

This is the module the whole project rests on. Making text easier to read
means changing it, and every tool that changes text can change what it says.
The failure is not theoretical and it is not rare: the two ways simplifiers
quietly lie are dropping a negation ("does not cause" becomes "causes") and
flattening a modal ("may cause" becomes "causes"). Both read beautifully.
Both are wrong, and a child studying from the result cannot tell.

So before anything is shown to a reader, we extract from the original every
token whose loss would change the meaning -- numbers, units, names,
negations, and words that set how strong a claim is -- and we check that all
of them survived. A transformation that loses one is rejected and the
original paragraph is kept. The reader sees a slightly harder sentence,
which is the correct failure.

Nothing here understands English. It is a conservative token check, and
conservative in a specific direction: it over-collects, so it fails loudly
rather than passing something it should not. The retention number in the
README is produced by running this over `corpus/`.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Dict, List, NamedTuple, Tuple

NUMBER = "number"
NEGATION = "negation"
MODALITY = "modality"
NAME = "name"
UNIT = "unit"

KINDS: Tuple[str, ...] = (NUMBER, NEGATION, MODALITY, NAME, UNIT)

KIND_WHY: Dict[str, str] = {
    NUMBER: "A changed or missing quantity makes the text wrong, not just different.",
    NEGATION: "Losing a negation reverses the claim. This is the most dangerous single failure.",
    MODALITY: "'May cause' and 'causes' are different claims. Flattening one overstates the text.",
    NAME: "A name, place or term the lesson is about must still be there to be studied.",
    UNIT: "A number without its unit is not an answer.",
}

# Negation. Includes the contracted forms, which are easy to lose when a
# sentence is split at a conjunction.
NEGATIONS = frozenset("""
no not none never neither nor nothing nobody nowhere
cannot cant dont doesnt didnt wont wouldnt shouldnt couldnt
isnt arent wasnt werent hasnt havent hadnt
without unlike except unless
""".split())

# Contracted auxiliaries are literally "auxiliary + not", so they collapse to
# the negation they carry. Without this, expanding "doesn't" into "does not"
# -- a legitimate simplification -- looked like a lost negation and the
# rewrite was rejected. The auxiliary itself is not what we are protecting;
# the negation is. "nobody" and "none" are deliberately NOT collapsed, because
# they carry more than a negation.
NEGATION_CANON: Dict[str, str] = {
    "cannot": "not", "cant": "not",
    "dont": "not", "doesnt": "not", "didnt": "not",
    "wont": "not", "wouldnt": "not", "shouldnt": "not", "couldnt": "not",
    "isnt": "not", "arent": "not", "wasnt": "not", "werent": "not",
    "hasnt": "not", "havent": "not", "hadnt": "not",
}

# Words that set how strong or how general a claim is. Losing one of these
# turns a hedged statement into a confident one.
MODALITIES = frozenset("""
may might could can must should would shall will
always usually often sometimes rarely seldom occasionally
all every each most many some few several any both
only just about approximately roughly nearly almost
likely unlikely possibly probably certainly perhaps
generally typically mainly mostly partly
at_least at_most up_to more_than less_than
""".split())

# Units we recognise next to a number. Deliberately short: a unit we do not
# know is still caught as a NAME or simply left in place, because nothing
# deletes text.
UNITS = frozenset("""
mm cm m km in ft yd mi
mg g kg lb oz t
ml l litre litres liter liters gal
s ms sec secs second seconds min mins minute minutes
h hr hrs hour hours day days week weeks month months year years
k hz khz mhz ghz b kb mb gb tb
c f k degree degrees celsius fahrenheit kelvin
v w kw kwh j kj cal kcal n pa atm mol
percent pct
""".split())

_NUMBER_RE = re.compile(
    r"""
    (?<![\w.])                 # not inside a word or a version string
    [+-]?                      # sign
    (?:
        \d{1,3}(?:[,  ]\d{3})+(?:\.\d+)?   # 1,234,567.89
      | \d+(?:\.\d+)?                                # 12 or 12.5
      | \.\d+                                        # .5
    )
    (?:\s*%|°)?           # trailing percent or degree sign
    """,
    re.VERBOSE,
)

_WORDY_NUMBER = frozenset("""
zero one two three four five six seven eight nine ten
eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen
twenty thirty forty fifty sixty seventy eighty ninety
hundred thousand million billion trillion
half third quarter
first second third fourth fifth
double triple twice
""".split())

_WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
_SENTENCE_START = re.compile(r"(?:^|[.!?]\s+|\n\s*|[:;]\s+|[•-]\s+)$")


class Fact(NamedTuple):
    kind: str
    value: str      # normalised, for comparison
    surface: str    # as it appeared, for showing a teacher


class Retention(NamedTuple):
    """Did the rewrite keep everything that mattered?"""

    kept: Dict[str, int]
    lost: Dict[str, List[str]]
    total: int

    @property
    def ok(self) -> bool:
        return not any(self.lost.values())

    @property
    def lost_count(self) -> int:
        return sum(len(v) for v in self.lost.values())

    @property
    def rate(self) -> float:
        """Fraction of facts that survived. 1.0 when there were none to lose."""
        if not self.total:
            return 1.0
        return round((self.total - self.lost_count) / self.total, 4)

    def summary(self) -> str:
        if self.ok:
            return "all %d checked items kept" % self.total
        parts = ["%s: %s" % (k, ", ".join(v)) for k, v in self.lost.items() if v]
        return "lost %d of %d (%s)" % (self.lost_count, self.total, "; ".join(parts))


def _norm_word(word: str) -> str:
    """Fold case, strip apostrophes, and strip accents.

    "don't", "dont" and "Don't" all have to compare equal, or a rewrite that
    only changes punctuation would look like it lost a negation.
    """
    w = unicodedata.normalize("NFKD", word.lower())
    w = "".join(c for c in w if not unicodedata.combining(c))
    return w.replace("'", "").replace("’", "")


def _norm_number(raw: str) -> str:
    """Normalise a number so formatting changes are not treated as losses."""
    s = raw.strip()
    percent = s.endswith("%") or s.endswith("°")
    s = s.rstrip("%°").strip()
    s = s.replace(",", "").replace(" ", "").replace(" ", "")
    try:
        value = float(s)
    except ValueError:
        return raw.strip()
    # 3.50 and 3.5 are the same number; 3 and 3.0 are too.
    out = ("%.10f" % value).rstrip("0").rstrip(".") if "." in s else str(int(value))
    return out + ("%" if percent else "")


def extract(text: str, lenient_names: bool = False) -> List[Fact]:
    """Collect every token whose loss would change what the text says.

    `lenient_names` exists because a name is detected by position: a
    capitalised word mid-sentence is a name, and at the start of a sentence
    it is just a capital letter. Splitting a sentence moves words to the
    front, so "Dr. Smith found" after a split looked like a lost name even
    though nothing was deleted. The retention check therefore collects names
    strictly on the original and leniently on the rewrite -- every
    capitalised word counts as a candidate match. Asymmetric on purpose: it
    cannot invent a loss, and it cannot hide a real deletion either, because
    a deleted name is absent from both positions.
    """
    found: List[Fact] = []

    for m in _NUMBER_RE.finditer(text):
        raw = m.group(0)
        found.append(Fact(NUMBER, _norm_number(raw), raw.strip()))

    for m in _WORD_RE.finditer(text):
        word = m.group(0)
        norm = _norm_word(word)

        if norm in NEGATIONS:
            found.append(Fact(NEGATION, NEGATION_CANON.get(norm, norm), word))
            continue
        if norm in MODALITIES:
            found.append(Fact(MODALITY, norm, word))
            continue
        if norm in _WORDY_NUMBER:
            found.append(Fact(NUMBER, norm, word))
            continue
        if norm in UNITS and _follows_number(text, m.start()):
            found.append(Fact(UNIT, norm, word))
            continue
        if lenient_names:
            if word[:1].isupper():
                found.append(Fact(NAME, norm, word))
        elif _is_name(text, m.start(), word):
            found.append(Fact(NAME, norm, word))

    return found


def _follows_number(text: str, pos: int) -> bool:
    """A unit only counts as a unit when a number is in front of it."""
    before = text[max(0, pos - 12):pos]
    return bool(re.search(r"[\d)°]\s*$", before))


def _is_name(text: str, pos: int, word: str) -> bool:
    """A capitalised word that is not merely sentence-initial.

    Over-collects on purpose. A common noun that happens to start a line is
    cheap to keep; a dropped place name is not.
    """
    if not word[:1].isupper():
        return False
    if word.isupper() and len(word) >= 2:
        return True                      # DNA, UK, HTML
    before = text[max(0, pos - 40):pos]
    return not _SENTENCE_START.search(before)


def retention(before: str, after: str) -> Retention:
    """Check that `after` still carries every fact `before` had.

    A multiset comparison, not a set one: text that said "no" twice and now
    says it once has lost something. The transformations in this program
    only split, reorder and annotate, so an exact multiset match is
    achievable -- and when it is not, that is the signal we want.
    """
    want = Counter((f.kind, f.value) for f in extract(before))
    have = Counter((f.kind, f.value) for f in extract(after, lenient_names=True))

    surfaces: Dict[Tuple[str, str], str] = {}
    for f in extract(before):
        surfaces.setdefault((f.kind, f.value), f.surface)

    kept = {k: 0 for k in KINDS}
    lost: Dict[str, List[str]] = {k: [] for k in KINDS}

    for (kind, value), n_want in want.items():
        n_have = have.get((kind, value), 0)
        kept[kind] += min(n_want, n_have)
        missing = n_want - n_have
        if missing > 0:
            surface = surfaces.get((kind, value), value)
            lost[kind].extend([surface] * missing)

    return Retention(kept=kept, lost=lost, total=sum(want.values()))


def describe(facts: List[Fact]) -> Dict[str, List[str]]:
    """Group surfaces by kind, for the reading view's 'what we are watching'."""
    out: Dict[str, List[str]] = {k: [] for k in KINDS}
    for f in facts:
        if f.surface not in out[f.kind]:
            out[f.kind].append(f.surface)
    return out
