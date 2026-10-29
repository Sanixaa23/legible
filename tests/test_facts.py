"""Tests for the check that decides whether a rewrite may be shown.

Two directions matter equally. It must catch a real loss, or the safety
claim is theatre. And it must not report a loss that did not happen, or
every rewrite gets rejected and the tool does nothing while appearing to
work.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from legible import facts as F  # noqa: E402


def kinds(text):
    out = {}
    for f in F.extract(text):
        out.setdefault(f.kind, []).append(f.value)
    return out


# --- what gets collected --------------------------------------------------

def test_numbers_in_every_written_form():
    got = kinds("It took 3 days, 4.5 hours, 1,200 steps, .5 litres and 12%.")
    assert set(got[F.NUMBER]) >= {"3", "4.5", "1200", "0.5", "12%"}


def test_written_out_numbers_count_too():
    assert "three" in kinds("It took three days.")[F.NUMBER]
    assert "half" in kinds("Half of the class arrived.")[F.NUMBER]


def test_negations_including_contractions():
    text = "It does not work and it doesn't help; nobody knew, nor cared."
    got = kinds(text)
    # "doesn't" collapses to the negation it carries; see NEGATION_CANON.
    assert set(got[F.NEGATION]) >= {"not", "nobody", "nor"}
    surfaces = [f.surface for f in F.extract(text) if f.kind == F.NEGATION]
    assert "doesn't" in surfaces, "the original wording must still be shown"


def test_modality_words():
    got = kinds("It may rarely happen, and only some cases are always fatal.")
    assert set(got[F.MODALITY]) >= {"may", "rarely", "only", "some", "always"}


def test_units_count_only_after_a_number():
    with_number = kinds("The mass was 5 kg.")
    assert "kg" in with_number.get(F.UNIT, [])
    alone = kinds("Mass in kg is what we record.")
    assert "kg" not in alone.get(F.UNIT, [])


def test_names_are_collected_mid_sentence_not_at_the_start():
    got = kinds("The reaction in Iceland stopped.")
    assert "iceland" in got[F.NAME]
    start = kinds("Iceland is cold.")
    assert F.NAME not in start or "iceland" not in start[F.NAME]


def test_acronyms_count_as_names_wherever_they_sit():
    assert "dna" in kinds("DNA carries it.")[F.NAME]


# --- normalisation --------------------------------------------------------

def test_number_formatting_changes_are_not_losses():
    assert F.retention("We counted 1,200 cells.", "We counted 1200 cells.").ok
    assert F.retention("It was 3.50 metres.", "It was 3.5 metres.").ok


def test_apostrophe_and_case_changes_are_not_losses():
    assert F.retention("Don't stop.", "Dont stop.").ok
    assert F.retention("it does not work.", "It does not work.").ok


def test_expanding_a_contraction_is_not_a_loss():
    """"doesn't" is "does not". Rejecting that expansion would be wrong.

    Found while writing these tests: a contracted auxiliary normalised to
    its own token, so the expansion lost it and the rewrite was refused. The
    contractions now collapse to the negation they carry.
    """
    assert F.retention("It doesn't work.", "It does not work.").ok
    assert F.retention("You cannot stop.", "You can not stop.").ok
    assert F.retention("It won't help.", "It will not help.").ok


def test_the_collapse_does_not_reach_further_than_contractions():
    """"nobody" carries more than a negation, so it must not fold into "not"."""
    check = F.retention("Nobody arrived at the hall.", "Not everyone arrived at the hall.")
    assert not check.ok
    assert check.lost[F.NEGATION] == ["Nobody"]


def test_a_name_moved_to_the_start_of_a_sentence_is_not_a_loss():
    """The bug this fixed: splitting a sentence moved a name to the front.

    "and Dr. Smith found" becomes "Dr. Smith found", where the strict name
    rule no longer sees a name, and the check reported a deletion that never
    happened. Names are collected strictly on the original and leniently on
    the rewrite for exactly this reason.
    """
    original = "The sample froze, and Dr. Smith recorded it in Iceland."
    split = "The sample froze. And Dr. Smith recorded it in Iceland."
    assert F.retention(original, split).ok


# --- what must be caught --------------------------------------------------

def test_a_dropped_negation_is_caught():
    check = F.retention("Antibiotics do not work against viruses.",
                        "Antibiotics work against viruses.")
    assert not check.ok
    assert check.lost[F.NEGATION] == ["not"]


def test_a_flattened_modal_is_caught():
    check = F.retention("The rate may fall below 10 degrees.",
                        "The rate falls below 10 degrees.")
    assert not check.ok
    assert "may" in check.lost[F.MODALITY]


def test_a_dropped_number_is_caught():
    check = F.retention("3 of the 40 samples reacted.",
                        "Some of the samples reacted.")
    assert not check.ok
    assert set(check.lost[F.NUMBER]) >= {"3", "40"}


def test_a_dropped_unit_is_caught():
    check = F.retention("It was 5 kg.", "It was 5.")
    assert not check.ok
    assert check.lost[F.UNIT] == ["kg"]


def test_losing_one_of_two_identical_facts_is_caught():
    """A multiset, not a set: said twice and now said once is a loss."""
    check = F.retention("It is not cold and it is not wet.",
                        "It is not cold and it is wet.")
    assert not check.ok
    assert check.lost[F.NEGATION] == ["not"]


def test_added_material_is_not_a_loss():
    """We check for deletion, not for addition. Addition is the LLM's problem."""
    assert F.retention("It was 5 kg.", "It was 5 kg, roughly, in total.").ok


# --- the report ------------------------------------------------------------

def test_rate_and_summary_agree():
    check = F.retention("It does not work in 3 cases.", "It works in cases.")
    assert check.lost_count == 2            # the negation and the number
    assert 0.0 <= check.rate < 1.0
    assert "lost" in check.summary()


def test_empty_text_is_safe_and_rated_one():
    check = F.retention("", "")
    assert check.ok and check.rate == 1.0 and check.total == 0


def test_every_kind_has_a_reason_a_teacher_can_read():
    for kind in F.KINDS:
        assert F.KIND_WHY[kind].endswith(".")
        assert len(F.KIND_WHY[kind]) > 30
