# Corpus

Lesson-style text written for this project, so it can be published with it.
Nothing here is copied from a textbook.

Every file is run through the whole pipeline by `tests/test_retention.py`,
which is where the retention number in the README comes from.

| File | Subject | What it is for |
|---|---|---|
| `01_biology_photosynthesis.txt` | Biology | Long sentences with nested clauses; the 61-word opener is the worst case for the clause splitter |
| `02_history_industrial.txt` | History | Dense with dates, populations and a specific statute, so losing a number is easy to see |
| `03_physics_forces.txt` | Physics | Contains a misconception stated and then denied, which a naive simplifier will invert |
| `04_chemistry_reactions.txt` | Chemistry | Definitions that depend on "not" and on contrast pairs |
| `05_geography_water.txt` | Geography | Percentages, fractions and comparatives together |
| `06_adversarial_negation.txt` | Mixed | **Built to break the tool.** Every paragraph's meaning lives in a negation or a modal: "do not work", "will not shorten", "rarely", "risk is not zero", "does not imply", "is not weight" |
| `90_control_already_simple.txt` | Science | **Negative control.** Already short and simple; the tool must not report an improvement it did not make |
| `91_control_two_sentences.txt` | Science | **Negative control.** Too short to restructure; no anchor, no chunking |

The two controls matter as much as the rest. A tool like this is judged by
what it does to text that was already fine.
