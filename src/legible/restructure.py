"""The pipeline: text in, a checked Document out.

Order matters and is fixed:

1. Measure the original.
2. Rewrite tier, if the teacher turned it on. Check retention immediately;
   if anything was lost, discard the rewrite and carry on with the original.
3. Layout tier on whatever survived step 2. This tier cannot lose anything.
4. Measure the result, and report the change rather than the absolute.

Step 2 is the only step that can fail, and it fails closed: the reader gets
the author's sentence back. That is the whole safety argument of this
program, and `tests/test_retention.py` is where it is kept honest.
"""
from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional

from . import facts, readability, transform


class Document(NamedTuple):
    original: str
    text: str                          # after the rewrite tier, if any
    paragraphs: List[transform.Paragraph]
    before: readability.Metrics
    after: readability.Metrics
    delta: Dict[str, float]
    retention: facts.Retention
    rewrite_applied: bool
    rewrite_rejected: Optional[str]    # why, when the gate refused it
    settings: Dict[str, bool]
    watched: Dict[str, List[str]]      # the facts we checked, for display
    longest_line_words: int            # see the note below

    # `longest_line_words` is the layout tier's own measure, and it exists
    # because the sentence statistics cannot see that tier at all. Layout
    # changes no words, so words-per-sentence is identical before and after
    # and the whole panel read "unchanged" while the screen had visibly
    # changed. What a clause-per-line layout actually shortens is the longest
    # unbroken run a reader has to track in one go, so that is what we report.

    @property
    def safe(self) -> bool:
        """True when nothing that matters was lost. Must be True to display."""
        return self.retention.ok

    def sentence_lengths(self) -> List[int]:
        return [s.word_count for p in self.paragraphs for s in p.sentences]


def build(text: str, settings: Optional[Dict[str, bool]] = None) -> Document:
    """Run the pipeline. Never raises on ordinary text, including empty."""
    on = dict(transform.DEFAULTS)
    on.update(settings or {})

    before = readability.measure(text)
    working = text
    rewrite_applied = False
    rejected = None

    if on.get("split_sentences", False):
        candidate = transform.split_sentences(text)
        check = facts.retention(text, candidate)
        if check.ok:
            working = candidate
            rewrite_applied = True
        else:
            # Fail closed. The reader gets the author's sentence.
            rejected = check.summary()

    paragraphs = transform.apply_layout(working, on)
    after = readability.measure(working)

    line_words = [len(readability.words(line))
                  for p in paragraphs for s in p.sentences for line in s.lines]

    return Document(
        original=text,
        text=working,
        paragraphs=paragraphs,
        before=before,
        after=after,
        delta=readability.delta(before, after),
        retention=facts.retention(text, working),
        rewrite_applied=rewrite_applied,
        rewrite_rejected=rejected,
        settings=on,
        watched=facts.describe(facts.extract(text)),
        longest_line_words=max(line_words) if line_words else 0,
    )


def summary_lines(doc: Document) -> List[str]:
    """The plain-text report the CLI prints. One fact per line, no prose."""
    d = doc.delta
    lines = [
        "Words                 %d" % doc.before.words,
        "Sentences             %d -> %d" % (doc.before.sentences, doc.after.sentences),
        "Mean sentence words   %.1f -> %.1f (%+.1f)" % (
            doc.before.mean_sentence_words, doc.after.mean_sentence_words,
            d["mean_sentence_words"]),
        "Longest sentence      %d -> %d words" % (
            doc.before.longest_sentence_words, doc.after.longest_sentence_words),
        "Sentences over %d     %d -> %d" % (
            readability.LONG_SENTENCE_WORDS,
            doc.before.long_sentences, doc.after.long_sentences),
        "Paragraphs over %d    %d -> %d" % (
            readability.LONG_PARAGRAPH_WORDS,
            doc.before.long_paragraphs, doc.after.long_paragraphs),
        "Flesch reading ease   %.1f -> %.1f (%+.1f)" % (
            doc.before.flesch_reading_ease, doc.after.flesch_reading_ease,
            d["flesch_reading_ease"]),
        "Flesch-Kincaid grade  %.1f -> %.1f (%+.1f)" % (
            doc.before.flesch_kincaid_grade, doc.after.flesch_kincaid_grade,
            d["flesch_kincaid_grade"]),
        "Reading blocks        %d -> %d" % (doc.before.paragraphs,
                                            len(doc.paragraphs)),
        "Longest unbroken line %d -> %d words" % (
            doc.before.longest_sentence_words, doc.longest_line_words),
        "Words flagged         %d" % sum(len(p.flags) for p in doc.paragraphs),
        "Meaning check         %s" % doc.retention.summary(),
    ]
    if doc.rewrite_rejected:
        lines.append(
            "Rewrite rejected      %s -- showing the original" % doc.rewrite_rejected)
    return lines
