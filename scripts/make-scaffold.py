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
from pathlib import Path

from corpus_text import MIN_CHARS_DEFAULT, split_paragraphs

ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS_DIR = ROOT / "translations"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--slug", required=True)
    p.add_argument("--min-chars", type=int, default=MIN_CHARS_DEFAULT,
                   help="skip fragments shorter than this (headings, stray markers). "
                        "verify.py checks anchors using the default, so a non-default "
                        "value here will be reported as anchor drift.")
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
    for ch_no, ch_label, idx, body in split_paragraphs(text, args.min_chars):
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
