"""A reading view served from the standard library.

No framework, because `pyproject.toml` promises no runtime dependencies and
a teacher installing this on a school laptop should not need a wheel to
build. `http.server` is enough for one page and one form.

It binds to 127.0.0.1 by default and says so on startup. The text a teacher
pastes is a child's lesson material: it is processed in this process and
never leaves the machine. That is a property of the design, not a promise in
a privacy policy -- there is no code here that could send it anywhere, and
`tests/test_safety.py` checks that the modules doing the work cannot either.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Tuple

from . import evidence, render, restructure, transform

MAX_BODY = 1000000          # a megabyte of lesson text is already too much


class Handler(BaseHTTPRequestHandler):
    server_version = "legible"

    # --- plumbing ---------------------------------------------------------

    def log_message(self, fmt, *args):
        """Log the method and path only. Never the pasted text."""
        sys.stderr.write("%s %s\n" % (self.command, self.path.split("?")[0]))

    def _send(self, body: str, status: int = 200,
              content_type: str = "text/html; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        # The page loads nothing from anywhere else, so the policy can say so.
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; "
            "script-src 'unsafe-inline'; form-action 'self'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    # --- routes -----------------------------------------------------------

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._send(render.page(None, ""))
        elif path == "/evidence":
            self._send(_evidence_page())
        elif path == "/api/evidence":
            self._send(json.dumps(_evidence_json(), indent=2),
                       content_type="application/json; charset=utf-8")
        elif path == "/healthz":
            self._send("ok", content_type="text/plain; charset=utf-8")
        else:
            self._send(_not_found(), status=404)

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY:
            self._send(_too_big(), status=413)
            return
        raw = self.rfile.read(length).decode("utf-8", "replace")

        if path == "/api/restructure":
            self._api(raw)
            return
        if path != "/":
            self._send(_not_found(), status=404)
            return

        fields = urllib.parse.parse_qs(raw, keep_blank_values=True)
        text, settings = _read_form(fields)
        doc = restructure.build(text, settings) if text.strip() else None
        self._send(render.page(doc, text))

    def _api(self, raw: str) -> None:
        """JSON in, JSON out. Same pipeline, no HTML."""
        try:
            payload = json.loads(raw or "{}")
        except ValueError as exc:
            self._send(json.dumps({"error": "invalid JSON: %s" % exc}),
                       status=400,
                       content_type="application/json; charset=utf-8")
            return

        text = str(payload.get("text") or "")
        settings = {k: bool(v)
                    for k, v in (payload.get("settings") or {}).items()
                    if k in transform.DEFAULTS}
        doc = restructure.build(text, settings)
        self._send(json.dumps(doc_json(doc), indent=2),
                   content_type="application/json; charset=utf-8")


def _read_form(fields: Dict[str, List[str]]) -> Tuple[str, Dict[str, bool]]:
    """Checkbox semantics: absent means off, so every key is listed explicitly."""
    if fields.get("sample"):
        return render.SAMPLE, dict(transform.DEFAULTS)
    text = (fields.get("text") or [""])[0]
    settings = {op.key: ("op_%s" % op.key) in fields
                for op in transform.OPERATIONS}
    return text, settings


def doc_json(doc: restructure.Document) -> dict:
    """The whole result as plain data. Used by the API and by the CLI."""
    return {
        "safe": doc.safe,
        "retention": {
            "rate": doc.retention.rate,
            "total": doc.retention.total,
            "kept": doc.retention.kept,
            "lost": {k: v for k, v in doc.retention.lost.items() if v},
            "summary": doc.retention.summary(),
        },
        "rewrite": {
            "applied": doc.rewrite_applied,
            "rejected": doc.rewrite_rejected,
        },
        "before": doc.before.as_dict(),
        "after": doc.after.as_dict(),
        "delta": doc.delta,
        "settings": doc.settings,
        "blocks": [
            {
                "index": p.index,
                "anchor": p.anchor,
                "words": p.word_count,
                "chunked": p.was_chunked,
                "flags": [f.word for f in p.flags],
                "sentences": [
                    {"text": s.text, "words": s.word_count,
                     "long": s.is_long, "lines": s.lines}
                    for s in p.sentences
                ],
            }
            for p in doc.paragraphs
        ],
    }


def _evidence_json() -> dict:
    return {
        "tiers": [
            {"tier": t, "label": evidence.TIER_LABEL[t],
             "meaning": evidence.TIER_MEANING[t]}
            for t in evidence.TIER_ORDER
        ],
        "findings": [dict(f._asdict()) for f in evidence.FINDINGS],
        "operations": [
            dict(dict(o._asdict()), tier=evidence.finding(o.evidence_key).tier)
            for o in transform.OPERATIONS
        ],
    }


def _shell(title: str, body: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>%s</title><style>%s</style></head>"
        '<body data-theme="auto">%s</body></html>'
        % (html.escape(title), render._css(), body)
    )


def _evidence_page() -> str:
    rows = []
    for f in sorted(evidence.FINDINGS, key=lambda x: evidence.tier_rank(x.tier)):
        rows.append(
            '<article class="card"><h2>%s</h2>'
            '<p><span class="tier tier-%s">%s</span> <strong>%s</strong></p>'
            '<p class="src">%s</p><p class="detail">%s</p></article>' % (
                html.escape(f.claim), html.escape(f.tier),
                html.escape(render.TIER_ABBR[f.tier]),
                html.escape(evidence.TIER_LABEL[f.tier]),
                html.escape(f.source), html.escape(f.detail))
        )
    tiers = "".join(
        '<li><span class="tier tier-%s">%s</span> %s</li>' % (
            html.escape(t), html.escape(render.TIER_ABBR[t]),
            html.escape(evidence.TIER_MEANING[t]))
        for t in evidence.TIER_ORDER
    )
    return _shell("What the evidence says - legible", (
        "<header><h1>What the evidence says</h1>"
        '<p class="lede">Every setting in legible carries one of these tiers, '
        "and the reading view shows it. This page is the whole register, "
        "strongest first.</p></header>"
        '<main><section class="card"><h2>The tiers</h2>'
        '<ul class="plain">%s</ul></section>%s'
        '<p class="hint"><a href="/">Back to the reading view</a> '
        '&middot; <a href="/api/evidence">The same register as JSON</a></p>'
        "</main>" % (tiers, "".join(rows))
    ))


def _not_found() -> str:
    return _shell("Not found - legible", (
        '<main><section class="card"><h2>Not found</h2>'
        '<p><a href="/">Back to the reading view</a></p></section></main>'))


def _too_big() -> str:
    return _shell("Too much text - legible", (
        '<main><section class="card"><h2>That is a lot of text</h2>'
        "<p>The limit is one megabyte, which is far more lesson material than "
        "this view can usefully show at once. Paste a section of it.</p>"
        '<p><a href="/">Back</a></p></section></main>'))


def serve(host: str = "127.0.0.1", port: int = 8000) -> int:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print("legible is reading at http://%s:%d/" % (host, port))
    print("Nothing leaves this machine. Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        httpd.server_close()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Serve the legible reading view")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)
    return serve(args.host, args.port)


if __name__ == "__main__":
    sys.exit(main())
