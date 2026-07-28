#!/usr/bin/env python
"""
Download a text from zh.wikisource.org into translations/<slug>/raw/.

Adapted from religions-history/scripts/download-wikisource.py. Differences:
zh only, catalog uses `category` not `religion`, meta.json carries text_role
and an empty psych_survey slot, and phase filtering defers the 小學 batch.

Usage:
    PYTHONIOENCODING=utf-8 python scripts/download-wikisource.py --slug sunzi-bingfa
    PYTHONIOENCODING=utf-8 python scripts/download-wikisource.py --category 兵家
    PYTHONIOENCODING=utf-8 python scripts/download-wikisource.py --all --limit 5
"""

import argparse
import hashlib
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = ROOT / "scripts" / "catalog"
TRANSLATIONS_DIR = ROOT / "translations"

WS_API = "https://zh.wikisource.org/w/api.php"
USER_AGENT = (
    "chinese-classics-corpus/0.1 (academic research; "
    "contact: psyhangsau@gmail.com; "
    "+https://github.com/Hangsau/chinese-classics-corpus)"
)
REQ_TIMEOUT = 30
SLEEP_BETWEEN_REQUESTS = 0.5
MAX_RETRIES = 5
BACKOFF_INITIAL = 10.0

_polite_req_count = 0
_LONG_PAUSE_EVERY = 100
_LONG_PAUSE_SECONDS = 30.0

# 全文/全覽 pages duplicate the whole book alongside its per-chapter subpages.
META_SUBPAGE_SUFFIXES = ("/全覽", "/全文", "/目錄", "/目录", "/編", "/編者按", "/校勘記")


def _polite_sleep_inline(base: float) -> None:
    global _polite_req_count
    _polite_req_count += 1
    time.sleep(base + random.uniform(0, 0.5))
    if _polite_req_count and _polite_req_count % _LONG_PAUSE_EVERY == 0:
        print(f"  [polite-pause] {_LONG_PAUSE_SECONDS:.0f}s break after {_polite_req_count} requests")
        time.sleep(_LONG_PAUSE_SECONDS)


def api_get(params: dict) -> dict:
    headers = {"User-Agent": USER_AGENT}
    backoff = BACKOFF_INITIAL
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(
                WS_API,
                params={**params, "format": "json", "formatversion": 2},
                headers=headers,
                timeout=REQ_TIMEOUT,
            )
            if r.status_code in (429, 503):
                print(f"  [rate-limit {r.status_code}] sleep {backoff:.0f}s")
                time.sleep(backoff)
                backoff *= 2
                continue
            r.raise_for_status()
            if not r.text.strip():
                raise ValueError("empty response")
            return r.json()
        except (requests.RequestException, ValueError) as e:
            print(f"  [req-error attempt {attempt}/{MAX_RETRIES}] sleep {backoff:.0f}s: {e}")
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError(f"max retries exceeded for {params}")


def natural_sort_key(s: str) -> tuple:
    parts = re.split(r"(\d+)", s)
    return tuple((int(p) if p.isdigit() else p) for p in parts)


def discover_subpages(title: str, drop_pattern: str | None = None) -> list[str]:
    """True subpages of title, via allpages strict prefix (prefixsearch is fuzzy).

    Some books carry two parallel uploads of the same content (韓非子 has a
    numbered 01–20 set beside the 55 named 篇). `drop_pattern` is set per-entry
    in the catalog to discard the redundant one.
    """
    prefix = title + "/"
    drop_re = re.compile(drop_pattern) if drop_pattern else None
    subs: list[str] = []
    continue_param: dict = {}
    while True:
        params = {
            "action": "query",
            "list": "allpages",
            "apprefix": prefix,
            "aplimit": 500,
            "apnamespace": 0,
        }
        params.update(continue_param)
        data = api_get(params)
        for p in data.get("query", {}).get("allpages", []):
            t = p["title"]
            if not t.startswith(prefix):
                continue
            if any(t.endswith(suf) for suf in META_SUBPAGE_SUFFIXES):
                continue
            if drop_re and drop_re.search(t[len(prefix):]):
                continue
            subs.append(t)
        if "continue" in data:
            continue_param = data["continue"]
        else:
            break
    return sorted(subs, key=natural_sort_key)


CHROME_PATTERNS = [re.compile(p) for p in (
    r"^姊妹計?畫?:", r"^姊妹计?划?:",
    r"参阅维基百科", r"參閱維基百科",
    r"此作品在全世界都",
    r"^本作品.*已(進|进)入公有(領|领)域",
    r"^数据项$", r"^資料項?$",
    r"^Wikidata", r"^数字图书馆",
    r"^(分类|分類)：?",
    r"^Public domain", r"^This work is in the public domain",
)]


HEADING_MARKER = "## "
NAV_HEADINGS = {"目次", "目錄", "目录", "参考", "參考", "注釋", "註釋", "注释", "參見", "参见"}


def is_chrome(text: str) -> bool:
    return any(p.search(text) for p in CHROME_PATTERNS)


def split_by_headings(text: str) -> list[tuple[str, str]] | None:
    """Split a single-page text into (篇名, body) chapters at heading markers.

    Returns None when the page has no usable headings, so the caller keeps it
    as one chapter rather than inventing structure.
    """
    lines = text.split("\n")
    marks = [i for i, l in enumerate(lines) if l.startswith(HEADING_MARKER)]
    marks = [i for i in marks if lines[i][len(HEADING_MARKER):].strip() not in NAV_HEADINGS]
    if len(marks) < 2:
        return None
    chapters = []
    for n, start in enumerate(marks):
        end = marks[n + 1] if n + 1 < len(marks) else len(lines)
        label = lines[start][len(HEADING_MARKER):].strip()
        body = "\n".join(lines[start + 1:end]).strip()
        if body:
            chapters.append((label, body))
    return chapters or None


def _nested_in_block(el, container, block_tags: list[str]) -> bool:
    for a in el.parents:
        if a is container:
            return False
        if a.name in block_tags:
            return True
    return False


def extract_main_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for sel in [
        "table.metadata", "div.noprint", "table.noprint",
        "div.mw-references-wrap", "ol.references",
        "div.thumb", "div.sister-projects",
        "div.toc", "span.mw-editsection",
        "div.printfooter", "table.toccolours",
        "div.navbox", "table.navbox", "div.catlinks",
        "div.dablink", "div.hatnote",
        "table.wikisource-template", "table[role='presentation']",
        "table.infobox", "table.header_notes",
        "div.header_notes", "table.headertemplate",
        "div.PD-icon", "p.PD-icon", "table.PD-icon",
        ".header_notes", ".sister-box", ".sisterproject",
        ".tright", ".tleft", ".gallery",
    ]:
        for el in soup.select(sel):
            el.decompose()
    container = soup.select_one("div.mw-parser-output") or soup

    block_tags = ["h2", "h3", "h4", "p", "dt", "dd", "li", "blockquote"]
    parts = []
    for el in container.find_all(block_tags, recursive=True):
        # 九章算術 nests <dd> inside <dd> 251 times; matching both levels emitted
        # every 荅曰 twice. Take only outermost blocks — get_text() already
        # includes the descendants, so nothing is lost, and on pages without
        # nesting this selects exactly the same set as before.
        if _nested_in_block(el, container, block_tags):
            continue
        t = el.get_text(strip=True)
        if not t:
            continue
        if not re.search(r"[^\s\d.,;:!?'\"()-]", t):
            continue
        if is_chrome(t):
            continue
        # Headings carry the 篇名 that annotations.json anchors on (SCHEMA §4).
        if el.name in ("h2", "h3", "h4"):
            t = HEADING_MARKER + t
        parts.append(t)
    if not parts:
        t = container.get_text("\n", strip=True)
        parts = [
            line for line in t.split("\n")
            if line.strip() and len(line.strip()) > 2 and not is_chrome(line)
        ]
    return "\n".join(parts)


def get_page_text(title: str) -> str:
    data = api_get({"action": "parse", "page": title, "prop": "text", "redirects": 1})
    if "error" in data:
        raise RuntimeError(f"parse({title}): {data['error']}")
    html = data.get("parse", {}).get("text", "")
    return extract_main_text(html) if html else ""


def download_text(entry: dict) -> dict:
    slug = entry["slug"]
    title = entry.get("wikisource_title") or entry["name_zh"]

    meta_path = TRANSLATIONS_DIR / slug / "meta.json"
    out_dir = TRANSLATIONS_DIR / slug / "raw"
    if meta_path.exists() and (out_dir / "original.txt").exists():
        try:
            if json.loads(meta_path.read_text(encoding="utf-8")).get("verified"):
                print(f"[skip] {slug}: already verified")
                return {"slug": slug, "status": "already_verified"}
        except (json.JSONDecodeError, OSError):
            pass

    fetched_titles: list[str] = []
    chapters: list[tuple[str, str]] = []
    seen_hashes: dict[str, str] = {}
    try:
        if entry.get("force_single_page"):
            subs = []
        else:
            subs = entry.get("wikisource_subpages_explicit") or discover_subpages(
                title, entry.get("subpage_drop_pattern")
            )
        if subs:
            print(f"  [multi] {len(subs)} subpages")
            for sub in subs:
                fetched_titles.append(sub)
                _polite_sleep_inline(SLEEP_BETWEEN_REQUESTS)
                text = get_page_text(sub)
                if not text.strip():
                    print(f"  [empty] {sub}")
                    continue
                # Wikisource keeps redirect pairs (八奸/八姦, 揚榷/揚權) that resolve
                # to identical content; drop the second copy.
                h = hashlib.sha256(text.encode("utf-8")).hexdigest()
                if h in seen_hashes:
                    print(f"  [dup] {sub} == {seen_hashes[h]}")
                    continue
                seen_hashes[h] = sub
                label = sub.split("/", 1)[1] if "/" in sub else sub
                chapters.append((label, text))
        else:
            fetched_titles.append(title)
            text = get_page_text(title)
            if not text.strip():
                return {"slug": slug, "status": "empty", "reason": f"{title} has no extractable text"}
            split = split_by_headings(text)
            chapters = split if split else [(title, text)]
    except RuntimeError as e:
        return {"slug": slug, "status": "error", "reason": str(e)}
    except requests.RequestException as e:
        return {"slug": slug, "status": "fetch_error", "reason": str(e)}

    if not chapters:
        return {"slug": slug, "status": "empty", "reason": "no non-empty chapters"}

    # Wikisource commonly serves 卷-level subpages that carry the real 篇 inside as
    # headings. SCHEMA §4 anchors on 篇名, so push the split down one level.
    if not entry.get("no_subpage_split"):
        expanded: list[tuple[str, str]] = []
        for label, body in chapters:
            split = split_by_headings(body)
            expanded.extend(split if split else [(label, body)])
        chapters = expanded

    # Redirect pairs (外儲說右上 / 右上, 明堂月令諭 / 明堂月令論) differ only by the
    # heading line, so they survive the pre-split hash check and collide here.
    # Keep the more specific label of each pair.
    by_body: dict[str, int] = {}
    kept: list[tuple[str, str]] = []
    for label, body in chapters:
        h = hashlib.sha256(body.strip().encode("utf-8")).hexdigest()
        if h in by_body:
            i = by_body[h]
            if len(label) > len(kept[i][0]):
                kept[i] = (label, kept[i][1])
            print(f"  [dup-body] {label} == {kept[i][0]}")
            continue
        by_body[h] = len(kept)
        kept.append((label, body))
    chapters = kept

    out_dir.mkdir(parents=True, exist_ok=True)
    # A heading can repeat inside one page (厚黑學 has several 空, 金匱要略 several
    # 【附方】). Chapter labels are annotation anchors, so they must be unique.
    counts: dict[str, int] = {}
    for lab, _ in chapters:
        counts[lab] = counts.get(lab, 0) + 1
    running: dict[str, int] = {}
    deduped = []
    for lab, text in chapters:
        if counts[lab] > 1:
            running[lab] = running.get(lab, 0) + 1
            lab = f"{lab}（{running[lab]}）"
        deduped.append((lab, text))
    chapters = deduped

    lines = []
    for i, (label, text) in enumerate(chapters, 1):
        lines.append(f"=== {i} | {label} ===")
        lines.append(text)
        lines.append("")
    original_bytes = ("\n".join(lines).rstrip() + "\n").encode("utf-8")

    (out_dir / "original.txt").write_bytes(original_bytes)
    ws_host = WS_API.replace("/w/api.php", "")
    page_urls = [f"{ws_host}/wiki/{t.replace(' ', '_')}" for t in fetched_titles]
    (out_dir / "source-urls.txt").write_bytes(("\n".join(page_urls) + "\n").encode("utf-8"))
    sha = hashlib.sha256(original_bytes).hexdigest()
    (out_dir / "checksums.sha256").write_bytes(f"{sha}  original.txt\n".encode("utf-8"))

    meta = {
        "slug": slug,
        "name_zh": entry["name_zh"],
        "name_en": entry.get("name_en", ""),
        "category": entry["category"],
        "text_role": entry.get("text_role", "original"),
        "language": entry.get("language", "古典漢語"),
        "version": entry.get("version", "Wikisource 通行本"),
        "version_date": entry.get("version_date", "—"),
        "source_platform": "zh.wikisource.org",
        "source_url": f"{ws_host}/wiki/{title.replace(' ', '_')}",
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "size_bytes": len(original_bytes),
        "checksum_sha256": sha,
        "chapter_count": len(chapters),
        "expected_chapter_count": entry.get("expected_chapter_count"),
        "license": "CC BY-SA 4.0",
        "verified": False,
        "tier": entry.get("tier"),
        # Paragraph-level L2/L3 live in annotations.json, not here (SCHEMA §1/§4).
        # psych_survey stays null until the text is actually read end to end;
        # null means "not surveyed", never "nothing there" (SCHEMA §5).
        "psych_survey": None,
        "notes": entry.get("note"),
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_bytes((json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"[ok] {slug}: {len(chapters)} chapters (expected {meta['expected_chapter_count']}), {len(original_bytes)} bytes")
    return {"slug": slug, "status": "ok", "meta": meta}


def load_catalog() -> list[dict]:
    entries: list[dict] = []
    for path in sorted(CATALOG_DIR.glob("*-ws.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for e in data["scriptures"]:
            e.setdefault("language", data.get("language"))
            entries.append(e)
    return entries


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--slug")
    p.add_argument("--category")
    p.add_argument("--all", action="store_true")
    p.add_argument("--phase", type=int, default=1, help="only fetch entries of this phase (default 1)")
    p.add_argument("--limit", type=int)
    p.add_argument("--survey", action="store_true",
                   help="list subpage structure only, one API call per text, no fetching")
    args = p.parse_args()

    entries = load_catalog()
    if args.slug:
        selected = [e for e in entries if e["slug"] == args.slug]
        if not selected:
            sys.exit(f"slug not in catalog: {args.slug}")
    elif args.category:
        selected = [e for e in entries if e["category"] == args.category
                    and e.get("phase", 1) == args.phase]
        if not selected:
            sys.exit(f"no phase-{args.phase} entries in category: {args.category}")
    elif args.all:
        selected = [e for e in entries if e.get("phase", 1) == args.phase]
    else:
        p.print_help()
        return

    if args.limit:
        selected = selected[: args.limit]

    print(f"[plan] {len(selected)} texts")

    if args.survey:
        report = []
        for e in selected:
            title = e.get("wikisource_title") or e["name_zh"]
            _polite_sleep_inline(SLEEP_BETWEEN_REQUESTS)
            subs = discover_subpages(title, e.get("subpage_drop_pattern"))
            labels = [s.split("/", 1)[1] for s in subs]
            numeric = [l for l in labels if re.fullmatch(r"[0-9０-９]+", l)]
            flags = []
            if numeric and len(numeric) != len(labels):
                flags.append(f"MIXED numeric={len(numeric)} named={len(labels) - len(numeric)}")
            exp = e.get("expected_chapter_count")
            if subs and exp and abs(len(subs) - exp) > max(2, exp * 0.2):
                flags.append(f"COUNT got={len(subs)} expected={exp}")
            if not subs:
                flags.append("SINGLE-PAGE")
            report.append({"slug": e["slug"], "name_zh": e["name_zh"],
                           "subpages": len(subs), "expected": exp,
                           "flags": flags, "labels": labels[:80]})
            print(f"  {e['slug']:<26} subs={len(subs):<4} exp={exp} {' '.join(flags)}")
        out = ROOT / "scripts" / "survey-wikisource.json"
        out.write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        print(f"\n[survey] written to {out}")
        print("[flagged]", json.dumps(
            [r["slug"] for r in report if r["flags"]], ensure_ascii=False))
        return

    results = []
    for e in selected:
        print(f"\n--- {e['slug']} ({e['name_zh']}) ---")
        try:
            r = download_text(e)
        except Exception as ex:
            r = {"slug": e["slug"], "status": "exception", "reason": repr(ex)}
            print(f"[exception] {e['slug']}: {ex}")
        results.append(r)

    summary: dict[str, int] = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    print("\n[summary]", json.dumps(summary, ensure_ascii=False))
    bad = [r for r in results if r["status"] not in ("ok", "already_verified")]
    if bad:
        print("[not-ok]", json.dumps(bad, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
