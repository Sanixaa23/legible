"""What we actually know about each reading support, and how well.

Every tool in this space ships the same headline feature: a dyslexia font.
The research does not support it. The main controlled test of OpenDyslexic
found no improvement in reading rate or accuracy and no reader preference,
an eye-tracking study found no improvement in reading time or fixation
duration, and a review of the area concluded there is no evidence that these
fonts improve reading performance.

Meanwhile the one manipulation with a strong result -- letter spacing -- is
the one almost nobody surfaces as a setting.

So every transformation in this program carries its evidence tier, and the
reading view shows it. A teacher turning something on can see whether they
are applying a finding, a convention, or a preference. That is the honest
version of this product, and it is also the interesting one.

Nothing here is medical advice, and a tier is not a promise about any one
reader: Zorzi et al. found the benefit was largest for the children who were
worst at identifying letters, which means it was not uniform.
"""
from __future__ import annotations

from typing import Dict, NamedTuple, Tuple

# Tiers, strongest first. The string values are what the UI prints.
STRONG = "strong"
MODERATE = "moderate"
CONVENTION = "convention"
PREFERENCE = "preference"
CONTESTED = "contested"

TIER_ORDER: Tuple[str, ...] = (STRONG, MODERATE, CONVENTION, PREFERENCE, CONTESTED)

TIER_LABEL: Dict[str, str] = {
    STRONG: "Measured effect",
    MODERATE: "Some evidence",
    CONVENTION: "Practitioner convention",
    PREFERENCE: "Reader preference",
    CONTESTED: "No measured benefit",
}

TIER_MEANING: Dict[str, str] = {
    STRONG: "A controlled study measured this effect on dyslexic readers, "
            "with at least one replication.",
    MODERATE: "A controlled study found an effect, but replication is thin "
              "or the population was not dyslexic readers specifically.",
    CONVENTION: "Published guidance recommends it. No study tests the "
                "specific threshold, so the number is a convention.",
    PREFERENCE: "No measured reading benefit. Offered because readers ask "
                "for it, and a reader's own comfort is a real reason.",
    CONTESTED: "Tested and found not to improve reading. Kept available, and "
               "labelled, because removing a reader's choice is worse.",
}


class Finding(NamedTuple):
    """One claim, its tier, and what it rests on."""

    key: str
    claim: str
    tier: str
    source: str
    detail: str


FINDINGS: Tuple[Finding, ...] = (
    Finding(
        key="letter_spacing",
        claim="Extra letter spacing improves reading in dyslexia.",
        tier=STRONG,
        source="Zorzi et al. (2012), PNAS 109(28):11455-11459",
        detail="74 children aged 8-14 diagnosed with developmental dyslexia, "
               "Italian and French. Reading accuracy roughly doubled and speed "
               "rose about 20% with extra-large spacing, with no training. The "
               "authors attribute it to crowding. A control comparison found "
               "the benefit in dyslexic children and not in younger typical "
               "readers; the finding was challenged by Skottun and Skoyles, "
               "and the authors' reply cites a Spanish replication. The "
               "benefit was largest for the children who were worst at "
               "identifying letters, so it is not uniform across readers.",
    ),
    Finding(
        key="line_length",
        claim="Lines of 60-70 characters are easier to track.",
        tier=CONVENTION,
        source="British Dyslexia Association, Dyslexia Style Guide",
        detail="The guide recommends 60-70 characters per line. We found no "
               "study testing that threshold against dyslexic readers, and a "
               "W3C working-group discussion notes that in one comparison it "
               "was non-dyslexic readers who benefited most from narrow "
               "44-character columns. Shorter lines plausibly reduce visual "
               "tracking and working-memory load; the specific number is "
               "convention, not a measurement.",
    ),
    Finding(
        key="sentence_length",
        claim="Shorter sentences are easier to comprehend.",
        tier=CONVENTION,
        source="BDA Dyslexia Style Guide; Dyslexia Scotland",
        detail="The BDA asks for short, simple sentences without giving a "
               "number. Dyslexia Scotland suggests up to 25 words. We use 20 "
               "as the flag threshold and 25 as the split threshold, and we "
               "report the sentence-length distribution rather than claiming "
               "a comprehension gain.",
    ),
    Finding(
        key="paragraph_length",
        claim="Short paragraphs with one idea each are easier to hold.",
        tier=CONVENTION,
        source="Plain-language guidance, widely repeated",
        detail="Roughly 50 words per paragraph is the figure usually cited. "
               "This one is the weakest kind of claim in this file: "
               "ubiquitous guidance with no single study behind it. It is on "
               "by default because the cost of being wrong is a shorter "
               "paragraph.",
    ),
    Finding(
        key="anchor_sentence",
        claim="A short cue before a paragraph helps a reader resume.",
        tier=MODERATE,
        source="Advance-organiser and signalling research, education literature",
        detail="Signalling and advance organisers have a long literature in "
               "instructional design, with measured comprehension effects in "
               "general populations -- not specifically dyslexic or ADHD "
               "readers. We extract the cue from the paragraph's own sentences "
               "rather than writing a new one, so the cue cannot introduce a "
               "claim the text does not make.",
    ),
    Finding(
        key="dyslexia_font",
        claim="A specialised dyslexia font improves reading.",
        tier=CONTESTED,
        source="Rello & Baeza-Yates (2013); Wery & Diliberto (2016); "
               "Kuster et al. (2018) review",
        detail="The single-subject study found no improvement in reading rate "
               "or accuracy for any participant, and none of the children "
               "preferred the font. The eye-tracking study found no effect on "
               "reading time or fixation duration. The review concluded there "
               "is currently no evidence that these fonts improve reading "
               "performance. One 2022 conference abstract reports a "
               "comprehension gain in adults; it is preliminary and we do not "
               "lean on it. The font stays available and stays labelled -- and "
               "part of why it is popular may simply be that it carries wide "
               "letter spacing, which is the thing that does work.",
    ),
    Finding(
        key="colour_overlay",
        claim="A coloured background or overlay reduces visual stress.",
        tier=PREFERENCE,
        source="Reader preference; no reliable reading-rate effect",
        detail="Tinted overlays have a long history and a poor evidence "
               "record for reading performance. Some readers report real "
               "comfort, which is worth offering. We present it as comfort, "
               "not as a treatment, and we never make colour the only signal "
               "for anything.",
    ),
)

BY_KEY: Dict[str, Finding] = {f.key: f for f in FINDINGS}


def finding(key: str) -> Finding:
    """Look a claim up, loudly. A transformation with no entry is a bug."""
    try:
        return BY_KEY[key]
    except KeyError:
        raise KeyError(
            "no evidence entry for %r: every transformation must declare one, "
            "even if the tier is %r" % (key, PREFERENCE)
        )


def tier_rank(tier: str) -> int:
    """For sorting. Lower is stronger."""
    return TIER_ORDER.index(tier)
