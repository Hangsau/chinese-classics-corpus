#!/usr/bin/env python
"""
Regenerate 00-overview/INDEX.json and INDEX.md from translations/*/meta.json.

Index is generated from data, never hand-edited (claudehome 知識規範 #6).

Usage:
    PYTHONIOENCODING=utf-8 python scripts/build-index.py
"""

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS_DIR = ROOT / "translations"
OVERVIEW_DIR = ROOT / "00-overview"

FIELDS = [
    "slug", "name_zh", "name_en", "category", "text_role", "language",
    "version", "version_date", "source_platform", "tier",
    "size_bytes", "chapter_count", "verified",
]


def main() -> None:
    records = []
    for meta_path in sorted(TRANSLATIONS_DIR.glob("*/meta.json")):
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        rec = {k: m.get(k) for k in FIELDS}
        survey = m.get("psych_survey")
        rec["surveyed"] = bool(survey)
        rec["domains_hit"] = (survey or {}).get("domains_hit")

        # A scaffold is not an annotation. Count paragraphs actually judged
        # (SCHEMA §5.1: null = unread, [] = read and empty), so a freshly
        # generated all-null file does not read as done.
        ann_path = meta_path.parent / "annotations.json"
        rows = json.loads(ann_path.read_text(encoding="utf-8")) if ann_path.exists() else []
        rec["paras_total"] = len(rows)
        rec["paras_judged"] = sum(1 for r in rows if r.get("psych_domains") is not None)
        rec["annotated"] = rec["paras_judged"] > 0
        records.append(rec)

    by_cat = Counter(r["category"] for r in records)
    by_role = Counter(r["text_role"] for r in records)
    domain_count: dict[str, int] = defaultdict(int)
    for r in records:
        for d in r["domains_hit"] or []:
            domain_count[d] += 1

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "text_count": len(records),
        "total_bytes": sum(r["size_bytes"] or 0 for r in records),
        "by_category": dict(sorted(by_cat.items(), key=lambda kv: -kv[1])),
        "by_text_role": dict(by_role),
        "surveyed_count": sum(1 for r in records if r["surveyed"]),
        "annotated_count": sum(1 for r in records if r["annotated"]),
        "scaffolded_count": sum(1 for r in records if r["paras_total"] and not r["annotated"]),
        "paras_judged": sum(r["paras_judged"] for r in records),
        "paras_pending": sum(r["paras_total"] - r["paras_judged"] for r in records),
        "domain_hit_counts": dict(sorted(domain_count.items())),
    }

    OVERVIEW_DIR.mkdir(exist_ok=True)
    (OVERVIEW_DIR / "INDEX.json").write_bytes(
        (json.dumps({"summary": summary, "texts": records}, ensure_ascii=False, indent=2) + "\n")
        .encode("utf-8")
    )

    lines = [
        "# 索引",
        "",
        "> 本檔由 `scripts/build-index.py` 生成，**不要手改**。",
        f"> 生成時間 {summary['generated_at']}｜{summary['text_count']} 部｜"
        f"{summary['total_bytes']:,} bytes｜已通讀 {summary['surveyed_count']} 部｜"
        f"已段落標註 {summary['annotated_count']} 部（{summary['paras_judged']} 段）｜"
        f"僅有骨架待標 {summary['scaffolded_count']} 部（{summary['paras_pending']} 段）",
        "",
        "## 分類統計",
        "",
        "| 類 | 部數 |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v} |" for k, v in summary["by_category"].items()]
    lines += ["", "## 全部文本", "",
              "| slug | 書名 | 類 | text_role | 章數 | bytes | 通讀 | 段落標註 |",
              "|---|---|---|---|---|---|---|---|"]
    for r in sorted(records, key=lambda r: (r["category"], r["slug"])):
        if r["paras_total"] == 0:
            ann = "—"
        elif r["annotated"]:
            ann = f"{r['paras_judged']}/{r['paras_total']}"
        else:
            ann = f"骨架 {r['paras_total']}"
        lines.append(
            f"| `{r['slug']}` | {r['name_zh']} | {r['category']} | {r['text_role']} | "
            f"{r['chapter_count']} | {r['size_bytes']:,} | "
            f"{'✓' if r['surveyed'] else '—'} | {ann} |"
        )
    lines.append("")
    (OVERVIEW_DIR / "INDEX.md").write_bytes(("\n".join(lines)).encode("utf-8"))

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
