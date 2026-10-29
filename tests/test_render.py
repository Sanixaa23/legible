"""Tests for the reading view and the server.

These also exist because nothing else imported `render.py` or `server.py`:
the suite was green while the rendering module had a syntax error in it. A
module no test imports is a module nobody is checking.
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from legible import evidence, render, restructure, server, transform  # noqa: E402

SAMPLE_DOC = restructure.build(render.SAMPLE, {"split_sentences": True})


def test_the_modules_import_and_render():
    page = render.page(SAMPLE_DOC, render.SAMPLE)
    assert page.startswith("<!doctype html>")
    assert page.rstrip().endswith("</html>")
    assert "<title>legible</title>" in page


def test_the_empty_state_renders_without_a_document():
    page = render.page(None, "")
    assert "Paste a lesson" in page
    assert "Meaning check" not in page


def test_the_page_loads_nothing_from_the_network():
    """Offline is a feature, and a feature can regress."""
    for page in (render.page(SAMPLE_DOC, render.SAMPLE),
                 render.page(None, ""),
                 server._evidence_page()):
        found = re.findall(r"https?://[^\s\"'<>)]+", page)
        assert found == [], found
        assert "<script src" not in page
        assert "<link" not in page


def test_hostile_text_is_escaped_everywhere_it_appears():
    nasty = ('<script>alert(1)</script> "quoted" & ampersand, and a very long '
             "sentence about 5 kg of sodium that keeps going for a while so "
             "that it is segmented into clause lines as well.")
    doc = restructure.build(nasty, {"split_sentences": True})
    page = render.page(doc, nasty)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_the_meaning_banner_states_the_result_in_words():
    """Never colour alone: the banner has to say it."""
    page = render.page(SAMPLE_DOC, render.SAMPLE)
    assert "Meaning check: Nothing lost." in page
    assert "still present" in page


def test_a_rejected_rewrite_is_explained_on_the_page():
    original = "The rate may not rise above 10 degrees."
    real = transform.split_sentences
    transform.split_sentences = lambda t: "The rate rises above 10 degrees."
    try:
        doc = restructure.build(original, {"split_sentences": True})
        page = render.page(doc, original)
    finally:
        transform.split_sentences = real
    assert "rejected" in page
    assert "a harder sentence beats a changed claim" in page


def test_every_tier_badge_carries_a_word_not_just_a_colour():
    page = render.page(SAMPLE_DOC, render.SAMPLE)
    for tier in evidence.TIER_ORDER:
        marker = 'class="tier tier-%s"' % tier
        if marker not in page:
            continue
        idx = page.index(marker)
        chunk = page[idx:idx + 200]
        assert render.TIER_ABBR[tier] in chunk, tier


def test_the_contested_tier_is_shown_on_the_page_not_hidden():
    """The font note has to be visible, not buried in a details element."""
    page = render.page(SAMPLE_DOC, render.SAMPLE)
    assert 'tier-contested' in page
    assert "We do not ship a" in page


def test_the_stats_panel_describes_movement_in_words():
    page = render.page(SAMPLE_DOC, render.SAMPLE)
    for word in ("improved", "unchanged"):
        assert word in page


def test_the_layout_tier_alone_still_moves_a_number():
    """The regression this panel was rebuilt for.

    With only layout settings on, no word changes, so every sentence
    statistic is identical before and after and the panel read "unchanged"
    across the board while the screen had visibly changed. The longest
    unbroken line is the figure that does move.
    """
    doc = restructure.build(render.SAMPLE, {"split_sentences": False})
    assert doc.text == doc.original
    assert doc.after.mean_sentence_words == doc.before.mean_sentence_words
    assert doc.longest_line_words < doc.before.longest_sentence_words
    assert len(doc.paragraphs) >= doc.before.paragraphs


def test_the_reading_view_marks_flagged_words():
    page = render.page(SAMPLE_DOC, render.SAMPLE)
    assert 'class="hard"' in page
    assert "Words to check with the class" in page


def test_the_original_text_is_always_available_on_the_page():
    page = render.page(SAMPLE_DOC, render.SAMPLE)
    assert "The original text, unchanged" in page


# --- the server, without a socket -----------------------------------------

def test_the_form_reader_treats_an_absent_checkbox_as_off():
    text, settings = server._read_form({"text": ["hello"]})
    assert text == "hello"
    assert all(v is False for v in settings.values())


def test_the_form_reader_loads_the_sample_with_the_defaults():
    text, settings = server._read_form({"sample": ["1"]})
    assert text == render.SAMPLE
    assert settings == dict(transform.DEFAULTS)


def test_the_api_payload_round_trips_as_json():
    payload = server.doc_json(SAMPLE_DOC)
    encoded = json.dumps(payload)
    back = json.loads(encoded)
    assert back["safe"] is True
    assert back["retention"]["rate"] == 1.0
    assert back["blocks"] and back["blocks"][0]["sentences"]


def test_the_evidence_api_lists_every_finding_and_operation():
    payload = server._evidence_json()
    assert len(payload["findings"]) == len(evidence.FINDINGS)
    assert len(payload["operations"]) == len(transform.OPERATIONS)
    for op in payload["operations"]:
        assert op["tier"] in evidence.TIER_ORDER


def test_the_server_binds_to_localhost_by_default():
    """Lesson text is a child's work. It does not go on the network by accident."""
    source = open(os.path.join(ROOT, "src", "legible", "server.py"),
                  encoding="utf-8").read()
    assert 'host: str = "127.0.0.1"' in source
    assert 'default="127.0.0.1"' in source


def test_the_server_never_logs_the_pasted_text():
    source = open(os.path.join(ROOT, "src", "legible", "server.py"),
                  encoding="utf-8").read()
    body = source.partition("def log_message(")[2].partition("\n    def ")[0]
    # Drop the docstring: it says the word "text" while stating the rule.
    code = body.partition('"""')[2].partition('"""')[2]
    for token in ("rfile", "raw", "body", "args"):
        assert token not in code, "log_message touches %s" % token
    assert "self.path.split" in code, "the path should still be logged"
