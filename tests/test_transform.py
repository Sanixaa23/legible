"""Tests for the transformations, token by token.

The layout tier's promise is stronger than "we checked it": it cannot lose a
word, because none of its operations delete one. These tests hold it to that
by comparing the tokens before and after over the whole corpus, not by
sampling.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from legible import evidence, readability, restructure, transform  # noqa: E402

CORPUS = os.path.join(ROOT, "corpus")


def corpus_texts():
    for name in sorted(os.listdir(CORPUS)):
        if name.endswith(".txt"):
            with open(os.path.join(CORPUS, name), encoding="utf-8") as f:
                yield name, f.read()


def tokens(text):
    return re.findall(r"[^\W_]+", text, re.UNICODE)


def tokens_ci(text):
    """Tokens, case-folded.

    The rewrite tier makes exactly one change a case-sensitive comparison
    would flag: the connective it moves to the front of a new sentence gets
    a capital letter. "and" becoming "And" is the token surviving, not the
    token being replaced, so the rewrite tier is checked case-insensitively
    and the layout tier -- which touches nothing at all -- is not.
    """
    return [t.lower() for t in tokens(text)]


# --- the layout tier's promise --------------------------------------------

def test_layout_preserves_every_token_in_order():
    """Not a sample: every file, every token, same order."""
    for name, text in corpus_texts():
        doc = restructure.build(text, {"split_sentences": False})
        rebuilt = " ".join(
            line
            for p in doc.paragraphs
            for s in p.sentences
            for line in s.lines
        )
        assert tokens(rebuilt) == tokens(text), name


def test_clause_lines_rejoin_to_the_original_sentence():
    sentence = ("The reaction takes place in the chloroplasts, which are "
                "found in the leaf, and it has two stages, although the "
                "second needs no light.")
    lines = transform.clause_lines(sentence)
    assert len(lines) > 1, "nothing was segmented"
    assert " ".join(lines) == sentence


def test_clause_lines_never_leave_a_sliver():
    for _, text in corpus_texts():
        for sentence in readability.sentences(text):
            for line in transform.clause_lines(sentence):
                assert len(readability.words(line)) >= 4 or len(
                    transform.clause_lines(sentence)) == 1, line


def test_chunking_only_splits_where_a_sentence_already_ended():
    long_text = next(t for n, t in corpus_texts() if n.startswith("01_"))
    doc = restructure.build(long_text, {"split_sentences": False})
    for p in doc.paragraphs:
        for s in p.sentences:
            # Every sentence in a chunk must be a sentence of the original.
            assert s.text in readability.sentences(long_text), s.text


def test_the_anchor_is_a_sentence_from_the_paragraph_verbatim():
    """It is extracted, never written. A generated cue could add a claim."""
    for name, text in corpus_texts():
        doc = restructure.build(text)
        for p in doc.paragraphs:
            if p.anchor is None:
                continue
            assert p.anchor in [s.text for s in p.sentences], (name, p.anchor)


def test_no_anchor_for_a_short_paragraph():
    doc = restructure.build("One sentence. Then a second one.")
    assert doc.paragraphs[0].anchor is None


def test_hard_word_flags_skip_proper_nouns():
    flags = [f.word for f in transform.hard_words(
        "Photosynthesis slowed in Iceland during December, and chlorophyll faded.")]
    assert "Photosynthesis" in flags
    assert "chlorophyll" in flags
    assert "Iceland" not in flags
    assert "December" not in flags


def test_hard_word_flags_are_unique_and_explained():
    flags = transform.hard_words(
        "Photosynthesis and photosynthesis and chlorophyll.")
    words = [f.word.lower() for f in flags]
    assert len(words) == len(set(words))
    for f in flags:
        assert f.syllables >= 3
        assert "syllable" in f.reason


# --- the rewrite tier ------------------------------------------------------

def test_the_splitter_keeps_the_connective():
    sentence = ("The apparatus leaked during the second run of the afternoon "
                "session, and the experiment failed completely because "
                "nobody had thought to check the rubber seal before the "
                "session began.")
    out = transform.split_sentences(sentence)
    assert "And the experiment failed" in out
    assert tokens_ci(out) == tokens_ci(sentence)


def test_the_splitter_leaves_short_sentences_alone():
    short = "It leaked, and it failed."
    assert transform.split_sentences(short) == short


def test_the_splitter_refuses_to_strand_a_fragment():
    """A break needs five real words on each side, or it does not happen."""
    sentence = ("A very long introductory clause that goes on and on and on "
                "and keeps going for a while longer still, so yes.")
    out = transform.split_sentences(sentence)
    for s in readability.sentences(out):
        assert len(readability.words(s)) >= 5, s


def test_the_splitter_does_not_strand_a_list_item():
    """The failure the corpus caught: ", and" continuing a list, not a clause.

    "it has two stages: the light-dependent stage, which ..., and the
    light-independent stage, which ..." was split at the last "and", which
    handed a child "And the light-independent stage, which uses the products
    of the first stage to build glucose from carbon dioxide." as a sentence.
    It has no main verb for its subject. Two shape rules now decline the
    break; see `_would_strand_a_fragment`.
    """
    sentence = ("It has two stages: the light-dependent stage, which splits "
                "water molecules and releases oxygen as a waste product, and "
                "the light-independent stage, which uses the products of the "
                "first stage to build glucose from carbon dioxide.")
    assert len(readability.words(sentence)) > 25, "must be over the threshold"
    assert transform.split_sentences(sentence) == sentence

    # The list-item shape alone is enough, with no colon present.
    no_colon = ("The first reading covered the lighter isotopes in some "
                "detail, and the heavier fraction, which nobody had measured "
                "before that afternoon in the laboratory.")
    assert transform.split_sentences(no_colon) == no_colon


def test_the_fragment_guard_still_allows_an_ordinary_clause():
    """It must decline list items without declining everything."""
    sentence = ("The apparatus leaked during the second run of the afternoon "
                "session, and the experiment failed completely because "
                "nobody had thought to check the rubber seal before the "
                "session began.")
    assert len(readability.words(sentence)) >= readability.SPLIT_SENTENCE_WORDS
    assert transform.split_sentences(sentence) != sentence


def test_the_splitter_does_not_break_at_a_subordinator():
    """"because" and "which" produce fragments, so they are not split points."""
    for word in ("because", "which", "although", "while"):
        assert word not in transform.SPLIT_CONNECTIVES


def test_the_splitter_recurses_on_very_long_sentences():
    """One break is not enough for a 50-word sentence; each half is retried."""
    sentence = ("The first clause in this example runs on for a good while "
                "without any obvious place to stop, and the second clause in "
                "this example also runs on for a good while without an "
                "obvious stop, and the third clause in this example runs on "
                "for a good while as well.")
    assert len(readability.words(sentence)) > 45
    out = transform.split_sentences(sentence)
    assert len(readability.sentences(out)) >= 3
    assert tokens_ci(out) == tokens_ci(sentence)


def test_the_splitter_stops_once_the_halves_are_short_enough():
    """Recursion is bounded by the threshold, not by the number of commas.

    A half that already reads at under 25 words is left with its commas
    intact. The goal is sentences a reader can hold, not the shortest
    possible sentences.
    """
    sentence = ("The first clause runs for a good while here, and the second "
                "clause also runs for a good while here, and the third "
                "clause runs for a good while as well.")
    out = transform.split_sentences(sentence)
    sents = readability.sentences(out)
    assert len(sents) == 2
    assert all(len(readability.words(s)) < readability.SPLIT_SENTENCE_WORDS
               for s in sents)


# --- the registry ----------------------------------------------------------

def test_every_operation_validates():
    assert transform.validate_operations() == []


def test_every_operation_declares_a_real_evidence_entry():
    for op in transform.OPERATIONS:
        found = evidence.finding(op.evidence_key)
        assert found.tier in evidence.TIER_ORDER


def test_layout_operations_all_declare_that_they_keep_the_words():
    for op in transform.OPERATIONS:
        if op.tier == transform.LAYOUT:
            assert op.changes_words is False, op.key


def test_the_rewrite_tier_is_off_by_default():
    assert transform.DEFAULTS["split_sentences"] is False
    for op in transform.OPERATIONS:
        if op.tier == transform.REWRITE:
            assert op.default_on is False, op.key


def test_the_spacing_operation_is_first_and_on():
    """The one with real evidence should not be buried below the rest."""
    assert transform.OPERATIONS[0].key == "spacing"
    assert transform.OPERATIONS[0].default_on is True
    assert evidence.finding("letter_spacing").tier == evidence.STRONG


def test_every_operation_has_a_note_that_says_why():
    for op in transform.OPERATIONS:
        assert len(op.note) > 40, op.key
        assert op.note.strip().endswith("."), op.key
