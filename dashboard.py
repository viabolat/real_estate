#!/usr/bin/env python3
"""
dashboard.py

A read-only window over state this project already derives. It renders every
listing on one of seven rungs, the whole lead table, the naming audit and the
open logo/email gaps -- then streams a `sample_` cut so a proof can be watched
without hunting for the file.

It writes nothing. No file, no CSV row, no marker. Every mutation stays behind
tour.py's prompts, where a human is asked once, every time -- see
_rules/the-dashboard-reads-it-never-writes.md.

Two entry points, one behaviour:

    python3 dashboard.py [--port N] [--no-browser]
    python3 tour.py      -> 6. Open the dashboard

Stdlib only, like the rest of the repo. It binds to 127.0.0.1 and renders in
memory: the page carries agent names, phone numbers and email addresses in
full, and the loopback bind is the only thing between that and the LAN.

The seven rungs, highest first, first match wins -- so a listing is on exactly
one of them and rung 6 can never double-count rung 5:

    7 delivered      a tour_ cut exists            tour.stage()
    6 follow-up due  contacted, window elapsed     status.followup_due()
    5 contacted      contacted, still snoozed      status.contacted()
    4 published      a links.csv row               status.published()
    3 sample built   out/ holds a sample_ cut      tour.sample_cuts()
    2 ready to build everything else
    1 unimported     a dump with no folder yet     tour.unimported_dumps()

There is no eighth rung. "Signed off" has no derivable signal, and
_rules/needs-attention-is-a-view-not-a-move.md forbids inventing one -- a
tour_ cut already stands in for signed-off-and-delivered.

Only `sample_` cuts are ever served. publish.family() is asked before the
filesystem is touched, so a tour_ request is 403 whether or not the file is
there: a local URL becomes a publishing boundary the moment it is pasted or
the screen is shared.
"""

import html
import http.server
import importlib.util
import mimetypes
import os
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.abspath(__file__))
AGENTS = os.path.join(ROOT, "agents")

# reason: never the empty string and never a wildcard bind. This page
# renders every lead's name, phone and email in full; the loopback bind is
# the only thing standing between that and every other machine on the network.
HOST = "127.0.0.1"
PORT = 8765

MEDIA_PREFIX = "/media/"
CHUNK = 64 * 1024

# parse_range()'s third answer: the header parsed, and asks for bytes that do
# not exist. Distinct from None, which means "no usable range -- serve 200".
UNSATISFIABLE = "unsatisfiable"

RUNGS = (
    (1, "Unimported", "a dump in scraper/dumps/ with no listing folder yet"),
    (2, "Ready to build", "scaffolded, nothing in out/ yet"),
    (3, "Sample built", "sample_ cuts waiting on review and a publish"),
    (4, "Published", "on the CDN, no email marked sent yet"),
    (5, "Contacted", "emailed, still inside the follow-up window"),
    (6, "Follow-up due", "emailed, the window has elapsed"),
    (7, "Delivered", "a tour_ cut exists"),
)


# ---- the modules this reads, loaded once, injectable ------------------------

def _module(name, relpath):
    """Import a repo script by path, once, under its own name.

    reason: the same spec/sys.modules/exec_module dance tests/helpers.py uses.
    Loading by path rather than by `import status` means the dashboard works
    from any cwd, which `python3 dashboard.py` from a listing folder needs.
    """
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, relpath))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _scraper_module(name):
    """A scraper/ module, with scraper/ on the path -- find_gaps.py imports
    photos.py as a flat sibling, so the folder itself has to be importable."""
    scraper = os.path.join(ROOT, "scraper")
    if scraper not in sys.path:
        sys.path.insert(0, scraper)
    import importlib
    return importlib.import_module(name)


class Sources:
    """Every fact the dashboard reads, bound onto one object a test can swap.

    reason: status.AGENTS, tour.LISTINGS_ROOT and publish.LINKS are all
    resolved from the real repo root at import time and cannot be pointed at a
    sandbox afterwards. Binding the callables here is the same dependency
    injection active_view.rebuild() and prospects.rebuild() already use when
    they take rows/agents_dir/dest_dir as arguments instead of reading their
    own module constants. Nothing below is imported until a Sources() is
    actually built, so `import dashboard` stays free.
    """

    def __init__(self, status=None, tour=None, publish=None, find_gaps=None,
                 lead=None, agents_dir=None):
        status = status or _module("status", "status.py")
        tour = tour or _module("tour", "tour.py")
        publish = publish or _module("publish", "publish.py")
        find_gaps = find_gaps or _scraper_module("find_gaps")
        lead = lead or _scraper_module("lead")

        self.agents_dir = agents_dir or AGENTS
        self.survey = status.survey
        self.audit = status.audit
        self.published = status.published
        self.contacted = status.contacted
        self.followup_due = status.followup_due
        self.stage = tour.stage
        self.sample_cuts = tour.sample_cuts
        self.unimported_dumps = tour.unimported_dumps
        self.family = publish.family
        self.recorded_link = publish.recorded_link
        self.contacted_at = publish.contacted_at
        self.follow_up_date = publish.follow_up_date
        self.brand_gaps = find_gaps.brand_gaps
        self.email_gaps = find_gaps.email_gaps
        self.load_leads = find_gaps.load_leads
        self.css = lead.CSS
        self.lead_fields = lead.CSV_FIELDS


# ---- the rung ladder ---------------------------------------------------------

def rung(delivered, followup, contacted, published, has_sample):
    """Exactly one rung per listing. Ordered, never summed.

    reason: publish.followup_due() already IMPLIES contacted -- it reads
    contacted_at() and compares against FOLLOW_UP_DAYS. Testing 6 before 5 is
    what turns them into a partition instead of a double count, so rung 5 reads
    "contacted, do nothing yet" and rung 6 reads "actually due". A lead that
    appeared under both is a lead that gets emailed twice. 7 sits above 6 for
    the same reason: a delivered listing is not chased.
    """
    if delivered:
        return 7
    if followup:
        return 6
    if contacted:
        return 5
    if published:
        return 4
    if has_sample:
        return 3
    return 2


def _safe(fn, *args, default=None):
    """Call a source and swallow its failure.

    reason: status._publish is loaded guarded and may be None, leads.csv may
    not exist, and a half-scaffolded folder may have no out/. One broken
    listing must degrade to a missing field, never take the whole page down --
    the same tolerance status.published()/contacted() already apply one level
    down, and the same reason tour.py's home screen still offers item 1 when
    the roll-up cannot load.
    """
    try:
        return fn(*args)
    except Exception:
        return default


def _listing(src, row):
    """One listing's facts, already on its rung, ready to render."""
    brand, listing, agent, n, worst, best, action, _bcfg, cfg = row
    d = os.path.join(src.agents_dir, brand, listing, agent)
    on_disk = os.path.isdir(d)
    cuts = _safe(src.sample_cuts, d, default=[]) or [] if on_disk else []
    delivered = on_disk and _safe(src.stage, d) == "delivered"
    marked = _safe(src.contacted_at, brand, listing, agent)
    return {
        "brand": brand, "listing": listing, "agent": agent,
        "photos": n, "worst": worst, "best": best, "action": action,
        "agent_name": (cfg or {}).get("agent_name", ""),
        "agent_phone": (cfg or {}).get("agent_phone", ""),
        "agent_email": (cfg or {}).get("agent_email", ""),
        "address": (cfg or {}).get("address", ""),
        "cuts": sorted(cuts),
        "link": _safe(src.recorded_link, brand, listing, agent),
        "contacted_at": marked,
        "follow_up": _safe(src.follow_up_date, marked) if marked else None,
        "on_disk": on_disk,
        "rung": rung(
            delivered,
            bool(_safe(src.followup_due, brand, listing, agent, default=False)),
            bool(_safe(src.contacted, brand, listing, agent, default=False)),
            bool(_safe(src.published, brand, listing, default=False)),
            bool(cuts),
        ),
    }


def collect(src):
    """The whole page's data, in memory. Reads; never writes."""
    rows, truth, known = _safe(src.survey, default=([], {}, set()))
    drift, unverifiable, orphans = _safe(
        src.audit, rows, truth, known, default=([], [], []))

    buckets = {n: [] for n, _label, _hint in RUNGS}
    for row in rows:
        item = _listing(src, row)
        buckets[item["rung"]].append(item)

    for name, brand, listing, agent in _safe(src.unimported_dumps,
                                             default=[]) or []:
        buckets[1].append({"dump": name, "brand": brand, "listing": listing,
                           "agent": agent, "rung": 1})

    leads = _safe(src.load_leads, default=[]) or []
    return {
        "rungs": buckets,
        "leads": leads,
        "lead_fields": list(src.lead_fields),
        "drift": drift or [],
        "unverifiable": unverifiable or [],
        "orphans": orphans or [],
        "logo_gaps": _safe(src.brand_gaps, leads, src.agents_dir,
                           default=[]) or [],
        "email_gaps": _safe(src.email_gaps, leads, src.agents_dir,
                            default=[]) or [],
    }


# ---- the page ----------------------------------------------------------------

# On top of scraper/lead.py's CSS, which is the house style for every page this
# project generates. Tokens are inherited, never redeclared.
EXTRA_CSS = """
  header.top { display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; }
  .pills { margin: 14px 0 4px; display: flex; gap: 8px; flex-wrap: wrap; }
  .pills a { text-decoration: none; font-size: 12px; padding: 4px 10px;
             border: 1px solid var(--border); border-radius: 999px;
             background: var(--head-bg); color: var(--fg); }
  h2 { font-size: 15px; margin: 30px 0 4px; }
  h2 .hint { font-weight: 400; opacity: .6; font-size: 12px; }
  .card { border: 1px solid var(--border); border-radius: 8px;
          padding: 12px 14px; margin: 10px 0; background: var(--row-alt); }
  .card h3 { font-size: 14px; margin: 0 0 2px; }
  .path { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px;
          opacity: .7; }
  .facts { display: grid; gap: 2px 20px; margin: 10px 0 0; font-size: 13px;
           grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); }
  .facts b { font-weight: 600; }
  .next { margin: 8px 0 0; font-size: 13px; }
  video { display: block; width: 100%; max-width: 560px; margin: 10px 0 0;
          border-radius: 6px; background: #000; }
  .cut { font-size: 12px; opacity: .7; margin: 8px 0 0; }
  .empty { opacity: .55; font-style: italic; font-size: 13px; }
  .warn { border-left: 3px solid #c0392b; padding-left: 10px; }
"""


def _e(value):
    """Every interpolated value goes through this. No exceptions."""
    return html.escape("" if value is None else str(value))


def _media_url(brand, listing, agent, name):
    quote = urllib.parse.quote
    return MEDIA_PREFIX + "/".join(
        quote(p, safe="") for p in (brand, listing, agent, name))


def _table(headers, rows):
    if not rows:
        return '<p class="empty">Nothing here.</p>'
    head = "".join("<th>" + _e(h) + "</th>" for h in headers)
    body = "\n".join(
        "<tr>" + "".join("<td>" + _e(c) + "</td>" for c in r) + "</tr>"
        for r in rows)
    return ('<div class="wrap"><table><thead><tr>' + head +
            "</tr></thead><tbody>\n" + body + "\n</tbody></table></div>")


def _card(item):
    if item["rung"] == 1:
        return ('<div class="card"><h3>' + _e(item["dump"]) + "</h3>"
                '<p class="path">scraper/dumps/ -> agents/' +
                _e("/".join((item["brand"], item["listing"], item["agent"]))) +
                "</p></div>")

    title = item["address"] or item["listing"].replace("_", " ")
    facts = [("Agent", item["agent_name"]), ("Phone", item["agent_phone"]),
             ("Email", item["agent_email"] or "-- not filled in"),
             ("Photos", item["photos"]),
             ("Smallest", str(item["worst"]) + "px" if item["worst"] else "--"),
             ("Contacted", item["contacted_at"] or "--"),
             ("Follow-up", item["follow_up"] or "--")]
    out = ['<div class="card"><h3>' + _e(title) + "</h3>",
           '<p class="path">agents/' +
           _e("/".join((item["brand"], item["listing"], item["agent"]))) +
           "</p>",
           '<div class="facts">']
    for label, value in facts:
        out.append("<div><b>" + _e(label) + ":</b> " + _e(value) + "</div>")
    out.append("</div>")
    out.append('<p class="next"><b>Next:</b> ' + _e(item["action"]) + "</p>")
    if item["link"]:
        out.append('<p class="next"><a href="' + _e(item["link"]) +
                   '">' + _e(item["link"]) + "</a></p>")
    for name in item["cuts"]:
        url = _media_url(item["brand"], item["listing"], item["agent"], name)
        out.append('<video controls preload="metadata" src="' + _e(url) +
                   '"></video>')
        out.append('<p class="cut">' + _e(name) + "</p>")
    out.append("</div>")
    return "\n".join(out)


def render(data):
    """The whole page as one string. Never touches the filesystem."""
    total = sum(len(v) for v in data["rungs"].values())
    pills = "".join(
        '<a href="#rung-' + str(n) + '">' + str(n) + ". " + _e(label) +
        " (" + str(len(data["rungs"][n])) + ")</a>"
        for n, label, _hint in RUNGS)

    parts = ['<header class="top"><h1>Listings (' + str(total) + ")</h1></header>",
             '<div class="pills">' + pills + "</div>"]

    for n, label, hint in RUNGS:
        items = data["rungs"][n]
        parts.append('<h2 id="rung-' + str(n) + '">' + str(n) + ". " +
                     _e(label) + ' <span class="hint">' + _e(hint) + " &middot; " +
                     str(len(items)) + "</span></h2>")
        if not items:
            parts.append('<p class="empty">Nothing on this rung.</p>')
            continue
        parts.extend(_card(i) for i in items)

    parts.append('<h2 id="leads">Leads (' + str(len(data["leads"])) + ")</h2>")
    fields = data["lead_fields"]
    parts.append(_table(fields,
                        [[row.get(f, "") for f in fields]
                         for row in data["leads"]]))

    # reason: status.audit() returns 4-tuples, not the 3-strings-and-a-pair this
    # renderer first assumed -- drift is (brand, listing, agent, want) where want
    # is itself a triple, and unverifiable is (brand, listing, agent, bool(cfg)).
    # Both tables crashed the page the first time either list was non-empty, and
    # neither was reachable until a folder with no lead row appeared, because the
    # real tree had an empty audit and FakeSources defaulted all three to ().
    parts.append('<h2 id="audit">Audit</h2>')
    parts.append("<h3>Naming drift</h3>")
    parts.append(_table(["current", "should be"],
                        [["/".join(d[:3]), "/".join(d[3])]
                         for d in data["drift"]]))
    parts.append("<h3>Unverifiable -- no lead row behind the folder</h3>")
    parts.append(_table(["folder", "scaffolded"],
                        [["/".join(u[:3]), "yes" if u[3] else "no"]
                         for u in data["unverifiable"]]))
    parts.append("<h3>Orphaned contacted.csv rows</h3>")
    parts.append(_table(["brand", "listing", "agent"],
                        [list(o) for o in data["orphans"]]))

    parts.append('<h2 id="gaps">Gaps</h2>')
    parts.append("<h3>Brand logos</h3>")
    parts.append(_table(["brand", "brokerage", "status", "candidate"],
                        [[g.get("brand"), g.get("broker_name"),
                          g.get("status"), g.get("candidate") or "--"]
                         for g in data["logo_gaps"]]))
    parts.append("<h3>Agent emails</h3>")
    parts.append(_table(["brand", "listing", "agent", "agent name"],
                        [[g.get("brand"), g.get("listing"), g.get("agent"),
                          g.get("agent_name")] for g in data["email_gaps"]]))

    css = data.get("css", "")
    return ("<!doctype html>\n<html>\n<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            "<title>Tour dashboard</title>\n<style>\n" + css + EXTRA_CSS +
            "</style>\n</head>\n<body>\n" + "\n".join(parts) +
            "\n</body>\n</html>\n")


# ---- the socket --------------------------------------------------------------

def resolve_media(path, agents_dir, family):
    """(status_code, abspath|None) for a /media/ request. Fails closed.

    The order is deliberate. A traversal attempt is refused before anything is
    read, and publish.family() is asked before the filesystem is touched at
    all -- so a tour_ request is 403 whether or not that file exists, and the
    403-vs-404 difference never leaks which deliverables are on disk.
    family() stays the single owner of the sample_/tour_ boundary; the prefix
    is never tested here (see _rules/only-sample-cuts-publish.md).
    """
    rel = urllib.parse.unquote(path[len(MEDIA_PREFIX):])
    parts = rel.split("/")
    if "\\" in rel or any(p in ("", ".", "..") for p in parts):
        return 403, None
    if len(parts) != 4:
        return 404, None
    brand, listing, agent, name = parts
    if family(name) != "sample":
        return 403, None
    base = os.path.realpath(agents_dir)
    full = os.path.realpath(
        os.path.join(base, brand, listing, agent, "out", name))
    # realpath resolves ".." and symlinks both, so one check catches an encoded
    # traversal that slipped a segment test and a symlink pointing out of the
    # tree. The separator matters: /agents-backup must not pass as /agents.
    if full != base and not full.startswith(base + os.sep):
        return 403, None
    if not os.path.isfile(full):
        return 404, None
    return 200, full


def parse_range(header, size):
    """RFC 7233 single byte range -> (start, end) inclusive.

    None      -- no usable range; serve the whole file with 200.
    UNSATISFIABLE -- syntactically fine, asks for bytes that do not exist; 416.

    A malformed header is ignored rather than rejected, which is what RFC 7233
    requires: only a well-formed byte-range-set that cannot be satisfied earns
    a 416. Multiple ranges are ignored too -- we do not write multipart.
    """
    if not header:
        return None
    value = header.strip()
    if not value.lower().startswith("bytes="):
        return None
    spec = value[len("bytes="):].strip()
    if "," in spec or "-" not in spec:
        return None
    first, _, last = spec.partition("-")
    first, last = first.strip(), last.strip()
    try:
        if not first:
            suffix = int(last)
            if suffix <= 0 or size == 0:
                return UNSATISFIABLE
            return max(0, size - suffix), size - 1
        start = int(first)
        end = int(last) if last else size - 1
    except ValueError:
        return None
    if start < 0 or size == 0 or start >= size or end < start:
        return UNSATISFIABLE
    return start, min(end, size - 1)


def content_type(path):
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    """Four routes, and a gate ladder in front of the only one that reads bytes."""

    sources = None
    server_version = "tour-dashboard"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        """Silence. reason: this shares a console with tour.py's roll-up, and a
        request line per video chunk would bury it -- with folder names in it."""

    def do_GET(self):
        self._route(body=True)

    def do_HEAD(self):
        self._route(body=False)

    def _refuse(self):
        self.send_error(405, "Only GET and HEAD")

    do_POST = do_PUT = do_DELETE = do_PATCH = _refuse

    def _route(self, body):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._page(body)
        if path == "/favicon.ico":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        if path.startswith(MEDIA_PREFIX):
            return self._media(path, body)
        self.send_error(404)
        return None

    def _page(self, body):
        data = collect(self.sources)
        data["css"] = self.sources.css
        payload = render(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        # reason: the page is derived state and nothing else. A cached copy is
        # a stale answer to "what is waiting on me", which is the whole point.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self._write(payload)

    def _media(self, path, body):
        code, full = resolve_media(path, self.sources.agents_dir,
                                   self.sources.family)
        if code != 200:
            self.send_error(code)
            return
        size = os.path.getsize(full)
        wanted = parse_range(self.headers.get("Range"), size)
        if wanted is UNSATISFIABLE:
            self.send_response(416)
            self.send_header("Content-Range", "bytes */" + str(size))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if wanted is None:
            start, end = 0, size - 1
            self.send_response(200)
        else:
            start, end = wanted
            self.send_response(206)
            self.send_header("Content-Range",
                             "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Content-Type", content_type(full))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(max(0, end - start + 1)))
        self.end_headers()
        if body:
            self._stream(full, start, end)

    def _write(self, payload):
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _stream(self, full, start, end):
        remaining = end - start + 1
        try:
            with open(full, "rb") as f:
                f.seek(start)
                while remaining > 0:
                    block = f.read(min(CHUNK, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)
        except (BrokenPipeError, ConnectionResetError):
            # reason: a browser scrubbing a video abandons the socket mid-write
            # on every seek. A traceback per seek would bury the console.
            pass


def make_server(port=PORT, sources=None, host=HOST):
    """A bound, unstarted server. Falls back to an ephemeral port if taken."""
    handler = type("BoundDashboardHandler", (DashboardHandler,),
                   {"sources": sources or Sources()})
    try:
        httpd = http.server.ThreadingHTTPServer((host, port), handler)
    except OSError:
        httpd = http.server.ThreadingHTTPServer((host, 0), handler)
    httpd.daemon_threads = True
    return httpd


def serve(port=PORT, open_browser=True, sources=None, host=HOST):
    """Bind, announce, optionally open a browser, and block until Ctrl-C."""
    httpd = make_server(port, sources, host)
    url = "http://%s:%d/" % (host, httpd.server_address[1])
    print("  Dashboard on " + url)
    print("  Read-only. Real phone numbers and emails -- not for screen-share.")
    print("  Ctrl-C to stop.")
    if open_browser:
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard stopped.")
    finally:
        httpd.server_close()
    return url


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="Read-only view of the leads and "
                                            "listings. Writes nothing.")
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args(argv)
    serve(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
