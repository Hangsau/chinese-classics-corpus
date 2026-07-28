#!/usr/bin/env python
"""
Verify downloaded texts against the catalog and their own checksums.

Checks per text:
  - meta.json / original.txt / checksums.sha256 all present
  - SHA-256 in checksums.sha256 matches the file on disk (catches CRLF damage)
  - file is not suspiciously small (a bare TOC page yields a few hundred bytes)
  - chapter labels are usable as annotation anchors (SCHEMA §4: name, not index)
  - no two chapters carry identical text

Usage:
    PYTHONIOENCODING=utf-8 python scripts/verify.py
    PYTHONIOENCODING=utf-8 python scripts/verify.py --strict   # warnings fail too
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = ROOT / "scripts" / "catalog"
TRANSLATIONS_DIR = ROOT / "translations"

MIN_BYTES = 1500
CHAPTER_RE = re.compile(r"^=== (\d+) \| (.+) ===$")


def load_catalog() -> dict[str, dict]:
    out = {}
    for path in sorted(CATALOG_DIR.glob("*-ws.json")):
        for e in json.loads(path.read_text(encoding="utf-8"))["scriptures"]:
            out[e["slug"]] = e
    return out


def check(slug: str, entry: dict) -> tuple[list[str], list[str], dict]:
    errors: list[str] = []
    warnings: list[str] = []
    info: dict = {"slug": slug}

    d = TRANSLATIONS_DIR / slug
    meta_p, txt_p, sum_p = d / "meta.json", d / "raw" / "original.txt", d / "raw" / "checksums.sha256"
    for p in (meta_p, txt_p, sum_p):
        if not p.exists():
            errors.append(f"missing {p.relative_to(ROOT)}")
    if errors:
        return errors, warnings, info

    raw = txt_p.read_bytes()
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    info["bytes"] = len(raw)

    actual = hashlib.sha256(raw).hexdigest()
    recorded = sum_p.read_text(encoding="utf-8").split()[0]
    if actual != recorded:
        errors.append(f"sha256 mismatch: file={actual[:12]} checksums={recorded[:12]}")
    if meta.get("checksum_sha256") != actual:
        errors.append("meta.checksum_sha256 disagrees with file")
    if meta.get("size_bytes") != len(raw):
        errors.append("meta.size_bytes disagrees with file")
    if b"\r\n" in raw:
        errors.append("CRLF found in original.txt (breaks reproducible SHA-256)")

    text = raw.decode("utf-8")
    labels, bodies, cur = [], [], []
    for line in text.split("\n"):
        m = CHAPTER_RE.match(line)
        if m:
            if labels:
                bodies.append("\n".join(cur))
            labels.append(m.group(2))
            cur = []
        else:
            cur.append(line)
    if labels:
        bodies.append("\n".join(cur))
    info["chapters"] = len(labels)

    floor = 600 if entry.get("tier") == "單篇" else MIN_BYTES
    if len(raw) < floor:
        errors.append(f"only {len(raw)} bytes — likely a TOC page, not the text")
    if not labels:
        errors.append("no chapter markers")
    if len(labels) != len(set(labels)):
        dupes = sorted({l for l in labels if labels.count(l) > 1})
        errors.append(f"duplicate chapter labels: {dupes[:5]}")

    seen: dict[str, str] = {}
    for lab, body in zip(labels, bodies):
        h = hashlib.sha256(body.strip().encode("utf-8")).hexdigest()
        if body.strip() and h in seen:
            errors.append(f"chapter '{lab}' has identical text to '{seen[h]}'")
        seen[h] = lab

    numeric = [l for l in labels if re.fullmatch(r"[0-9０-９]+", l)]
    if numeric:
        warnings.append(f"{len(numeric)}/{len(labels)} chapter labels are bare numbers "
                        f"— poor anchors for annotations.json")
    exp = entry.get("expected_chapter_count")
    if exp and labels and abs(len(labels) - exp) > max(2, exp * 0.25):
        warnings.append(f"chapter count {len(labels)} vs catalog expected {exp}")
    if meta.get("text_role") != entry.get("text_role", "original"):
        errors.append("meta.text_role disagrees with catalog")
    if "psych_survey" not in meta:
        errors.append("meta.psych_survey field absent (SCHEMA §5)")

    return errors, warnings, info


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()

    catalog = load_catalog()
    downloaded = sorted(x.name for x in TRANSLATIONS_DIR.iterdir() if x.is_dir()) \
        if TRANSLATIONS_DIR.exists() else []

    unknown = [s for s in downloaded if s not in catalog]
    for s in unknown:
        print(f"[ERROR] {s}: directory has no catalog entry")

    n_err = len(unknown)
    n_warn = 0
    rows = []
    for slug in downloaded:
        if slug in unknown:
            continue
        errors, warnings, info = check(slug, catalog[slug])
        rows.append(info)
        for e in errors:
            print(f"[ERROR] {slug}: {e}")
        for w in warnings:
            print(f"[warn]  {slug}: {w}")
        n_err += len(errors)
        n_warn += len(warnings)

    total = sum(r.get("bytes", 0) for r in rows)
    print(f"\n{len(rows)} texts, {total:,} bytes, {n_err} errors, {n_warn} warnings")
    pending = [s for s in catalog if catalog[s].get("phase", 1) == 1 and s not in downloaded]
    if pending:
        print(f"phase-1 not yet downloaded ({len(pending)}): {', '.join(pending)}")
    smallest = sorted((r for r in rows if "bytes" in r), key=lambda r: r["bytes"])[:5]
    print("smallest:", ", ".join(f"{r['slug']}={r['bytes']}" for r in smallest))

    sys.exit(1 if n_err or (args.strict and n_warn) else 0)


if __name__ == "__main__":
    main()
