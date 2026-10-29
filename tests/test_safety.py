"""Invariants that protect the claims, enforced instead of promised.

Three things could quietly turn this project into the thing it argues
against: the core could start reaching the network, the font setting could
get promoted to something the evidence does not support, and the program
could start describing itself as a treatment. Each has a test here.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "legible")
sys.path.insert(0, os.path.join(ROOT, "src"))

from legible import evidence, facts, restructure, transform  # noqa: E402

# Everything except the optional rewriter must be offline and deterministic.
OFFLINE_MODULES = (
    "readability.py", "facts.py", "transform.py", "restructure.py",
    "evidence.py", "render.py",
)
NETWORK_TOKENS = ("urlopen", "urllib", "requests", "http.client", "socket")
NONDETERMINISM = ("random.", "time.time(", "datetime.now(", "uuid")


def source(name):
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        return f.read()


def modules():
    return sorted(f for f in os.listdir(SRC) if f.endswith(".py"))


# --- offline and deterministic by construction ----------------------------

def test_the_core_never_reaches_the_network():
    for name in OFFLINE_MODULES:
        if not os.path.exists(os.path.join(SRC, name)):
            continue
        text = source(name)
        for token in NETWORK_TOKENS:
            assert token not in text, "%s mentions %s" % (name, token)


def test_the_measurement_path_is_deterministic():
    """A number a teacher is shown must be the same number tomorrow."""
    for name in ("readability.py", "facts.py", "transform.py", "restructure.py"):
        text = source(name)
        for token in NONDETERMINISM:
            assert token not in text, "%s uses %s" % (name, token)


def test_the_same_input_gives_the_same_document():
    text = "A sentence, and another one that runs a good deal longer than it."
    a = restructure.build(text, {"split_sentences": True})
    b = restructure.build(text, {"split_sentences": True})
    assert a.text == b.text
    assert a.delta == b.delta
    assert a.retention.rate == b.retention.rate


def test_only_the_optional_rewriter_may_talk_to_a_model():
    """If ai.py exists, it is the one place a request may be made."""
    path = os.path.join(SRC, "ai.py")
    if not os.path.exists(path):
        return
    text = source("ai.py")
    before, _, after = text.partition("def _request(")
    assert "urlopen" not in before, "a call outside _request opens a connection"
    assert after.count("urlopen") == 1


# --- the claims cannot drift ----------------------------------------------

def test_the_font_setting_stays_labelled_as_unsupported():
    """The test that stops this project becoming what it criticises.

    Every competing tool leads with a dyslexia font. The evidence does not
    support it: no effect on reading rate, accuracy, reading time or
    fixation duration, and a review finding no evidence of improvement. If
    someone promotes this entry to a stronger tier, they have to delete this
    test and explain why in the diff.
    """
    found = evidence.finding("dyslexia_font")
    assert found.tier == evidence.CONTESTED
    assert evidence.tier_rank(found.tier) == len(evidence.TIER_ORDER) - 1


def test_the_setting_with_real_evidence_is_the_one_marked_strong():
    assert evidence.finding("letter_spacing").tier == evidence.STRONG
    strong = [f for f in evidence.FINDINGS if f.tier == evidence.STRONG]
    assert [f.key for f in strong] == ["letter_spacing"], (
        "only the spacing finding has a replicated controlled result; "
        "promoting another one needs a citation, not a preference")


def test_every_finding_carries_a_source_and_a_real_explanation():
    for f in evidence.FINDINGS:
        assert f.source and len(f.source) > 10, f.key
        assert len(f.detail) > 120, "%s: detail too thin to be checkable" % f.key
        assert f.claim.endswith("."), f.key


def test_every_tier_has_a_label_and_a_meaning():
    for tier in evidence.TIER_ORDER:
        assert tier in evidence.TIER_LABEL
        assert tier in evidence.TIER_MEANING
        assert len(evidence.TIER_MEANING[tier]) > 50


def test_nothing_in_the_project_calls_itself_a_treatment():
    """No medical claim anywhere, including in a docstring or the UI."""
    banned = re.compile(
        r"\b(cure[sd]?|treats?\s+dyslexia|therapy|diagnos(?:e|es|is)\s+"
        r"dyslexia|fixes\s+dyslexia)\b", re.IGNORECASE)
    for name in modules():
        text = source(name)
        hit = banned.search(text)
        assert hit is None, "%s says %r" % (name, hit.group(0) if hit else "")


# --- the pipeline fails closed --------------------------------------------

def test_build_never_returns_an_unsafe_document():
    """Whatever happens upstream, what comes out is safe to show."""
    for settings in ({}, {"split_sentences": True},
                     {"split_sentences": True, "chunk": False, "anchor": False}):
        for text in ("", "   ", "One.", "No numbers here at all.",
                     "It may not exceed 4.5 kg in Iceland, says Dr. Smith."):
            doc = restructure.build(text, settings)
            assert doc.safe, (settings, text, doc.retention.summary())


def test_a_rejected_rewrite_leaves_the_original_text():
    original = "The rate may not rise above 10 degrees."
    real = transform.split_sentences
    transform.split_sentences = lambda t: "The rate rises above 10 degrees."
    try:
        doc = restructure.build(original, {"split_sentences": True})
        assert doc.text == original
        assert doc.safe
        assert doc.rewrite_rejected
    finally:
        transform.split_sentences = real


def test_the_layout_tier_does_not_reach_the_rewrite_tier():
    """apply_layout must not be able to change a word, even by accident."""
    text = source("transform.py")
    body = text.partition("def apply_layout(")[2].partition("\ndef ")[0]
    assert "split_sentences" not in body, (
        "apply_layout calls the rewrite tier; the layout promise is gone")


def test_the_kinds_we_watch_all_have_a_stated_reason():
    for kind in facts.KINDS:
        assert kind in facts.KIND_WHY


def test_an_unknown_evidence_key_fails_loudly():
    try:
        evidence.finding("no_such_claim")
    except KeyError as exc:
        assert "no evidence entry" in str(exc)
    else:
        raise AssertionError("an unknown claim was accepted")
