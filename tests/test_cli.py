"""Tests for the command line, and for the one thing it is a gate over.

This file exists because of a defect found after the first public push: the
README printed a `legible check damaged.txt` transcript ending in MEANING
CHANGED, and no input file could ever produce it. `check` ran our own
pipeline, our pipeline discards a losing rewrite before returning, so
`doc.safe` was always true and the failing branch was unreachable.

The lesson is the one already in the README as finding 6, arriving a second
time in a different shape: nothing imported `cli.py`, so nothing noticed
that one of its two outcomes could not happen. A branch no test reaches is
a branch nobody is checking.

So two things are pinned here. That `--against` can fail, because that is
the gate. And that plain `check` cannot, because that is a property of the
pipeline worth knowing rather than a bug to fix.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from legible import cli  # noqa: E402

HONEST = "Antibiotics do not work against viruses, and they will not shorten a cold.\n"
LYING = "Antibiotics work against viruses and shorten a cold.\n"


def _run(argv):
    parser = cli.build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


# --- the gate -------------------------------------------------------------

def test_against_exits_one_when_the_rewrite_lost_a_negation(tmp_path, capsys):
    """The transcript the README prints has to be reproducible."""
    original = _write(tmp_path, "good.txt", HONEST)
    damaged = _write(tmp_path, "bad.txt", LYING)

    code = _run(["check", original, "--against", damaged])

    err = capsys.readouterr().err
    assert code == 1
    assert "MEANING CHANGED" in err
    assert "lost negation" in err
    assert "not" in err


def test_against_exits_zero_when_the_rewrite_kept_everything(tmp_path, capsys):
    original = _write(tmp_path, "good.txt", HONEST)
    faithful = _write(
        tmp_path, "ok.txt",
        "Antibiotics do not work against viruses. And they will not shorten a cold.\n")

    code = _run(["check", original, "--against", faithful])

    assert code == 0
    assert "kept" in capsys.readouterr().out


def test_against_names_both_files_so_a_log_says_which_rewrite_failed(tmp_path, capsys):
    original = _write(tmp_path, "good.txt", HONEST)
    damaged = _write(tmp_path, "bad.txt", LYING)

    _run(["check", original, "--against", damaged])

    err = capsys.readouterr().err
    assert "good.txt" in err and "bad.txt" in err
    assert "->" in err


def test_a_flattened_hedge_fails_the_gate_too(tmp_path, capsys):
    """Not only negations: a hedge becoming a fact is the other failure."""
    original = _write(tmp_path, "a.txt",
                      "The rate may fall below 10 degrees in rare conditions.\n")
    damaged = _write(tmp_path, "b.txt", "The rate falls below 10 degrees.\n")

    code = _run(["check", original, "--against", damaged])

    assert code == 1
    assert "lost modality" in capsys.readouterr().err


def test_the_quiet_flag_silences_a_pass_but_never_a_failure(tmp_path, capsys):
    original = _write(tmp_path, "good.txt", HONEST)
    damaged = _write(tmp_path, "bad.txt", LYING)

    assert _run(["check", original, "-q"]) == 0
    assert capsys.readouterr().out == ""

    assert _run(["check", original, "--against", damaged, "-q"]) == 1
    assert "MEANING CHANGED" in capsys.readouterr().err


# --- the property that made the README wrong ------------------------------

def test_our_own_output_cannot_fail_the_check(tmp_path, capsys):
    """Why `--against` had to exist.

    Every corpus file, through both tiers, must come back 0. Not because
    the check is weak -- `--against` above shows it is not -- but because
    the pipeline fails closed upstream of it. If this ever returns 1, the
    fallback in restructure.build has broken, which is the one bug this
    program cannot have.
    """
    corpus = os.path.join(ROOT, "corpus")
    names = sorted(n for n in os.listdir(corpus) if n.endswith(".txt"))
    assert names, "the corpus is missing"

    for name in names:
        path = os.path.join(corpus, name)
        assert _run(["check", path, "-q"]) == 0, name
        assert _run(["check", path, "--rewrite", "-q"]) == 0, name

    assert capsys.readouterr().err == ""


# --- the rest of the surface ---------------------------------------------

def test_an_unknown_setting_name_lists_the_real_ones(tmp_path):
    path = _write(tmp_path, "a.txt", HONEST)
    try:
        _run(["read", path, "--off", "nonsense"])
    except SystemExit as exc:
        assert "No such setting: nonsense" in str(exc)
        assert "anchor" in str(exc), "the message should list what is valid"
    else:
        raise AssertionError("an unknown setting should not pass silently")


def test_every_subcommand_runs_on_a_real_file(tmp_path, capsys):
    """A smoke test, because nothing imported this module before."""
    path = _write(tmp_path, "a.txt", HONEST)
    for argv in (["read", path], ["read", path, "--json"], ["read", path, "--html"],
                 ["stats", path], ["check", path], ["evidence"]):
        assert _run(argv) == 0, argv
        assert capsys.readouterr().out.strip(), argv
