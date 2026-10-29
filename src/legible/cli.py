"""The command line. Five subcommands, each doing one thing.

    legible read lesson.txt        restructure and print it
    legible check lesson.txt       just the meaning check, exit 1 if it fails
    legible stats lesson.txt       just the numbers
    legible evidence               the register, strongest first
    legible serve                  the reading view in a browser

`check` exits non-zero when something was lost, so it can go in a marking
pipeline or a pre-commit hook over a folder of worksheets.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

from . import __version__, evidence, facts, readability, render, restructure, transform


def _read_input(path: Optional[str]) -> str:
    """A file, or standard input when the path is missing or '-'."""
    if path in (None, "-"):
        data = sys.stdin.buffer.read()
        return data.decode("utf-8", "replace")
    if path.lower().endswith(".pdf"):
        return _read_pdf(path)
    with open(path, "rb") as f:
        return f.read().decode("utf-8", "replace")


def _read_pdf(path: str) -> str:
    """PDF is an optional extra, and the failure says exactly what to install."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise SystemExit(
            "Reading PDFs needs one extra package:\n\n"
            "    pip install \"legible[pdf]\"\n\n"
            "Plain text and pasted text need nothing.")
    reader = PdfReader(path)
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def _settings(args) -> Dict[str, bool]:
    on = dict(transform.DEFAULTS)
    for key in getattr(args, "off", None) or []:
        if key not in on:
            raise SystemExit("No such setting: %s (try: %s)"
                             % (key, ", ".join(sorted(on))))
        on[key] = False
    if getattr(args, "rewrite", False):
        on["split_sentences"] = True
    return on


# --- the commands ---------------------------------------------------------

def cmd_read(args) -> int:
    text = _read_input(args.path)
    doc = restructure.build(text, _settings(args))

    if args.json:
        from .server import doc_json
        print(json.dumps(doc_json(doc), indent=2))
        return 0 if doc.safe else 1
    if args.html:
        print(render.page(doc, text))
        return 0 if doc.safe else 1

    for p in doc.paragraphs:
        print()
        print("-- block %d %s" % (p.index + 1, "-" * 52))
        if p.anchor and p.sentences and p.anchor != p.sentences[0].text:
            print("   KEY: %s" % p.anchor)
            print()
        for s in p.sentences:
            for i, line in enumerate(s.lines):
                print("   %s%s" % ("    " if i else "", line))
            if s.is_long:
                print("        [%d words]" % s.word_count)
        if p.flags:
            print()
            print("   words to check: %s" % ", ".join(f.word for f in p.flags))

    print()
    print("=" * 66)
    for line in restructure.summary_lines(doc):
        print(line)
    return 0 if doc.safe else 1


def cmd_check(args) -> int:
    """The gate. Silent and zero when nothing was lost."""
    text = _read_input(args.path)
    doc = restructure.build(text, _settings(args))
    name = args.path or "stdin"

    if doc.safe:
        if not args.quiet:
            print("%s: %s" % (name, doc.retention.summary()))
        return 0

    print("%s: MEANING CHANGED -- %s" % (name, doc.retention.summary()),
          file=sys.stderr)
    for kind, items in doc.retention.lost.items():
        for item in items:
            print("  lost %-9s %-20s %s" % (kind, item, facts.KIND_WHY[kind]),
                  file=sys.stderr)
    return 1


def cmd_stats(args) -> int:
    text = _read_input(args.path)
    doc = restructure.build(text, _settings(args))
    for line in restructure.summary_lines(doc):
        print(line)
    lengths = doc.sentence_lengths()
    if lengths:
        print()
        print("Sentence lengths")
        for bucket, n in readability.distribution(lengths).items():
            print("  %-6s %s %d" % (bucket, "#" * n, n))
    return 0


def cmd_evidence(args) -> int:
    if args.json:
        from .server import _evidence_json
        print(json.dumps(_evidence_json(), indent=2))
        return 0

    print("What each setting rests on, strongest first.")
    print()
    for found in sorted(evidence.FINDINGS, key=lambda f: evidence.tier_rank(f.tier)):
        print("[%s] %s" % (evidence.TIER_LABEL[found.tier].upper(), found.claim))
        print("    source: %s" % found.source)
        for line in _wrap(found.detail, 68):
            print("    %s" % line)
        print()
    print("Settings in the program, and the claim each one uses:")
    for op in transform.OPERATIONS:
        found = evidence.finding(op.evidence_key)
        print("  %-16s %-12s %s%s" % (
            op.key, found.tier, op.title,
            "" if op.default_on else "   (off by default)"))
    return 0


def cmd_serve(args) -> int:
    from .server import serve
    return serve(args.host, args.port)


def _wrap(text: str, width: int) -> List[str]:
    out, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = (line + " " + word).strip()
    if line:
        out.append(line)
    return out


# --- wiring ---------------------------------------------------------------

def _add_common(parser) -> None:
    parser.add_argument("path", nargs="?", help="a .txt or .pdf file, or - for stdin")
    parser.add_argument("--rewrite", action="store_true",
                        help="also split sentences over %d words (off by default)"
                             % readability.SPLIT_SENTENCE_WORDS)
    parser.add_argument("--off", action="append", metavar="SETTING",
                        help="turn a setting off; repeatable")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="legible",
        description="Restructure lesson material, and prove it kept the meaning.")
    ap.add_argument("--version", action="version",
                    version="legible %s" % __version__)
    sub = ap.add_subparsers(dest="command")

    read = sub.add_parser("read", help="restructure text and print it")
    _add_common(read)
    read.add_argument("--json", action="store_true", help="machine-readable output")
    read.add_argument("--html", action="store_true", help="the full reading view")
    read.set_defaults(func=cmd_read)

    check = sub.add_parser(
        "check",
        help="exit 1 if any number, name, negation or hedge was lost")
    _add_common(check)
    check.add_argument("-q", "--quiet", action="store_true")
    check.set_defaults(func=cmd_check)

    stats = sub.add_parser("stats", help="the numbers only")
    _add_common(stats)
    stats.set_defaults(func=cmd_stats)

    ev = sub.add_parser("evidence", help="what each setting rests on")
    ev.add_argument("--json", action="store_true")
    ev.set_defaults(func=cmd_evidence)

    srv = sub.add_parser("serve", help="the reading view, in a browser")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8000)
    srv.set_defaults(func=cmd_serve)

    return ap


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 0
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print("No such file: %s" % exc.filename, file=sys.stderr)
        return 2
    except BrokenPipeError:
        # `legible read x | head` is a normal thing to do.
        os_devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(os_devnull, sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    sys.exit(main())
