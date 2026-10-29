"""The reading view.

Design rules this file keeps, each for a reason:

- **Nothing is signalled by colour alone.** Every evidence tier has a word
  next to it, every flagged word has a dotted underline as well as a tint,
  and the meaning check says "all 27 kept", not just turning green.
- **The typography controls are instant.** Spacing, line width and theme are
  CSS variables set on the page, so a reader drags a slider and sees the
  effect with no round trip. Only the text analysis needs the server.
- **One job per control, labelled with its evidence.** The setting with a
  measured effect sits at the top; the one with none sits at the bottom and
  says so. A teacher can see which is which without reading a paper.
- **It works with no network.** The CSS is inline, the fonts are the
  reader's own, and there is no script tag doing anything the page needs to
  be readable. Turn JavaScript off and the reading view still renders; the
  sliders stop working, which is the right thing to lose.

The HTML is assembled by hand rather than with a template engine so that
`pyproject.toml` can keep an empty dependency list.
"""
from __future__ import annotations

import html
from typing import Dict, List, Optional

from . import evidence, facts, readability, restructure, transform

TIER_ABBR = {
    evidence.STRONG: "evidence",
    evidence.MODERATE: "some evidence",
    evidence.CONVENTION: "convention",
    evidence.PREFERENCE: "preference",
    evidence.CONTESTED: "no evidence",
}

SAMPLE = (
    "Photosynthesis is the process by which green plants, algae and some "
    "bacteria convert light energy into the chemical energy stored in "
    "sugars, and because the reaction depends on a pigment called "
    "chlorophyll, which absorbs light most strongly in the blue and the red "
    "parts of the visible spectrum while reflecting green, the leaves of "
    "most plants appear green to us.\n\n"
    "Photosynthesis does not continue at the same rate in all conditions. "
    "The rate may fall sharply below 10 degrees Celsius, and it rarely "
    "increases further once light intensity passes a certain point, because "
    "some other factor, usually the supply of carbon dioxide, has become "
    "the limiting one."
)


def e(text: object) -> str:
    return html.escape(str(text), quote=True)


# --- the page -------------------------------------------------------------

def page(doc: Optional[restructure.Document] = None,
         raw_text: str = "",
         title: str = "legible") -> str:
    """The whole single-page app, server-rendered."""
    body = _reading_view(doc) if doc else _empty_state()
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>%s</title>" % e(title),
        '<meta name="description" content="Restructures lesson material for '
        'dyslexic and ADHD readers, and proves it kept the meaning.">',
        "<style>%s</style>" % _css(),
        "</head>",
        '<body data-theme="auto">',
        _skip_link(),
        _header(),
        '<main id="main">',
        _form(raw_text, doc),
        body,
        "</main>",
        _footer(),
        "<script>%s</script>" % _js(),
        "</body>",
        "</html>",
    ])


def _skip_link() -> str:
    return '<a class="skip" href="#reading">Skip to the restructured text</a>'


def _header() -> str:
    return (
        "<header>"
        '<h1>legible</h1>'
        "<p class=\"lede\">Restructures lesson material for dyslexic and ADHD "
        "readers &mdash; and checks that it kept every number, name, "
        "negation and hedge the original had.</p>"
        "</header>"
    )


def _empty_state() -> str:
    return (
        '<section id="reading" class="card empty">'
        "<h2>Paste a lesson, or load the sample</h2>"
        "<p>Nothing is uploaded anywhere. The text is restructured on this "
        "machine, by code you can read, and no language model is involved "
        "unless you ask for one.</p>"
        "<ul class=\"plain\">"
        "<li><strong>What it changes:</strong> spacing, line width, "
        "paragraph length, clause layout, and which sentence you see first.</li>"
        "<li><strong>What it never changes by default:</strong> the words. "
        "The default path cannot delete one.</li>"
        "</ul>"
        "</section>"
    )


# --- the form -------------------------------------------------------------

def _form(raw_text: str, doc: Optional[restructure.Document]) -> str:
    settings = doc.settings if doc else dict(transform.DEFAULTS)
    rows = []
    for op in transform.OPERATIONS:
        found = evidence.finding(op.evidence_key)
        checked = " checked" if settings.get(op.key, op.default_on) else ""
        rows.append(
            '<li class="op">'
            '<label><input type="checkbox" name="op_%s" value="1"%s> '
            '<span class="op-title">%s</span></label>'
            '<span class="tier tier-%s">%s</span>'
            '<details><summary>Why, and what it rests on</summary>'
            '<p class="note">%s</p>'
            '<p class="src"><strong>%s</strong> &mdash; %s</p>'
            '<p class="detail">%s</p></details>'
            "</li>" % (
                e(op.key), checked, e(op.title),
                e(found.tier), e(TIER_ABBR[found.tier]),
                e(op.note), e(evidence.TIER_LABEL[found.tier]),
                e(found.source), e(found.detail),
            )
        )

    return "".join([
        '<form method="post" action="/" class="card">',
        '<h2><label for="text">The lesson text</label></h2>',
        '<textarea id="text" name="text" rows="8" spellcheck="false" '
        'placeholder="Paste a paragraph of a lesson here.">%s</textarea>'
        % e(raw_text),
        '<div class="actions">',
        '<button type="submit" class="primary">Restructure</button>',
        '<button type="submit" name="sample" value="1">Load the sample</button>',
        "</div>",
        '<h2 class="ops-head">What to apply</h2>',
        '<p class="hint">Each one carries how well it is supported. The top '
        'setting is the only one with a replicated controlled result.</p>',
        '<ul class="ops">', "".join(rows), "</ul>",
        _typography_controls(),
        "</form>",
    ])


def _typography_controls() -> str:
    """Instant, client-side, and honest about the font."""
    return "".join([
        '<h2 class="ops-head">How it looks</h2>',
        '<p class="hint">These apply as you drag them. Nothing is sent '
        'anywhere.</p>',
        '<div class="typo">',
        _slider("letter", "Letter spacing", 0, 16, 6,
                "0.01em steps. The one with a measured effect.", evidence.STRONG),
        _slider("line", "Line height", 14, 26, 19,
                "0.1 steps, from 1.4 to 2.6.", evidence.CONVENTION),
        _slider("width", "Line width", 40, 90, 66,
                "Characters per line. 60-70 is the usual advice.",
                evidence.CONVENTION),
        '<div class="field">',
        '<label for="font">Typeface</label>',
        '<select id="font" name="font">',
        '<option value="sans">System sans (default)</option>',
        '<option value="serif">System serif</option>',
        '<option value="wide">Wide sans, extra spacing</option>',
        "</select>",
        '<p class="hint">We do not ship a "dyslexia font". The controlled '
        'tests of one found no gain in reading rate, accuracy, reading time '
        'or fixation duration. Part of why they feel better may simply be '
        'their wide letter spacing &mdash; which is the slider above, and it '
        'is the thing that works. <span class="tier tier-contested">'
        'no evidence</span></p>',
        "</div>",
        '<div class="field">',
        '<label for="theme">Background</label>',
        '<select id="theme" name="theme">',
        '<option value="auto">Match my system</option>',
        '<option value="light">Light</option>',
        '<option value="dark">Dark</option>',
        '<option value="cream">Cream</option>',
        '<option value="slate">Slate blue</option>',
        "</select>",
        '<p class="hint">Offered for comfort, not as a treatment. '
        '<span class="tier tier-preference">preference</span></p>',
        "</div>",
        "</div>",
    ])


def _slider(key: str, label: str, low: int, high: int, value: int,
            hint: str, tier: str) -> str:
    return (
        '<div class="field">'
        '<label for="%s">%s</label>'
        '<input type="range" id="%s" min="%d" max="%d" value="%d" step="1">'
        '<output for="%s" id="%s-out"></output>'
        '<p class="hint">%s <span class="tier tier-%s">%s</span></p>'
        "</div>" % (e(key), e(label), e(key), low, high, value,
                    e(key), e(key), e(hint), e(tier), e(TIER_ABBR[tier]))
    )


# --- the result -----------------------------------------------------------

def _reading_view(doc: restructure.Document) -> str:
    return "".join([
        _meaning_banner(doc),
        _numbers(doc),
        '<section id="reading" class="card reading" aria-label="Restructured text">',
        "".join(_paragraph(p) for p in doc.paragraphs),
        "</section>",
        _watched(doc),
        _original(doc),
    ])


def _meaning_banner(doc: restructure.Document) -> str:
    """Stated in words, not colour. The headline claim of the program."""
    r = doc.retention
    if r.ok:
        state, word = "ok", "Nothing lost."
        detail = ("All %d numbers, units, names, negations and hedges in the "
                  "original are still present." % r.total)
    else:
        state, word = "bad", "Something was lost."
        detail = e(r.summary())

    extra = ""
    if doc.rewrite_rejected:
        extra = ('<p class="banner-extra">The sentence rewrite was rejected '
                 "(%s) and the original wording is shown instead. This is the "
                 "intended behaviour: a harder sentence beats a changed "
                 "claim.</p>" % e(doc.rewrite_rejected))

    return (
        '<section class="banner banner-%s" role="status">'
        '<p><strong>Meaning check: %s</strong> %s</p>%s'
        "</section>" % (state, word, detail, extra)
    )


def _numbers(doc: restructure.Document) -> str:
    d = doc.delta
    # The first two move with the layout tier, which changes no words; the
    # last two move only when the rewrite tier is on. Keeping them side by
    # side is deliberate -- a teacher can see which half of the tool did what.
    cells = [
        _stat("Longest unbroken line", doc.before.longest_sentence_words,
              doc.longest_line_words, lower_is_better=True, unit=" words"),
        _stat("Reading blocks", doc.before.paragraphs, len(doc.paragraphs),
              lower_is_better=False),
        _stat("Sentences over %d words" % readability.LONG_SENTENCE_WORDS,
              doc.before.long_sentences, doc.after.long_sentences,
              lower_is_better=True),
        _stat("Mean sentence length",
              round(doc.before.mean_sentence_words, 1),
              round(doc.after.mean_sentence_words, 1),
              lower_is_better=True, unit=" words"),
    ]
    secondary = (
        '<p class="hint secondary">The first two figures are what the layout '
        "settings change: they alter no words, so words-per-sentence cannot "
        "see them, but the longest run a reader must track in one go gets "
        "shorter. The last two move only when sentence splitting is on. "
        "Flesch reading ease %.1f &rarr; %.1f (%+.1f), "
        "Flesch&ndash;Kincaid grade %.1f &rarr; %.1f (%+.1f). "
        "Reported second because the ease score punishes syllables per word "
        "as hard as words per sentence, so it can fall even when text gets "
        "easier &mdash; the figures above are the ones these settings "
        "actually change. The syllable count behind both is a heuristic with "
        "a documented error list.</p>" % (
            doc.before.flesch_reading_ease, doc.after.flesch_reading_ease,
            d["flesch_reading_ease"],
            doc.before.flesch_kincaid_grade, doc.after.flesch_kincaid_grade,
            d["flesch_kincaid_grade"])
    )
    return ('<section class="card numbers" aria-label="What changed">'
            '<h2>What changed</h2><div class="stats">%s</div>%s</section>'
            % ("".join(cells), secondary))


def _stat(label: str, before: object, after: object,
          lower_is_better: bool, unit: str = "") -> str:
    moved = ""
    try:
        if float(after) < float(before):
            moved = "better" if lower_is_better else "worse"
        elif float(after) > float(before):
            moved = "worse" if lower_is_better else "better"
        else:
            moved = "same"
    except (TypeError, ValueError):
        moved = "same"
    arrow = {"better": "improved", "worse": "worsened", "same": "unchanged"}[moved]
    return (
        '<div class="stat stat-%s">'
        '<span class="stat-label">%s</span>'
        '<span class="stat-value">%s%s <span aria-hidden="true">&rarr;</span> '
        '<strong>%s%s</strong></span>'
        '<span class="stat-move">%s</span>'
        "</div>" % (moved, e(label), e(before), e(unit), e(after), e(unit),
                    arrow)
    )


def _paragraph(p: transform.Paragraph) -> str:
    out = ['<article class="block" aria-labelledby="blk-%d">' % p.index]
    out.append('<h3 class="block-n" id="blk-%d">Block %d</h3>'
               % (p.index, p.index + 1))

    first = p.sentences[0].text if p.sentences else ""
    if p.anchor and p.anchor != first:
        out.append('<p class="anchor"><span class="anchor-tag">Key sentence'
                   "</span> %s</p>" % e(p.anchor))

    for s in p.sentences:
        cls = "sentence long" if s.is_long else "sentence"
        marked = " marked" if p.anchor and s.text == p.anchor else ""
        out.append('<p class="%s%s">' % (cls, marked))
        if marked:
            out.append('<span class="anchor-tag inline">Key</span> ')
        for line in s.lines:
            out.append('<span class="line">%s</span>' % _mark_flags(line, p.flags))
        if s.is_long:
            out.append('<span class="badge">%d words</span>' % s.word_count)
        out.append("</p>")

    if p.flags:
        out.append('<p class="flags"><span class="flags-label">Words to '
                   "check with the class:</span> %s</p>"
                   % ", ".join('<span class="flag">%s</span>' % e(f.word)
                               for f in p.flags))
    out.append("</article>")
    return "".join(out)


def _mark_flags(line: str, flags: List[transform.Flag]) -> str:
    """Underline flagged words. Escapes first, then marks, so nothing injects."""
    safe = e(line)
    for f in flags:
        word = e(f.word)
        safe = safe.replace(
            word,
            '<span class="hard" title="%s">%s</span>' % (e(f.reason), word),
            1,
        )
    return safe


def _watched(doc: restructure.Document) -> str:
    rows = []
    for kind in facts.KINDS:
        items = doc.watched.get(kind, [])
        if not items:
            continue
        rows.append(
            "<tr><th scope=\"row\">%s</th><td>%d</td><td>%s</td>"
            '<td class="why">%s</td></tr>' % (
                e(kind), len(items),
                ", ".join('<code>%s</code>' % e(i) for i in items[:12])
                + (" &hellip;" if len(items) > 12 else ""),
                e(facts.KIND_WHY[kind]))
        )
    if not rows:
        return ""
    return (
        '<details class="card"><summary>What the meaning check watched '
        "(%d items)</summary>"
        '<table><thead><tr><th scope="col">Kind</th>'
        '<th scope="col">Count</th><th scope="col">Found</th>'
        '<th scope="col">Why it matters</th></tr></thead>'
        "<tbody>%s</tbody></table></details>"
        % (doc.retention.total, "".join(rows))
    )


def _original(doc: restructure.Document) -> str:
    return (
        '<details class="card"><summary>The original text, unchanged'
        "</summary><pre class=\"original\">%s</pre></details>"
        % e(doc.original)
    )


def _footer() -> str:
    return (
        "<footer>"
        "<p>legible restructures text. It is not a diagnosis, an assessment "
        "or a treatment, and it does not claim to be one. Every setting "
        "states how well it is supported, including the ones that are not.</p>"
        "</footer>"
    )


# --- CSS and the one script ------------------------------------------------

def _css() -> str:
    return """
:root {
  --bg: #fbfaf8; --fg: #1a1a1a; --muted: #5b5b5b; --line: #e2ddd5;
  --card: #ffffff; --accent: #1b5e5a; --accent-fg: #ffffff;
  --ok: #1b5e3f; --ok-bg: #e8f3ec; --bad: #8a2318; --bad-bg: #fbeae7;
  --flag: #7a4b00; --flag-bg: #fdf3e2;
  --t-strong: #1b5e3f; --t-strong-bg: #e3f0e8;
  --t-moderate: #1f4f73; --t-moderate-bg: #e4eef6;
  --t-convention: #5b4a1f; --t-convention-bg: #f4eeda;
  --t-preference: #4a4a4a; --t-preference-bg: #ededed;
  --t-contested: #7a241a; --t-contested-bg: #f7e6e3;
  --letter: 0.06em; --lh: 1.9; --measure: 66ch;
  --font: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --radius: 10px;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]):not([data-theme="cream"]) {
    --bg: #15171a; --fg: #ecebe8; --muted: #a3a6ab; --line: #2d3136;
    --card: #1c1f23; --accent: #6fd3c7; --accent-fg: #0d2b28;
    --ok: #74d6a4; --ok-bg: #16281f; --bad: #f09b8d; --bad-bg: #2b1a17;
    --flag: #e7bd74; --flag-bg: #2a2317;
    --t-strong: #74d6a4; --t-strong-bg: #16281f;
    --t-moderate: #8cc4ea; --t-moderate-bg: #16232e;
    --t-convention: #ddc77f; --t-convention-bg: #272216;
    --t-preference: #bdbdbd; --t-preference-bg: #232323;
    --t-contested: #f0a398; --t-contested-bg: #2b1a17;
  }
}
body[data-theme="dark"] {
  --bg: #15171a; --fg: #ecebe8; --muted: #a3a6ab; --line: #2d3136;
  --card: #1c1f23; --accent: #6fd3c7; --accent-fg: #0d2b28;
  --ok: #74d6a4; --ok-bg: #16281f; --bad: #f09b8d; --bad-bg: #2b1a17;
  --flag: #e7bd74; --flag-bg: #2a2317;
  --t-strong: #74d6a4; --t-strong-bg: #16281f;
  --t-moderate: #8cc4ea; --t-moderate-bg: #16232e;
  --t-convention: #ddc77f; --t-convention-bg: #272216;
  --t-preference: #bdbdbd; --t-preference-bg: #232323;
  --t-contested: #f0a398; --t-contested-bg: #2b1a17;
}
body[data-theme="light"] { --bg: #fbfaf8; --fg: #1a1a1a; }
body[data-theme="cream"] { --bg: #f6efdf; --card: #fdf9ef; --fg: #241f16;
  --line: #e0d6bd; }
body[data-theme="slate"] { --bg: #e8eef3; --card: #f6f9fb; --fg: #16222b;
  --line: #cfdae3; }
body[data-font="serif"] { --font: Georgia, "Iowan Old Style", serif; }
body[data-font="wide"] { --font: Verdana, Tahoma, system-ui, sans-serif;
  --letter: 0.11em; }

* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font-family: var(--font); font-size: 1.0625rem; line-height: 1.5;
}
.skip {
  position: absolute; left: -9999px; top: 0; background: var(--accent);
  color: var(--accent-fg); padding: .7em 1em; z-index: 10;
}
.skip:focus { left: 0; }
header, main, footer { max-width: 62rem; margin: 0 auto; padding: 0 16px; }
header { padding-top: 2.5rem; padding-bottom: .5rem; }
h1 { font-size: 2rem; margin: 0 0 .25rem; letter-spacing: -0.02em; }
.lede { color: var(--muted); max-width: 46ch; margin: 0 0 1.5rem; }
h2 { font-size: 1.1rem; margin: 0 0 .5rem; }
h3 { font-size: .8rem; }
.card {
  background: var(--card); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 1.25rem; margin: 0 0 1.25rem;
}
textarea {
  width: 100%; font: inherit; font-size: 1rem; padding: .75rem;
  border: 1px solid var(--line); border-radius: 8px; resize: vertical;
  background: var(--bg); color: var(--fg);
}
.actions { display: flex; gap: .5rem; flex-wrap: wrap; margin: .75rem 0 0; }
button {
  font: inherit; padding: .6em 1.1em; border-radius: 8px; cursor: pointer;
  border: 1px solid var(--line); background: var(--bg); color: var(--fg);
}
button.primary {
  background: var(--accent); color: var(--accent-fg); border-color: var(--accent);
  font-weight: 600;
}
:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
.ops-head { margin-top: 1.75rem; }
.hint { color: var(--muted); font-size: .875rem; margin: .25rem 0 0;
  max-width: 62ch; }
.hint.secondary { margin-top: 1rem; }
ul.ops, ul.plain { list-style: none; padding: 0; margin: .5rem 0 0; }
ul.plain li { margin: .4rem 0; }
.op { border-top: 1px solid var(--line); padding: .7rem 0; }
.op label { display: inline-flex; align-items: center; gap: .55rem;
  cursor: pointer; }
.op-title { font-weight: 600; }
.op input[type="checkbox"] { width: 1.15rem; height: 1.15rem; accent-color: var(--accent); }
.tier {
  display: inline-block; margin-left: .5rem; padding: .1em .55em;
  border-radius: 999px; font-size: .72rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .04em; white-space: nowrap;
  border: 1px solid currentColor;
}
.tier-strong { color: var(--t-strong); background: var(--t-strong-bg); }
.tier-moderate { color: var(--t-moderate); background: var(--t-moderate-bg); }
.tier-convention { color: var(--t-convention); background: var(--t-convention-bg); }
.tier-preference { color: var(--t-preference); background: var(--t-preference-bg); }
.tier-contested { color: var(--t-contested); background: var(--t-contested-bg); }
details { margin-top: .4rem; }
summary { cursor: pointer; color: var(--muted); font-size: .875rem; }
.note, .src, .detail { font-size: .875rem; max-width: 66ch; }
.src { color: var(--muted); }
.detail { color: var(--muted); }
.typo { display: grid; gap: 1.1rem; grid-template-columns: 1fr; margin-top: .5rem; }
@media (min-width: 40rem) { .typo { grid-template-columns: 1fr 1fr; } }
.field label { display: block; font-weight: 600; margin-bottom: .3rem; }
.field input[type="range"] { width: 100%; accent-color: var(--accent); }
.field select { font: inherit; padding: .45em .6em; border-radius: 8px;
  border: 1px solid var(--line); background: var(--bg); color: var(--fg);
  width: 100%; }
output { font-variant-numeric: tabular-nums; color: var(--muted);
  font-size: .85rem; }

.banner { border-radius: var(--radius); padding: .9rem 1.1rem;
  margin: 0 0 1.25rem; border: 1px solid; }
.banner p { margin: 0; }
.banner-ok { color: var(--ok); background: var(--ok-bg); border-color: currentColor; }
.banner-bad { color: var(--bad); background: var(--bad-bg); border-color: currentColor; }
.banner-extra { margin-top: .5rem; font-size: .9rem; }

.stats { display: grid; gap: .75rem; grid-template-columns: 1fr; }
@media (min-width: 34rem) { .stats { grid-template-columns: 1fr 1fr; } }
@media (min-width: 52rem) { .stats { grid-template-columns: repeat(4, 1fr); } }
.stat { border: 1px solid var(--line); border-radius: 8px; padding: .7rem .8rem; }
.stat-label { display: block; font-size: .78rem; color: var(--muted);
  text-transform: uppercase; letter-spacing: .04em; }
.stat-value { display: block; font-size: 1.15rem; margin: .25rem 0 .1rem;
  font-variant-numeric: tabular-nums; }
.stat-move { font-size: .75rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .04em; }
.stat-better .stat-move { color: var(--ok); }
.stat-worse .stat-move { color: var(--bad); }
.stat-same .stat-move { color: var(--muted); }

.reading { max-width: none; }
.block { border-top: 1px solid var(--line); padding: 1.1rem 0 .4rem; }
.block:first-of-type { border-top: 0; padding-top: 0; }
.block-n { color: var(--muted); font-size: .72rem; text-transform: uppercase;
  letter-spacing: .08em; margin: 0 0 .5rem; font-weight: 700; }
.anchor { background: var(--t-moderate-bg); border-left: 4px solid var(--t-moderate);
  padding: .6rem .8rem; border-radius: 0 8px 8px 0; margin: 0 0 .9rem;
  max-width: var(--measure); }
.anchor-tag { font-size: .7rem; font-weight: 800; text-transform: uppercase;
  letter-spacing: .06em; color: var(--t-moderate); display: block; }
.anchor-tag.inline { display: inline; margin-right: .4rem; }
.sentence { margin: 0 0 .85rem; max-width: var(--measure);
  letter-spacing: var(--letter); line-height: var(--lh); }
.sentence.marked { border-left: 4px solid var(--t-moderate); padding-left: .8rem; }
.line { display: block; }
.line + .line { padding-left: 1.4rem; }
.badge { display: inline-block; margin-top: .3rem; font-size: .72rem;
  color: var(--muted); border: 1px solid var(--line); border-radius: 999px;
  padding: .05em .6em; letter-spacing: normal; }
.hard { background: var(--flag-bg); color: var(--flag);
  text-decoration: underline; text-decoration-style: dotted;
  text-underline-offset: 3px; border-radius: 3px; padding: 0 .1em; }
.flags { font-size: .875rem; color: var(--muted); max-width: var(--measure); }
.flags-label { font-weight: 700; }
.flag { border-bottom: 2px dotted var(--flag); }
table { border-collapse: collapse; width: 100%; font-size: .875rem;
  margin-top: .75rem; }
th, td { text-align: left; padding: .45rem .5rem; border-bottom: 1px solid var(--line);
  vertical-align: top; }
td.why { color: var(--muted); }
code { background: var(--bg); border: 1px solid var(--line); border-radius: 4px;
  padding: 0 .3em; font-size: .9em; }
pre.original { white-space: pre-wrap; font-family: var(--font);
  font-size: .95rem; color: var(--muted); max-width: 72ch; margin: .75rem 0 0; }
footer { color: var(--muted); font-size: .85rem; padding: 1rem 16px 3rem;
  max-width: 52rem; }
.empty h2 { margin-bottom: .5rem; }
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
"""


def _js() -> str:
    """Typography only. The page is fully readable without it."""
    return """
(function () {
  var body = document.body;
  var map = {
    letter: function (v) { body.style.setProperty('--letter', (v / 100) + 'em');
      return (v / 100).toFixed(2) + 'em'; },
    line: function (v) { body.style.setProperty('--lh', (v / 10));
      return (v / 10).toFixed(1); },
    width: function (v) { body.style.setProperty('--measure', v + 'ch');
      return v + ' characters'; }
  };
  Object.keys(map).forEach(function (key) {
    var input = document.getElementById(key);
    var out = document.getElementById(key + '-out');
    if (!input) { return; }
    var apply = function () {
      var label = map[key](parseInt(input.value, 10));
      if (out) { out.textContent = label; }
      try { localStorage.setItem('legible.' + key, input.value); } catch (e) {}
    };
    try {
      var saved = localStorage.getItem('legible.' + key);
      if (saved !== null) { input.value = saved; }
    } catch (e) {}
    input.addEventListener('input', apply);
    apply();
  });
  [['font', 'data-font'], ['theme', 'data-theme']].forEach(function (pair) {
    var select = document.getElementById(pair[0]);
    if (!select) { return; }
    var apply = function () {
      body.setAttribute(pair[1], select.value);
      try { localStorage.setItem('legible.' + pair[0], select.value); } catch (e) {}
    };
    try {
      var saved = localStorage.getItem('legible.' + pair[0]);
      if (saved !== null) { select.value = saved; }
    } catch (e) {}
    select.addEventListener('change', apply);
    apply();
  });
}());
"""
