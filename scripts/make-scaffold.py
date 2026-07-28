#!/usr/bin/env python
"""
Emit an annotation scaffold for one text: one row per paragraph, anchors filled in,
L2/L3 left null.

Annotating means editing the null fields — the anchors are generated from the text
itself, so they cannot drift from it (SCHEMA §4). Writing annotations.json by hand
is how bad anchors get in.

Existing annotations are preserved: rows already carrying a non-null psych_domains
or discourse_mode are kept as-is, so re-running after the text is re-downloaded
only adds the new paragraphs.

Usage:
    PYTHONIOENCODING=utf-8 python scripts/make-scaffold.py --slug sunzi-bingfa
    PYTHONIOENCODING=utf-8 python scripts/make-scaffold.py --slug sunzi-bingfa --min-chars 20
"""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS_DIR = ROOT / "translations"
CHAPTER_RE = re.compile(r"^=== (\d+) \| (.+) ===$")


def paragraphs(text: str, min_chars: int) -> list[tuple[int, str, int, str]]:
    """Yield (chapter_no, chapter_label, para_index, body) for each paragraph."""
    out = []
    ch_no, ch_label, idx = 0, None, 0
    for line in text.split("\n"):
        m = CHAPTER_RE.match(line)
        if m:
            ch_no, ch_label, idx = int(m.group(1)), m.group(2), 0
            continue
        body = line.strip()
        if ch_label is None or len(body) < min_chars:
            continue
        idx += 1
        out.append((ch_no, ch_label, idx, body))
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--slug", required=True)
    p.add_argument("--min-chars", type=int, default=12,
                   help="skip fragments shorter than this (headings, stray markers)")
    args = p.parse_args()

    d = TRANSLATIONS_DIR / args.slug
    text = (d / "raw" / "original.txt").read_text(encoding="utf-8")
    out_p = d / "annotations.json"

    done = {}
    if out_p.exists():
        for r in json.loads(out_p.read_text(encoding="utf-8")):
            if r.get("psych_domains") is not None or r.get("discourse_mode") is not None:
                done[r["para_id"]] = r

    rows = []
    for ch_no, ch_label, idx, body in paragraphs(text, args.min_chars):
        pid = f"{args.slug}#{ch_no:02d}-p{idx:02d}"
        if pid in done:
            rows.append(done[pid])
            continue
        rows.append({
            "para_id": pid,
            "anchor": {"chapter": ch_label, "para_index": idx},
            "psych_domains": None,
            "discourse_mode": None,
            "confidence": None,
            "note": None,
            "excerpt": body[:40],
        })

    out_p.write_bytes((json.dumps(rows, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"{args.slug}: {len(rows)} paragraphs, {len(done)} already annotated -> {out_p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
