#!/usr/bin/env python3
"""
lead.py

Parses a raw Zillow HDP page-text dump (the __NEXT_DATA__ blob you copy/paste,
which comes through with backslash-escaped JSON quotes, e.g.
\\"agentName\\":\\"Jane Doe\\" -- a made-up name; no real lead data belongs
in this repo) and prints a clean lead report:
property summary, listing agent (name/phone/brokerage/MLS ID/email), and who
actually receives the lead if the Contact Agent button is clicked (may differ
from the listing agent on Premier Agent ad slots). Also appends a row to
leads.csv and regenerates leads.html, a browser-viewable table of all leads.
leads.html carries two derived columns, first in the table: CONTACTED, reading
"contacted" or "open", and FOLLOW UP, a date FOLLOW_UP_DAYS after the row's
outreach/contacted.csv timestamp (blank until contacted). Both are joined
against outreach/contacted.csv by slugifying each row the same way
scraper/photos.py's target_for() already names its folder, so the table and
agents/ can never disagree about which lead a row is (see
lead._load_photos()'s docstring for why that reuse has to stay a lazy,
function-scoped load rather than a module-level import of photos.py). The
agent_email column is likewise overridden from that listing's config.json
when set, since Zillow does not always expose one at scrape time.

Usage:
    python3 lead.py paste.txt
    python3 lead.py paste.txt --full     # also writes beautified.txt
"""

import re
import argparse
import csv
import datetime
import html
import json
import os
import sys

CSV_FIELDS = [
    "address", "zip", "city", "state", "price", "beds", "baths", "zpid",
    "status", "type", "agent_name", "agent_email", "agent_phone",
    "broker_name", "mls_id", "contact_role", "contact_name",
]

# Keys long/unique enough that inserting a newline before them won't
# accidentally slice through the middle of an unrelated word.
SAFE_KEYS = [
    "agentName", "agentEmail", "agentPhoneNumber", "brokerName", "mlsId", "mlsName",
    "listingAttributionContact", "notMLSSourcedListing", "displayname", "businessname",
    "badgetype", "phoneareacode", "profileurl", "ratingaverage", "recentsales",
    "reviewcount", "streetAddress", "zipcode", "homeType", "homeStatus", "zpid",
    "listingsubtype", "isFSBA", "isFSBO", "premieragent", "agentreason",
    "listingTypeDimension", "hdpTypeDimension", "attributionInfo", "contactrecipients",
    "displayedagents", "contactFormRenderData", "encodedzuid", "firstname",
]


def field(text: str, key: str):
    """
    Find `key` and pull the value that follows it, tolerating the
    backslash-escaped JSON punctuation (\\":\\") the real dumps use between
    a key and its value. Returns None for both "not found" and a literal
    JSON null.

    The trailing (?![A-Za-z0-9_]) is required so a short key like "price"
    or "city" can't match as a prefix of a longer, unrelated key that
    happens to appear earlier in the dump (e.g. "price_band", "...Capacity").
    """
    m = re.search(re.escape(key) + r'(?![A-Za-z0-9_])[\\"\s:]*(null|[^\\",]*)', text)
    if not m:
        return None
    val = m.group(1).strip()
    return None if val in ("", "null") else val


def extract_zip_city_state(text: str):
    """
    "city" is too generic a key to search for on its own -- dumps also
    contain an earlier, unrelated "city" field from analytics/tracking data
    (e.g. a slugified "South_Boston" vs. the real address's "South Boston"),
    and a lone field() search grabs whichever occurs first. Anchoring the
    match to the contiguous zipcode -> city -> state sequence in the actual
    address block avoids that.
    """
    m = re.search(
        r'zipcode(?![A-Za-z0-9_])[\\"\s:]*(\d+)'
        r'[\\"\s:,]*city(?![A-Za-z0-9_])[\\"\s:]*([^\\",]*)'
        r'[\\"\s:,]*state(?![A-Za-z0-9_])[\\"\s:]*([A-Z]{2})',
        text
    )
    if m:
        zip_, city, state = m.groups()
        return zip_ or None, city.strip() or None, state
    return field(text, "zipcode"), field(text, "city"), field(text, "state")


def extract_property(text: str) -> dict:
    zip_, city, state = extract_zip_city_state(text)
    return {
        "address": field(text, "streetAddress"),
        "zip": zip_,
        "city": city,
        "state": state,
        "price": field(text, "price"),
        "beds": field(text, "bedrooms"),
        "baths": field(text, "bathrooms"),
        "zpid": field(text, "zpid"),
        "status": field(text, "homeStatus"),
        "type": field(text, "homeType"),
    }


def extract_listing_agent(text: str) -> dict:
    return {
        "agent_name": field(text, "agentName"),
        "agent_email": field(text, "agentEmail"),
        "agent_phone": field(text, "agentPhoneNumber"),
        "broker_name": field(text, "brokerName"),
        "mls_id": field(text, "mlsId"),
        "mls_name": field(text, "mlsName"),
    }


def extract_contact_button_agent(text: str) -> dict:
    """
    Whoever this returns is who actually gets the lead if the Contact Agent
    button is clicked -- may or may not be the same person as the listing
    agent above (Premier Agent ad slots can intercept it).
    """
    m = re.search(
        r'badgetype[\\"\s:]*(Premier Agent|Listing Agent)'
        r'.*?businessname[\\"\s:]*([A-Za-z0-9 &\'\.\-]+?)(?=\\?["\\]*,?\\?"?displayname)'
        r'.*?displayname[\\"\s:]*([A-Za-z .\-]+?)(?=\\?["\\]*,?\\?"?encodedzuid)',
        text
    )
    if not m:
        return {"role": None, "business": None, "name": None}
    role, business, name = m.groups()
    return {"role": role, "business": business.strip(), "name": name.strip()}


# The house style for every page this project generates -- scraper/leads.html
# below and dashboard.py's one page. One definition, so a token added to one
# cannot be missing from the other.
CSS = """  :root {
    --bg: #ffffff; --fg: #1a1a1a; --border: #d8dce1;
    --head-bg: #f1f3f5; --row-alt: #f8f9fa; --row-hover: #eef4ff;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #14171a; --fg: #e6e6e6; --border: #33383e;
      --head-bg: #1f2428; --row-alt: #191c1f; --row-hover: #24303d;
    }
  }
  body { background: var(--bg); color: var(--fg); font-family: -apple-system, Helvetica, Arial, sans-serif;
          margin: 24px; }
  h1 { font-size: 18px; margin: 0 0 12px; }
  .wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; }
  table { border-collapse: collapse; width: 100%; white-space: nowrap; font-size: 13px; }
  th, td { padding: 8px 12px; border-bottom: 1px solid var(--border); text-align: left; }
  th { background: var(--head-bg); position: sticky; top: 0; font-weight: 600; }
  tbody tr:nth-child(even) { background: var(--row-alt); }
  tbody tr:hover { background: var(--row-hover); }
"""


def _brace_escape(css):
    """CSS ready to drop into a str.format() template.

    reason: HTML_TEMPLATE is consumed by .format(), so every literal brace in it
    has to be doubled -- while dashboard.py concatenates its page and wants them
    single. Doubling here keeps CSS itself valid, readable and singular.
    """
    return css.replace("{", "{{").replace("}", "}}")


HTML_TEMPLATE = ("""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Leads</title>
<style>
""" + _brace_escape(CSS) + """</style>
</head>
<body>
<h1>Leads ({count})</h1>
<div class="wrap">
<table>
<thead><tr>{header}</tr></thead>
<tbody>
{body}
</tbody>
</table>
</div>
</body>
</html>
""")


def normalize_phone(phone):
    digits = re.sub(r'\D', '', phone or "")
    return digits or None


def find_duplicate(csv_path: str, row: dict):
    """
    A row is a duplicate of an existing one if it's the same property
    (zpid) AND the same listing agent (agent_phone). Address text is too
    fragile to key on (formatting varies), and zpid alone is too broad --
    the same property can get relisted later by a different agent/brokerage,
    which is a genuinely new lead, not a duplicate.

    zpid is required to make a call either way: without it there's no
    reliable property identity to compare, so treat the row as new.
    """
    if not row.get("zpid") or not os.path.isfile(csv_path):
        return None

    row_phone = normalize_phone(row.get("agent_phone"))
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        for existing in csv.DictReader(f):
            if existing.get("zpid") != row["zpid"]:
                continue
            if normalize_phone(existing.get("agent_phone")) == row_phone:
                return existing
    return None


def duplicate_banner(csv_path: str, row: dict) -> str:
    """The loud, three-line message printed when find_duplicate() has a hit."""
    banner = (f"{row['address']} -- {row['agent_name']} already in {csv_path} "
              f"(zpid {row['zpid']}, same listing agent phone). Nothing appended.")
    rule = "=" * max(60, len(banner))
    return f"{rule}\nDUPLICATE -- SKIPPED\n{banner}\n{rule}"


def _load_photos():
    """scraper/photos.py, or None -- the one place slugify()/UNASSIGNED_AGENT
    live, borrowed here rather than kept as a third slug function (see
    two-slug-functions-one-apostrophe-rule.md).

    reason: photos.py imports FROM lead.py (`from lead import field,
    extract_zip_city_state`), so this load has to stay lazy and
    function-scoped -- called only from write_html_table(), after lead.py
    has already finished defining field()/extract_zip_city_state() at
    import time. A module-level call here would re-enter this same file
    under the name "lead" (photos.py's import triggers a fresh load, since
    lead.py never runs under that name itself) before those functions exist
    on it yet, and crash on the very first run.
    """
    try:
        import importlib.util
        script_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(script_dir, "photos.py")
        spec = importlib.util.spec_from_file_location("_photos_for_lead", path)
        mod = importlib.util.module_from_spec(spec)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


CONTACTED_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "outreach", "contacted.csv")

AGENTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents")

FOLLOW_UP_DAYS = 5


def _contacted_marked_at():
    """{(brand, listing, agent): marked_at} from outreach/contacted.csv.

    reason: publish.py owns writing this file (record_contacted()), but
    publish.py itself loads scraper/photos.py for jpeg_size -- importing
    publish.py from here would load photos.py a second time through that
    path, the same cycle _load_photos()'s docstring avoids. Reading the
    documented columns (marked_at,brand,listing,agent) directly needs no
    import and invents no second writer for the file. Keyed by marked_at
    rather than a bare set of keys so the derived follow-up column below can
    compute FOLLOW_UP_DAYS from the actual timestamp, not just membership.
    """
    if not os.path.isfile(CONTACTED_CSV):
        return {}
    try:
        with open(CONTACTED_CSV, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return {}
    return {(r.get("brand", "").strip(), r.get("listing", "").strip(),
             r.get("agent", "").strip()): r.get("marked_at", "").strip()
            for r in rows}


def _follow_up_date(marked_at):
    """marked_at + FOLLOW_UP_DAYS, as YYYY-MM-DD -- "" if marked_at cannot be
    parsed (a hand-edited row, a test fixture), never the reason the page
    fails to render.
    """
    try:
        when = datetime.datetime.fromisoformat(marked_at)
    except (TypeError, ValueError):
        return ""
    return (when + datetime.timedelta(days=FOLLOW_UP_DAYS)).strftime("%Y-%m-%d")


def _agent_email_override(key):
    """config.json's agent_email for agents/<brand>/<listing>/<agent>/, or ""

    reason: Zillow does not always expose an agentEmail -- lead.py's own
    docstring already says so of agent_phone -- and re-scraping is not always
    possible. A human who finds the address by other means can fill it in on
    the listing's own config.json (never brand.json -- see
    brand-json-carries-no-agent-identity.md) and have it show here, without
    hand-editing the append-only leads.csv this table mirrors.
    """
    path = os.path.join(AGENTS_DIR, *key, "config.json")
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return ""
    return (cfg.get("agent_email") or "").strip()


def write_html_table(csv_path: str, html_path: str) -> None:
    """Mirror leads.csv as a real, styled HTML table -- open leads.html in a browser.

    Adds three derived columns, joined against outreach/contacted.csv and the
    listing's own config.json by slugifying broker_name/address/agent_name the
    same way scraper/photos.py's target_for() already names the folder for
    this row -- so this table and agents/ can never disagree about which lead
    a row is:
      * CONTACTED -- "contacted" once outreach/contacted.csv has a row,
        "open" until then. reason: the column is a state of the OUTREACH, not
        of the lead. A scraped-months-ago listing still awaiting its first
        email is not "new" -- calling it that read as "nothing has happened
        here yet" on rows where plenty had.
      * FOLLOW UP -- FOLLOW_UP_DAYS after that row's marked_at, blank until
        contacted.
      * agent_email -- overridden by config.json's own agent_email when set,
        since Zillow does not always expose one at scrape time.
    """
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    photos = _load_photos()
    marked = _contacted_marked_at()
    header = "<th>contacted</th><th>follow up</th>"
    header += "".join(f"<th>{html.escape(key)}</th>" for key in CSV_FIELDS)
    body_lines = []
    for row in rows:
        is_contacted = False
        follow_up = ""
        if photos is not None:
            key = (photos.slugify(row.get("broker_name"), "unknown_brokerage"),
                   photos.slugify(row.get("address")),
                   photos.slugify(row.get("agent_name"), photos.UNASSIGNED_AGENT))
            marked_at = marked.get(key)
            is_contacted = marked_at is not None
            if is_contacted:
                follow_up = _follow_up_date(marked_at)
            email = _agent_email_override(key)
            if email:
                row = dict(row, agent_email=email)
        cells = f"<td>{'contacted' if is_contacted else 'open'}</td>"
        cells += f"<td>{html.escape(follow_up)}</td>"
        cells += "".join(f"<td>{html.escape(row.get(key) or '')}</td>" for key in CSV_FIELDS)
        body_lines.append(f"<tr>{cells}</tr>")

    page = HTML_TEMPLATE.format(count=len(rows), header=header, body="\n".join(body_lines))
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(page)


def beautify(text: str, keys=None) -> str:
    """Insert a newline before every occurrence of a known field key."""
    keys = keys or SAFE_KEYS
    keys_sorted = sorted(keys, key=len, reverse=True)
    pattern = re.compile(r'(?<![A-Za-z])(' + '|'.join(re.escape(k) for k in keys_sorted) + r')')
    return pattern.sub(r'\n\1: ', text)


def main():
    parser = argparse.ArgumentParser(description="Extract listing agent + property info from a Zillow HDP dump.")
    parser.add_argument("file", help="Path to the pasted Zillow page text file")
    parser.add_argument("--full", action="store_true", help="Also write a full beautified.txt")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "leads.csv")
    html_path = os.path.join(script_dir, "leads.html")

    with open(args.file, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    prop = extract_property(text)
    agent = extract_listing_agent(text)
    contact = extract_contact_button_agent(text)

    # reason: a dump with no zpid is not a listing page -- an empty file, a
    # half-copied paste, or the wrong tab. Parsing one yields a row of Nones,
    # and because find_duplicate() needs a zpid to compare it cannot recognise
    # the row as a duplicate either, so every rerun appends another. Left
    # unguarded this exits 0, so a batch run reports it as processed cleanly
    # while poisoning leads.csv -- which is also the naming authority. Refuse
    # here, before anything is written.
    if not prop["zpid"]:
        print(f"{args.file}: no zpid -- this is not a Zillow listing dump. "
              f"Nothing written.")
        sys.exit(2)

    print(f"{prop['address']}, {prop['city']}, {prop['state']} {prop['zip']}")
    print(f"  ${int(prop['price']):,}" if prop['price'] else "  price: n/a",
          f"| {prop['beds']}bd/{prop['baths']}ba | {prop['type']} | {prop['status']}")
    print()
    print(f"Agent name: {agent['agent_name']}")
    print(f"Phone: {agent['agent_phone']}")
    print(f"Brokerage: {agent['broker_name']}")
    print(f"MLS ID: {agent['mls_id']}")
    print(f"Email: {agent['agent_email']}")
    print()
    print("Contact-button recipient:")
    if contact["role"] == "Listing Agent":
        print(f"  {contact['name']} -- SAME as listing agent (goes to the right person)")
    elif contact["role"] == "Premier Agent":
        print(f"  {contact['name']} ({contact['business']}) -- PREMIER AGENT AD, not the listing agent")
    else:
        print("  not found")

    row = {
        **prop,
        "agent_name": agent["agent_name"],
        "agent_email": agent["agent_email"],
        "agent_phone": agent["agent_phone"],
        "broker_name": agent["broker_name"],
        "mls_id": agent["mls_id"],
        "contact_role": contact["role"],
        "contact_name": contact["name"],
    }
    print()
    dup = find_duplicate(csv_path, row)
    if dup:
        print(duplicate_banner(csv_path, row))
    else:
        file_exists = os.path.isfile(csv_path)
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
        print(f"Appended to {csv_path}")

    write_html_table(csv_path, html_path)

    # reason: a duplicate is not a failure (exit 2 is reserved for "not a
    # listing dump" above) but it is not a success either -- run.py needs a
    # third signal to keep the two apart in a batch summary.
    if dup:
        sys.exit(3)
    print(f"Updated {html_path}")

    if args.full:
        out_path = os.path.join(script_dir, "beautified.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(beautify(text))
        print(f"Full beautified dump written to {out_path}")


if __name__ == "__main__":
    main()
