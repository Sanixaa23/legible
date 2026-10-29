"""The claim this project is willing to be judged on.

Run it directly to print the table:

    python tests/test_retention.py

For every file in `corpus/`, with the rewrite tier on and off, we check that
not one number, unit, name, negation or modality word was lost. The layout
tier should be perfect by construction; the rewrite tier should be perfect by
design. Anything less than 1.0 is a bug, and the table says which file.

The adversarial file exists to make this test capable of failing: every
paragraph in `06_adversarial_negation.txt` has its meaning sitting in a
negation or a hedge. A tool that drops one scores well on readability and is
worse than no tool at all.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from legible import facts, readability, restructure, transform  # noqa: E402

CORPUS = os.path.join(ROOT, "corpus")


def corpus_files():
    return sorted(
        f for f in os.listdir(CORPUS)
        if f.endswith(".txt")
    )


def read(name):
    with open(os.path.join(CORPUS, name), encoding="utf-8") as f:
        return f.read()


# --- the claim ------------------------------------------------------------

def test_layout_tier_loses_nothing():
    """The default path cannot lose a fact. Checked on every file."""
    for name in corpus_files():
        text = read(name)
        doc = restructure.build(text, {"split_sentences": False})
        assert doc.retention.ok, "%s: %s" % (name, doc.retention.summary())
        assert doc.retention.rate == 1.0


def test_rewrite_tier_loses_nothing():
    """The opt-in sentence splitter keeps every token too."""
    for name in corpus_files():
        text = read(name)
        doc = restructure.build(text, {"split_sentences": True})
        assert doc.retention.ok, "%s: %s" % (name, doc.retention.summary())
        assert doc.rewrite_rejected is None, "%s: %s" % (name, doc.rewrite_rejected)


def test_adversarial_file_actually_carries_the_risk():
    """Guards the guard: if this file stops containing negations, say so.

    A retention test over a corpus with nothing to lose passes trivially.
    """
    text = read("06_adversarial_negation.txt")
    found = facts.extract(text)
    negations = [f for f in found if f.kind == facts.NEGATION]
    modalities = [f for f in found if f.kind == facts.MODALITY]
    assert len(negations) >= 10, "only %d negations" % len(negations)
    assert len(modalities) >= 8, "only %d modality words" % len(modalities)


def test_a_naive_simplification_is_caught():
    """The test that proves the check is not vacuous.

    This is what a careless rewrite of the physics paragraph looks like. It
    reads better than the original and says the opposite.
    """
    original = (
        "Newton's first law states that an object will not change its motion "
        "unless a resultant force acts on it. This is sometimes misread as a "
        "claim that moving objects naturally slow down. They do not."
    )
    naive = (
        "Newton's first law says an object changes its motion when a force "
        "acts on it. Moving objects naturally slow down."
    )
    check = facts.retention(original, naive)
    assert not check.ok
    assert check.lost[facts.NEGATION], "the lost negation was not detected"


def test_rewrite_is_rejected_rather_than_shown():
    """Fail closed: a losing rewrite must not reach the reader."""
    original = "The rate may not rise above 10 degrees, and only 3 of 40 samples reacted."

    real_split = transform.split_sentences
    transform.split_sentences = lambda text: "The rate rises above 10 degrees. Samples reacted."
    try:
        doc = restructure.build(original, {"split_sentences": True})
        assert doc.text == original, "a losing rewrite was shown to the reader"
        assert doc.rewrite_applied is False
        assert doc.rewrite_rejected and "negation" in doc.rewrite_rejected
        assert doc.safe
    finally:
        transform.split_sentences = real_split


# --- the controls ---------------------------------------------------------

def test_already_simple_text_is_left_alone():
    """No invented improvement on text that was already fine."""
    text = read("90_control_already_simple.txt")
    doc = restructure.build(text, {"split_sentences": True})
    assert doc.delta["flesch_reading_ease"] == 0.0
    assert doc.after.long_sentences == 0
    assert all(not s.is_long for p in doc.paragraphs for s in p.sentences)


def test_two_sentence_text_gets_no_anchor_and_no_chunking():
    text = read("91_control_two_sentences.txt")
    doc = restructure.build(text)
    assert len(doc.paragraphs) == 1
    assert doc.paragraphs[0].was_chunked is False
    assert doc.paragraphs[0].anchor is None, "invented an anchor for two sentences"


def test_the_rewrite_tier_changes_something_somewhere():
    """Guards the other direction: a no-op would also pass retention."""
    changed = 0
    for name in corpus_files():
        text = read(name)
        if transform.split_sentences(text) != " ".join(text.split()).replace(
                "", ""):
            pass
        before = readability.measure(text)
        after = readability.measure(transform.split_sentences(text))
        if after.sentences > before.sentences:
            changed += 1
    assert changed >= 4, "the splitter only affected %d files" % changed


# --- the report -----------------------------------------------------------

def table():
    """Print the retention table. This is the figure quoted in the README."""
    rows = []
    for name in corpus_files():
        text = read(name)
        layout = restructure.build(text, {"split_sentences": False})
        rewrite = restructure.build(text, {"split_sentences": True})
        found = facts.extract(text)
        rows.append((name, len(found), layout, rewrite))

    width = max(len(r[0]) for r in rows)
    print()
    print("FACT RETENTION".ljust(width + 2), "items  layout  rewrite   sentences   ease")
    print("-" * (width + 48))

    total_items = 0
    total_lost = 0
    for name, n_items, layout, rewrite in rows:
        total_items += n_items * 2
        total_lost += layout.retention.lost_count + rewrite.retention.lost_count
        print("%s  %5d  %6s  %7s   %3d -> %-3d  %+5.1f" % (
            name.ljust(width),
            n_items,
            "%.2f" % layout.retention.rate,
            "%.2f" % rewrite.retention.rate,
            rewrite.before.sentences,
            rewrite.after.sentences,
            rewrite.delta["flesch_reading_ease"],
        ))

    print("-" * (width + 48))
    kept = total_items - total_lost
    print("%d of %d checked items kept across %d files, both tiers (%.1f%%)" % (
        kept, total_items, len(rows), 100.0 * kept / total_items))
    print()
    print("Layout tier cannot lose a token by construction; the rewrite tier")
    print("keeps connectives instead of deleting them. The adversarial file")
    print("carries %d negations and %d hedges, so this table can fail." % (
        len([f for f in facts.extract(read("06_adversarial_negation.txt"))
             if f.kind == facts.NEGATION]),
        len([f for f in facts.extract(read("06_adversarial_negation.txt"))
             if f.kind == facts.MODALITY]),
    ))
    return total_lost


if __name__ == "__main__":
    sys.exit(1 if table() else 0)
