"""Render the short vertical video for social, 1080x1920.

    python tools/viral_render.py            # docs/legible-short.mp4

This is the same bargain as the long-form tool in gitwhy: the frames are
drawn rather than screen-recorded, but the words on them are not invented.
The lesson text, the clause lines it gets broken into, the 60-to-28 figure
and the 13-of-13 retention all come out of `legible` itself at render time,
through the same code path the web view uses. If the library changes, these
frames change with it.

The narration decides the cut. Each scene lasts exactly as long as its own
line plus a breath, read from docs/narration/*.mp3. With that folder empty
the video still renders, silent, on the fallback timings written here.

Vertical because the destination is a phone. The typography is the argument,
so it gets a serif for anything that is lesson text and a heavy sans for
anything that is us talking: the viewer should never be unsure which they
are looking at.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from typing import Callable, List, NamedTuple, Optional, Sequence, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("Needs Pillow:\n\n    pip install Pillow\n")

try:
    import imageio_ffmpeg
except ImportError:
    raise SystemExit("Needs ffmpeg:\n\n    pip install imageio-ffmpeg\n")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from legible import render as legible_render       # noqa: E402
from legible import restructure                     # noqa: E402

NARRATION = os.path.join(ROOT, "docs", "narration")
OUT = os.path.join(ROOT, "docs", "legible-short.mp4")
SILENT = os.path.join(ROOT, "docs", "legible-short-silent.mp4")

W, H = 1080, 1920
FPS = 30
PAD = 0.45          # breath after each line; short, because this is social
MARGIN = 96

# legible's own paper, so the video and the product look like one thing.
PAPER = (250, 248, 245)
INK = (32, 30, 28)
MUTED = (122, 116, 110)
ACCENT = (176, 94, 40)        # the glossary/flag warm tone
GOOD = (54, 122, 76)
BAD = (186, 60, 52)
RULE = (226, 220, 212)

SANS = r"C:\Windows\Fonts\segoeui.ttf"
SANS_BLACK = r"C:\Windows\Fonts\seguibl.ttf"
SANS_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"
SERIF = r"C:\Windows\Fonts\georgia.ttf"

_FONTS: dict = {}


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    key = (path, size)
    if key not in _FONTS:
        if not os.path.exists(path):
            raise SystemExit("Missing font: %s" % path)
        _FONTS[key] = ImageFont.truetype(path, size)
    return _FONTS[key]


def ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


# --- the real content, read out of legible ---------------------------------

def lesson() -> Tuple[str, List[str], int, int, int]:
    """The sentence, its clause lines, and the figures. All from legible.

    Nothing here is a copy kept in this file: the paragraph is legible's own
    sample, the lines are what the layout tier produces from it, and the two
    numbers are what the pipeline measured. A frame claiming "60 words"
    cannot drift away from the thing that counted them.
    """
    doc = restructure.build(legible_render.SAMPLE, {})
    first = doc.paragraphs[0].sentences[0]
    sentence = " ".join(first.lines)
    return (sentence, list(first.lines),
            doc.before.longest_sentence_words, doc.longest_line_words,
            doc.retention.total)


SENTENCE, CLAUSE_LINES, LONGEST_BEFORE, LONGEST_AFTER, WATCHED = lesson()


# --- drawing ---------------------------------------------------------------

def wrap(text: str, f: ImageFont.FreeTypeFont, width: int) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        trial = (cur + " " + word).strip()
        if f.getlength(trial) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def new_frame() -> Tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), PAPER)
    return img, ImageDraw.Draw(img)


def block(d: ImageDraw.ImageDraw, lines: Sequence[str],
          f: ImageFont.FreeTypeFont, top: int, leading: float,
          colour=INK, centre=True, x0: int = MARGIN) -> int:
    """Draw lines from `top`, return the y just past the last one."""
    lh = int(f.size * leading)
    y = top
    for line in lines:
        x = (W - f.getlength(line)) / 2 if centre else x0
        d.text((x, y), line, font=f, fill=colour)
        y += lh
    return y


def centred_block_top(n: int, f: ImageFont.FreeTypeFont, leading: float) -> int:
    return int((H - n * f.size * leading) / 2)


# --- scenes ----------------------------------------------------------------
#
# A scene is a function of progress (0..1) returning a frame, so anything
# that moves -- a counter, a reveal -- is just a function of t.

def scene_hook(t: float) -> Image.Image:
    img, d = new_frame()
    f = font(SANS_BLACK, 112)
    small = font(SANS, 52)
    top = centred_block_top(4, f, 1.18) - 60
    y = block(d, ["You just read", "a whole page."], f, top, 1.18)
    y += 54
    if t > 0.42:
        q = font(SANS_BLACK, 100)
        block(d, wrap("Remember one sentence?", q, W - 2 * MARGIN), q, y, 1.15,
              colour=ACCENT)
    else:
        block(d, ["Be honest."], small, y + 18, 1.2, colour=MUTED)
    return img


def scene_not_you(t: float) -> Image.Image:
    img, d = new_frame()
    f = font(SANS_BLACK, 108)
    top = centred_block_top(4, f, 1.18)
    y = block(d, ["It's not your", "attention span."], f, top, 1.18, colour=MUTED)
    y += 46
    if t > 0.38:
        block(d, ["It's the shape", "of the text."], f, y, 1.18, colour=INK)
    return img


def _wall_lines() -> List[str]:
    """The sentence set in long lines, the way it arrives in the wild."""
    return wrap(SENTENCE, font(SERIF, 46), W - 2 * MARGIN)


def scene_wall(t: float) -> Image.Image:
    """One sentence, long lines, tight leading. The problem, drawn."""
    img, d = new_frame()
    f = font(SERIF, 46)
    lines = _wall_lines()
    top = centred_block_top(len(lines), f, 1.28) - 40
    block(d, lines, f, top, 1.28, centre=False)

    badge = font(SANS_BOLD, 40)
    label = "%d words before a single break." % LONGEST_BEFORE
    y = top + len(lines) * f.size * 1.28 + 56
    if t > 0.3:
        d.text(((W - badge.getlength(label)) / 2, y), label,
               font=badge, fill=BAD)
    return img


def scene_break(t: float) -> Image.Image:
    """The same words, re-laid as clause lines, while the number falls."""
    img, d = new_frame()
    f = font(SERIF, 44)
    lines = CLAUSE_LINES
    drawn: List[str] = []
    for i, line in enumerate(lines):
        if t >= (i / max(1, len(lines))) * 0.55:
            drawn.append(line)
    laid: List[str] = []
    for line in drawn:
        laid.extend(wrap(line, f, W - 2 * MARGIN - 60))

    top = centred_block_top(len(_wall_lines()) + 2, f, 1.9) - 40
    y = top
    for line in laid:
        d.text((MARGIN + 30, y), line, font=f, fill=INK)
        y += int(f.size * 1.9)

    # 60 -> 28, counted down rather than cut to.
    big = font(SANS_BLACK, 150)
    frac = min(1.0, max(0.0, (t - 0.45) / 0.4))
    n = int(round(LONGEST_BEFORE + (LONGEST_AFTER - LONGEST_BEFORE) * frac))
    colour = GOOD if frac >= 1.0 else INK
    label = "%d" % n
    d.text(((W - big.getlength(label)) / 2, H - 430), label, font=big, fill=colour)
    cap = font(SANS_BOLD, 38)
    sub = "words before a break"
    d.text(((W - cap.getlength(sub)) / 2, H - 250), sub, font=cap, fill=MUTED)
    return img


def scene_same_words(t: float) -> Image.Image:
    img, d = new_frame()
    f = font(SANS_BLACK, 128)
    top = centred_block_top(3, f, 1.15) - 80
    y = block(d, ["SAME", "WORDS."], f, top, 1.15)
    y += 50
    small = font(SANS, 44)
    items = ["nothing rewritten", "nothing summarised", "nothing deleted"]
    for i, item in enumerate(items):
        if t > 0.3 + i * 0.16:
            d.text(((W - small.getlength(item)) / 2, y), item,
                   font=small, fill=MUTED)
        y += 68
    return img


def scene_nobody_checks(t: float) -> Image.Image:
    img, d = new_frame()
    f = font(SANS_BLACK, 100)
    lines = wrap("Here's what nobody checks.", f, W - 2 * MARGIN)
    top = centred_block_top(len(lines) + 3, f, 1.16)
    y = block(d, lines, f, top, 1.16)
    y += 50
    if t > 0.35:
        small = font(SANS, 46)
        body = wrap("Tools that \u201csimplify\u201d text quietly change "
                    "what it says.", small, W - 2 * MARGIN)
        block(d, body, small, y, 1.34, colour=MUTED)
    return img


def scene_antibiotics(t: float) -> Image.Image:
    """The failure the whole project exists for, in one frame."""
    img, d = new_frame()
    f = font(SERIF, 54)
    top = 420

    before = wrap("Antibiotics do not work against viruses.", f, W - 2 * MARGIN)
    y = block(d, before, f, top, 1.34, centre=False)
    tag = font(SANS_BOLD, 32)
    d.text((MARGIN, y + 10), "ORIGINAL", font=tag, fill=MUTED)

    if t > 0.34:
        y2 = y + 150
        d.line([(MARGIN, y2 - 40), (W - MARGIN, y2 - 40)], fill=RULE, width=2)
        after = wrap("Antibiotics work against viruses.", f, W - 2 * MARGIN)
        y3 = block(d, after, f, y2 + 20, 1.34, centre=False, colour=BAD)
        # strike the line that lost the negation
        if t > 0.6:
            d.line([(MARGIN, y2 + 20 + f.size * 0.62),
                    (MARGIN + f.getlength(after[0]), y2 + 20 + f.size * 0.62)],
                   fill=BAD, width=3)
        d.text((MARGIN, y3 + 10), "\u201cSIMPLIFIED\u201d", font=tag, fill=BAD)
        if t > 0.66:
            verdict = font(SANS_BLACK, 62)
            msg = "Reads easier. Opposite meaning."
            for line in wrap(msg, verdict, W - 2 * MARGIN):
                d.text(((W - verdict.getlength(line)) / 2, y3 + 150), line,
                       font=verdict, fill=INK)
                y3 += int(verdict.size * 1.18)
    return img


def scene_counts(t: float) -> Image.Image:
    img, d = new_frame()
    f = font(SANS_BLACK, 112)
    items = [("Every number.", 0.0), ("Every name.", 0.22),
             ("Every \u201cnot\u201d.", 0.44)]
    top = centred_block_top(3, f, 1.3)
    y = top
    for text, at in items:
        if t > at:
            d.text(((W - f.getlength(text)) / 2, y), text, font=f, fill=INK)
        y += int(f.size * 1.3)
    if t > 0.7:
        small = font(SANS, 44)
        msg = "checked before you ever see it"
        d.text(((W - small.getlength(msg)) / 2, y + 30), msg,
               font=small, fill=MUTED)
    return img


def scene_proof(t: float) -> Image.Image:
    img, d = new_frame()
    big = font(SANS_BLACK, 260)
    frac = min(1.0, t / 0.45)
    n = int(round(WATCHED * frac))
    label = "%d/%d" % (n, WATCHED)
    d.text(((W - big.getlength(label)) / 2, H / 2 - 320), label,
           font=big, fill=GOOD if frac >= 1.0 else INK)
    cap = font(SANS_BOLD, 52)
    for i, line in enumerate(["numbers, names, negations", "and hedges kept"]):
        d.text(((W - cap.getlength(line)) / 2, H / 2 + 80 + i * 72), line,
               font=cap, fill=INK)
    if t > 0.6:
        small = font(SANS, 40)
        msg = "every file, every time, or it refuses"
        d.text(((W - small.getlength(msg)) / 2, H / 2 + 270), msg,
               font=small, fill=MUTED)
    return img


def scene_end(t: float) -> Image.Image:
    img, d = new_frame()
    mark = font(SANS_BLACK, 176)
    d.text(((W - mark.getlength("legible")) / 2, H / 2 - 220),
           "legible", font=mark, fill=INK)
    cap = font(SANS, 46)
    for i, line in enumerate(["free \u00b7 offline \u00b7 open source",
                              "your text never leaves the machine"]):
        d.text(((W - cap.getlength(line)) / 2, H / 2 - 20 + i * 70),
               line, font=cap, fill=MUTED)
    if t > 0.3:
        url = font(SANS_BOLD, 44)
        link = "github.com/Sanixaa23/legible"
        d.text(((W - url.getlength(link)) / 2, H / 2 + 170), link,
               font=url, fill=ACCENT)
    return img


class Scene(NamedTuple):
    clip: str                      # narration basename, "" for none
    fallback: float                # seconds when there is no narration
    draw: Callable[[float], Image.Image]


SCENES: Tuple[Scene, ...] = (
    Scene("01_hook", 4.5, scene_hook),
    Scene("02_not_you", 3.6, scene_not_you),
    Scene("03_wall", 6.0, scene_wall),
    Scene("04_break", 4.2, scene_break),
    Scene("05_same_words", 5.0, scene_same_words),
    Scene("06_nobody_checks", 5.0, scene_nobody_checks),
    Scene("07_antibiotics", 7.0, scene_antibiotics),
    Scene("08_counts", 4.6, scene_counts),
    Scene("09_proof", 3.6, scene_proof),
    Scene("10_end", 5.0, scene_end),
)


# --- timing from the narration ---------------------------------------------

def audio_seconds(path: str) -> float:
    import re
    out = subprocess.run([ffmpeg(), "-i", path], capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.?\d*)", out)
    if not m:
        raise SystemExit("Cannot read the length of %s" % path)
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


def clip_path(name: str) -> Optional[str]:
    path = os.path.join(NARRATION, name + ".mp3")
    return path if name and os.path.exists(path) else None


def durations() -> List[float]:
    out = []
    for sc in SCENES:
        path = clip_path(sc.clip)
        out.append(round(audio_seconds(path) + PAD, 2) if path else sc.fallback)
    return out


# --- audio -----------------------------------------------------------------

def build_audio(secs: Sequence[float], wav: str) -> bool:
    clips = [clip_path(sc.clip) for sc in SCENES]
    if not any(clips):
        return False
    work = tempfile.mkdtemp(prefix="legible-audio-")
    parts = []
    for i, (sc, dur, clip) in enumerate(zip(SCENES, secs, clips)):
        path = os.path.join(work, "%02d.wav" % i)
        if clip:
            subprocess.run([ffmpeg(), "-y", "-v", "error", "-i", clip,
                            "-af", "apad=pad_dur=%.3f" % PAD,
                            "-ar", "44100", "-ac", "2", path], check=True)
        else:
            subprocess.run([ffmpeg(), "-y", "-v", "error", "-f", "lavfi",
                            "-i", "anullsrc=r=44100:cl=stereo",
                            "-t", "%.3f" % dur, path], check=True)
        parts.append(path)
    listing = os.path.join(work, "list.txt")
    with open(listing, "w", encoding="utf-8") as f:
        for p in parts:
            f.write("file '%s'\n" % p.replace("\\", "/"))
    subprocess.run([ffmpeg(), "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", listing, "-c", "copy", wav], check=True)
    return True


def mux(video: str, wav: str, out: str) -> None:
    subprocess.run([ffmpeg(), "-y", "-v", "error", "-i", video, "-i", wav,
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", out], check=True)


# --- main ------------------------------------------------------------------

def main(argv: Sequence[str] = ()) -> int:
    secs = durations()
    total = sum(secs)
    narrated = any(clip_path(sc.clip) for sc in SCENES)
    print("legible short: %dx%d @%dfps, %.1fs, %s" % (
        W, H, FPS, total, "narrated" if narrated else "silent"))

    target = SILENT if narrated else OUT
    writer = imageio_ffmpeg.write_frames(
        target, (W, H), fps=FPS, codec="libx264", quality=7,
        macro_block_size=1, ffmpeg_log_level="error",
        output_params=["-pix_fmt", "yuv420p"])
    writer.send(None)

    frames = 0
    try:
        for sc, dur in zip(SCENES, secs):
            n = max(1, int(round(dur * FPS)))
            got = "yes" if clip_path(sc.clip) else "-- "
            print("  %-18s %5.1fs  %4d frames  narration %s" % (
                sc.clip or "(silent)", dur, n, got))
            for i in range(n):
                writer.send(sc.draw(i / max(1, n - 1)).tobytes())
            frames += n
    finally:
        writer.close()

    if narrated:
        wav = os.path.join(os.path.dirname(OUT), "legible-short-narration.wav")
        build_audio(secs, wav)
        mux(SILENT, wav, OUT)
        os.remove(wav)
        os.remove(SILENT)

    print("\n%s" % OUT)
    print("%d frames, %.1fs, %.1f MB" % (
        frames, frames / FPS, os.path.getsize(OUT) / 1e6))
    missing = [sc.clip for sc in SCENES if not clip_path(sc.clip)]
    if missing:
        print("no narration yet for: %s" % ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
