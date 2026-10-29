"""Measurement tests, including the words the syllable counter gets wrong.

A heuristic with a documented error list is a tool. A heuristic presented as
exact is a liability, so the words it misses are written down here rather
than discovered by a teacher.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from legible import readability as r  # noqa: E402

# Words the counter gets right, with the count a dictionary gives.
CORRECT = {
    "cat": 1, "the": 1, "queue": 1, "strength": 1,
    "table": 2, "simple": 2, "water": 2, "little": 2,
    "energy": 3, "chlorophyll": 3, "important": 3,
    "photosynthesis": 5,
}

# Words it gets wrong, and by how much. Listed so the error is known and so
# a change to the heuristic has to come here and argue with the list.
KNOWN_WRONG = {
    "idea": (3, 2),         # id-e-a; adjacent vowels count as one run
    "being": (2, 1),        # be-ing; the silent-e rule eats it
    "equilibrium": (5, 4),  # e-qui-lib-ri-um; "iu" is one run to us
}


def test_counts_the_words_it_claims_to():
    for word, expected in CORRECT.items():
        assert r.syllables(word) == expected, word


def test_the_known_errors_are_still_exactly_these():
    for word, (truth, ours) in KNOWN_WRONG.items():
        assert r.syllables(word) == ours, (
            "%s now counts %d, not the documented %d -- update KNOWN_WRONG"
            % (word, r.syllables(word), ours))
        assert truth != ours


def test_syllables_never_returns_zero_for_a_word():
    for word in ("a", "I", "rhythm", "strengths", "xyz"):
        assert r.syllables(word) >= 1, word


def test_a_token_with_no_letters_has_no_syllables():
    """Not an edge case to paper over: the metrics must not count punctuation."""
    for token in ("'", "--", "42", ""):
        assert r.syllables(token) == 0, token


def test_sentence_split_keeps_decimals_together():
    out = r.sentences("The mass was 3.5 kg. It fell.")
    assert out == ["The mass was 3.5 kg.", "It fell."]


def test_sentence_split_handles_abbreviations_and_initials():
    assert r.sentences("Dr. Smith arrived. He left.") == [
        "Dr. Smith arrived.", "He left."]
    assert r.sentences("See fig. 4 for detail. Then stop.") == [
        "See fig. 4 for detail.", "Then stop."]
    assert r.sentences("J. R. Firth wrote it. Nobody read it.") == [
        "J. R. Firth wrote it.", "Nobody read it."]


def test_sentence_split_handles_question_and_exclamation():
    assert r.sentences("Why? Because! Yes.") == ["Why?", "Because!", "Yes."]


def test_sentence_split_keeps_a_sentence_without_final_punctuation():
    assert r.sentences("No full stop here") == ["No full stop here"]


def test_paragraphs_split_on_blank_lines_only():
    text = "One line\nstill the same paragraph.\n\nA second one."
    assert len(r.paragraphs(text)) == 2
    assert r.paragraphs("a\r\n\r\nb") == ["a", "b"]


def test_measure_is_deterministic():
    text = "A sentence here. And another one, slightly longer than the first."
    assert r.measure(text) == r.measure(text)


def test_measure_of_empty_text_does_not_divide_by_zero():
    m = r.measure("")
    assert m.words == 0 and m.sentences == 0
    assert m.flesch_reading_ease == 0.0
    assert m.flesch_kincaid_grade == 0.0


def test_short_simple_text_scores_easier_than_long_dense_text():
    simple = "Ice is water. It is cold. It melts."
    dense = ("The thermodynamic equilibrium of the crystalline phase is "
             "contingent upon the ambient temperature exceeding the "
             "characteristic transition threshold of the substance.")
    assert (r.measure(simple).flesch_reading_ease
            > r.measure(dense).flesch_reading_ease)


def test_long_sentence_and_paragraph_counts_use_the_documented_thresholds():
    sentence = " ".join(["word"] * r.LONG_SENTENCE_WORDS) + "."
    assert r.measure(sentence).long_sentences == 1
    shorter = " ".join(["word"] * (r.LONG_SENTENCE_WORDS - 1)) + "."
    assert r.measure(shorter).long_sentences == 0


def test_splitting_a_sentence_raises_the_ease_score():
    """What this tool actually does: add a sentence boundary, delete nothing."""
    before = r.measure("The apparatus leaked, and the experiment failed "
                       "because nobody had checked the seal beforehand.")
    after = r.measure("The apparatus leaked. And the experiment failed "
                      "because nobody had checked the seal beforehand.")
    d = r.delta(before, after)
    assert d["flesch_reading_ease"] > 0
    assert d["mean_sentence_words"] < 0
    assert d["words"] == 0, "splitting must not change the word count"


def test_deleting_words_can_lower_the_ease_score():
    """A finding, kept as a test, because it decides what we put on screen.

    Flesch reading ease punishes syllables per word as hard as it punishes
    words per sentence. Deleting short function words -- which is most of
    what "simplifying" prose looks like -- shortens the sentence and raises
    the syllable density at the same time, and the score can fall even
    though the text got easier to read.

    Two consequences, both load-bearing:

    1. Ease is reported as a secondary number. The headline figures are
       mean sentence length and the count of over-long sentences, because
       those are what the transformations actually change.
    2. It is one more reason the layout tier deletes nothing. A tool whose
       own metric cannot tell whether a deletion helped should not be
       deleting.
    """
    before = r.measure("The experiment, which had been prepared in advance, "
                       "failed because the apparatus leaked.")
    after = r.measure("The experiment failed. The apparatus leaked.")
    d = r.delta(before, after)
    assert d["mean_sentence_words"] < 0, "sentences did get shorter"
    assert d["flesch_reading_ease"] < 0, "and the ease score still fell"


def test_distribution_buckets_add_up():
    lengths = [3, 12, 22, 40, 5]
    buckets = r.distribution(lengths)
    assert sum(buckets.values()) == len(lengths)
    assert buckets["31+"] == 1
