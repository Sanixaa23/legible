"""Proves the meaning check can fail, by handing it a rewrite that lies.

CI runs this. A green suite that cannot go red proves nothing, so the gate
is shown catching the exact failure the project exists to prevent: a
simplification that reads better and says the opposite.

    python tools/gate_demo.py

Exits 0 when the gate caught it, 1 when it did not -- which is the inverse
of the usual arrangement, and deliberate: this script passes by failing.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from legible import facts, restructure, transform  # noqa: E402

CASES = (
    (
        "a reversed claim",
        "Antibiotics do not work against viruses, and they will not shorten a cold.",
        "Antibiotics work against viruses and shorten a cold.",
        facts.NEGATION,
    ),
    (
        "a flattened hedge",
        "The rate may fall below 10 degrees Celsius in rare conditions.",
        "The rate falls below 10 degrees Celsius.",
        facts.MODALITY,
    ),
    (
        "a dropped quantity",
        "Only 3 of the 1,200 samples from Iceland reacted at all.",
        "Some samples reacted.",
        facts.NUMBER,
    ),
    (
        "a dropped unit",
        "The dose was 5 mg per kilogram of body mass.",
        "The dose was 5 per kilogram of body mass.",
        facts.UNIT,
    ),
)


def main() -> int:
    failures = []

    print("The meaning check, shown catching what it is for.")
    print()
    for label, original, damaged, expect in CASES:
        check = facts.retention(original, damaged)
        caught = (not check.ok) and bool(check.lost.get(expect))
        print("%-20s %s" % (label, "caught" if caught else "MISSED"))
        print("   original: %s" % original)
        print("   damaged : %s" % damaged)
        print("   verdict : %s" % check.summary())
        print()
        if not caught:
            failures.append(label)

    # And the pipeline must fall back rather than show a losing rewrite.
    original = CASES[0][1]
    real = transform.split_sentences
    transform.split_sentences = lambda text: CASES[0][2]
    try:
        doc = restructure.build(original, {"split_sentences": True})
        fell_back = doc.text == original and doc.safe and bool(doc.rewrite_rejected)
    finally:
        transform.split_sentences = real

    print("%-20s %s" % ("pipeline fallback",
                        "original kept" if fell_back else "LOSING TEXT SHOWN"))
    if not fell_back:
        failures.append("pipeline fallback")

    print()
    if failures:
        print("FAILED: the gate did not catch %s" % ", ".join(failures))
        return 1
    print("All %d cases caught, and the pipeline kept the original." % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
