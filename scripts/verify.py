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

from corpus_text import split_paragraphs

ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = ROOT / "scripts" / "catalog"
TRANSLATIONS_DIR = ROOT / "translations"
VOCAB_DIR = ROOT / "vocab"

MIN_BYTES = 1500
CHAPTER_RE = re.compile(r"^=== (\d+) \| (.+) ===$")
CONFIDENCE_VALUES = {"high", "medium", "low"}


def load_catalog() -> dict[str, dict]:
    out = {}
    for path in sorted(CATALOG_DIR.glob("*-ws.json")):
        for e in json.loads(path.read_text(encoding="utf-8"))["scriptures"]:
            out[e["slug"]] = e
    return out


def load_vocab() -> tuple[set[str], set[str]]:
    d = json.loads((VOCAB_DIR / "psych-domains.json").read_text(encoding="utf-8"))
    m = json.loads((VOCAB_DIR / "discourse-modes.json").read_text(encoding="utf-8"))
    return {x["id"] for x in d["domains"]}, {x["id"] for x in m["modes"]}


def check_vocab_drift() -> list[str]:
    """The 13 domains were derived in religions-history; detect silent divergence."""
    d = json.loads((VOCAB_DIR / "psych-domains.json").read_text(encoding="utf-8"))
    src = d["derived_from"]
    p = ROOT.parent / src["project"] / src["path"]
    if not p.exists():
        return [f"vocab derived_from source missing: {p}"]
    actual = hashlib.sha256(p.read_bytes()).hexdigest()
    if actual != src["sha256"]:
        return [f"vocab source changed since derivation "
                f"(now {actual[:12]}, recorded {src['sha256'][:12]}) "
                f"— re-check the 13 domains, then update derived_from.sha256"]
    return []


def check_annotations(path: Path, labels: list[str], slug: str,
                      domain_ids: set[str], mode_ids: set[str],
                      text: str) -> list[str]:
    errors: list[str] = []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"annotations.json is not valid JSON: {e}"]
    if not isinstance(rows, list):
        return ["annotations.json must be a list of annotation records"]

    label_set = set(labels)
    seen_ids: set[str] = set()

    # Anchors are chapter name + paragraph index, which survives a re-download only
    # as long as the paragraphs before them do. Re-check each anchor against the
    # current text so a shifted index is caught instead of silently re-pointing an
    # annotation at someone else's paragraph.
    para_at = {(ch_label, idx): body
               for _, ch_label, idx, body in split_paragraphs(text)}
    drifted = 0
    for i, r in enumerate(rows):
        where = f"annotations[{i}]"
        pid = r.get("para_id")
        if not pid:
            errors.append(f"{where}: para_id missing")
        elif pid in seen_ids:
            errors.append(f"{where}: duplicate para_id {pid}")
        else:
            seen_ids.add(pid)

        anchor = r.get("anchor") or {}
        chapter = anchor.get("chapter")
        if chapter is None:
            errors.append(f"{where}: anchor.chapter missing")
        elif chapter not in label_set:
            errors.append(f"{where}: anchor.chapter '{chapter}' is not a chapter of {slug}")
        idx = anchor.get("para_index")
        if not isinstance(idx, int):
            errors.append(f"{where}: anchor.para_index must be an integer")
        elif (excerpt := r.get("excerpt")):
            body = para_at.get((chapter, idx))
            if body is None:
                errors.append(f"{where}: anchor ({chapter}, {idx}) has no paragraph "
                              f"in the current text")
            elif not body.startswith(excerpt):
                drifted += 1

        # null means unannotated and is allowed; a wrong value is not.
        for field, allowed in (("psych_domains", domain_ids), ("discourse_mode", mode_ids)):
            v = r.get(field)
            if v is None:
                continue
            if not isinstance(v, list):
                errors.append(f"{where}: {field} must be a list or null")
                continue
            for bad in [x for x in v if x not in allowed]:
                errors.append(f"{where}: {field} value '{bad}' not in vocab")

        conf = r.get("confidence")
        if conf is not None and conf not in CONFIDENCE_VALUES:
            errors.append(f"{where}: confidence '{conf}' not in {sorted(CONFIDENCE_VALUES)}")

    if drifted:
        errors.append(f"{drifted}/{len(rows)} anchors no longer point at the paragraph "
                      f"they were written against — original.txt changed after "
                      f"annotation; re-run make-scaffold.py and re-check by hand")
    return errors


def check(slug: str, entry: dict, domain_ids: set[str], mode_ids: set[str]) -> tuple[list[str], list[str], dict]:
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

    # 「卷第3」這種只有卷序沒有篇名的標籤，成因通常是卷級子頁只含一篇而篇名被
    # 丟掉（見 download-wikisource.adopt_sole_heading）。它不是純數字，過去漏網，
    # 要等標到那部書才發現錨點沒有意義。
    num = r"[0-9０-９〇一二三四五六七八九十百]+"
    numeric = [l for l in labels
               if re.fullmatch(rf"(?:卷第|篇第|第|卷|篇)?{num}(?:卷|篇)?", l)]
    if numeric:
        warnings.append(f"{len(numeric)}/{len(labels)} chapter labels carry only an ordinal "
                        f"({numeric[:3]}) — poor anchors for annotations.json")
    exp = entry.get("expected_chapter_count")
    if exp and labels and abs(len(labels) - exp) > max(2, exp * 0.25):
        warnings.append(f"chapter count {len(labels)} vs catalog expected {exp}")
    if meta.get("text_role") != entry.get("text_role", "original"):
        errors.append("meta.text_role disagrees with catalog")
    if "psych_survey" not in meta:
        errors.append("meta.psych_survey field absent (SCHEMA §5)")

    ann_p = d / "annotations.json"
    info["annotated"] = ann_p.exists()
    if ann_p.exists():
        errors += check_annotations(ann_p, labels, slug, domain_ids, mode_ids, text)
    elif meta.get("psych_survey"):
        warnings.append("psych_survey recorded but no annotations.json")

    return errors, warnings, info


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()

    catalog = load_catalog()
    domain_ids, mode_ids = load_vocab()
    downloaded = sorted(x.name for x in TRANSLATIONS_DIR.iterdir() if x.is_dir()) \
        if TRANSLATIONS_DIR.exists() else []

    drift = check_vocab_drift()
    for e in drift:
        print(f"[ERROR] vocab: {e}")

    unknown = [s for s in downloaded if s not in catalog]
    for s in unknown:
        print(f"[ERROR] {s}: directory has no catalog entry")

    n_err = len(unknown) + len(drift)
    n_warn = 0
    rows = []
    for slug in downloaded:
        if slug in unknown:
            continue
        errors, warnings, info = check(slug, catalog[slug], domain_ids, mode_ids)
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
