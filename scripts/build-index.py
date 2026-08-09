#!/usr/bin/env python
"""
Regenerate the generated index layer from translations/*/{meta.json,annotations.json}.

Index is generated from data, never hand-edited (claudehome 知識規範 #6). Three
outputs, one command, so they cannot drift apart:

    00-overview/INDEX.json / INDEX.md   內容索引（書級）
    00-overview/DOMAINS.md              標籤索引總表 + 缺口報告
    00-overview/domains/<id>.{md,json}  每個領域一頁，段級反向索引

Why the domain pages exist: 書級 domains_hit only answers "which book to open",
which SCHEMA §1.1 states outright is not enough. Paragraph-level annotation only
pays off through a reverse index, so it ships from the same command.

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
VOCAB_PATH = ROOT / "vocab" / "psych-domains.json"

FIELDS = [
    "slug", "name_zh", "name_en", "category", "text_role", "language",
    "version", "version_date", "source_platform", "tier",
    "size_bytes", "chapter_count", "verified",
]


def cell(s: str) -> str:
    """Markdown table cells break on a literal pipe or newline."""
    return (s or "").replace("|", "｜").replace("\n", " ").strip()


def build_domain_index(records: list[dict], annotations: dict[str, list],
                       overview_dir: Path) -> dict[str, int]:
    domains_dir = overview_dir / "domains"
    vocab = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))["domains"]
    meta_by_slug = {r["slug"]: r for r in records}

    hits: dict[str, list[dict]] = defaultdict(list)
    for slug, rows in annotations.items():
        for row in rows:
            domains = row.get("psych_domains")
            if not domains:
                continue
            for d in domains:
                hits[d].append({
                    "slug": slug,
                    "chapter": row["anchor"]["chapter"],
                    "para_index": row["anchor"]["para_index"],
                    "para_id": row.get("para_id"),
                    "modes": row.get("discourse_mode") or [],
                    "excerpt": row.get("excerpt") or "",
                    "note": row.get("note") or "",
                    "co_domains": [x for x in domains if x != d],
                })

    # Surveyed-and-empty is a result, not a hole (SCHEMA §5). Keep it next to the
    # hits so a zero never reads as "nobody looked".
    nulls: dict[str, list[str]] = defaultdict(list)
    for r in records:
        for d in (r.get("domains_null") or []):
            nulls[d].append(r["slug"])

    domains_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    hub_rows = []

    for d in vocab:
        did, rows = d["id"], hits.get(d["id"], [])
        by_book = Counter(h["slug"] for h in rows)
        mode_count = Counter(m for h in rows for m in h["modes"])
        hub_rows.append((did, d["name_zh"], len(rows), len(by_book), len(nulls.get(did, []))))

        (domains_dir / f"{did}.json").write_bytes(
            (json.dumps({
                "domain": did, "name_zh": d["name_zh"], "gist": d["gist"],
                "generated_at": generated_at,
                "para_count": len(rows), "book_count": len(by_book),
                "surveyed_zero_hit": sorted(nulls.get(did, [])),
                "paras": rows,
            }, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        )

        out = [
            f"# {did} {d['name_zh']}",
            "",
            "> 本檔由 `scripts/build-index.py` 生成，**不要手改**。",
            f"> {len(rows)} 段命中｜跨 {len(by_book)} 部｜生成時間 {generated_at}",
            "",
            f"{d['gist']}",
            "",
        ]
        if mode_count:
            out += ["姿態分佈："
                    + "、".join(f"`{m}` {n}" for m, n in mode_count.most_common()), ""]
        if nulls.get(did):
            out += [
                "## 已通讀但本領域零命中",
                "",
                "負面結果，不是缺口——這些書讀過了，就是沒有（SCHEMA §5）。",
                "",
                "　".join(f"`{s}`（{meta_by_slug[s]['name_zh']}）"
                          for s in sorted(nulls[did])),
                "",
            ]
        if not rows:
            out += ["## 段落", "", "尚無命中。", ""]
        for slug, _ in by_book.most_common():
            m = meta_by_slug[slug]
            out += [
                f"## {m['name_zh']}（{m['category']}）　{by_book[slug]} 段",
                "",
                "| 篇 | 段 | 姿態 | 摘句 | 判讀 |",
                "|---|---|---|---|---|",
            ]
            for h in [x for x in rows if x["slug"] == slug]:
                co = f"＋{'／'.join(h['co_domains'])} " if h["co_domains"] else ""
                out.append(
                    f"| {cell(h['chapter'])} | {h['para_index']} | "
                    f"{' '.join('`' + m2 + '`' for m2 in h['modes'])} | "
                    f"{cell(h['excerpt'])} | {co}{cell(h['note'])} |"
                )
            out.append("")
        (domains_dir / f"{did}.md").write_bytes("\n".join(out).encode("utf-8"))

    unannotated = [r for r in records if not r["annotated"]]
    hub = [
        "# 標籤索引：13 個人生問題領域",
        "",
        "> 本檔由 `scripts/build-index.py` 生成，**不要手改**。",
        f"> 生成時間 {generated_at}｜"
        f"{sum(len(v) for v in hits.values())} 筆領域標記｜"
        f"來自 {sum(1 for r in records if r['annotated'])} 部已標註的書",
        "",
        "書級 `domains_hit` 只能告訴你去哪本書找；這裡直接給段落（SCHEMA §1.1）。",
        "",
        "| 領域 | 名稱 | 命中段數 | 命中書數 | 通讀零命中書數 |",
        "|---|---|---|---|---|",
    ]
    hub += [f"| [{did}](./domains/{did}.md) | {name} | {n} | {nb} | {nz} |"
            for did, name, n, nb, nz in hub_rows]
    hub += [
        "",
        "## 缺口報告",
        "",
        f"**未標註 {len(unannotated)} 部**——這些書的領域分佈目前是未知，"
        "不是零。上表任何一格的低數字都要先扣掉這批才有意義。",
        "",
    ]
    for r in sorted(unannotated, key=lambda r: (r["category"], r["slug"])):
        hub.append(f"- `{r['slug']}` {r['name_zh']}（{r['category']}，"
                   f"{r['chapter_count']} 章，{r['size_bytes']:,} bytes）")
    hub.append("")
    (overview_dir / "DOMAINS.md").write_bytes("\n".join(hub).encode("utf-8"))
    return {did: n for did, _, n, _, _ in hub_rows}


def main(overview_dir: Path = OVERVIEW_DIR, quiet: bool = False) -> None:
    records = []
    annotations: dict[str, list] = {}
    for meta_path in sorted(TRANSLATIONS_DIR.glob("*/meta.json")):
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        rec = {k: m.get(k) for k in FIELDS}
        survey = m.get("psych_survey")
        rec["surveyed"] = bool(survey)
        rec["domains_hit"] = (survey or {}).get("domains_hit")
        rec["domains_null"] = (survey or {}).get("domains_null")

        # A scaffold is not an annotation. Count paragraphs actually judged
        # (SCHEMA §5.1: null = unread, [] = read and empty), so a freshly
        # generated all-null file does not read as done.
        ann_path = meta_path.parent / "annotations.json"
        rows = json.loads(ann_path.read_text(encoding="utf-8")) if ann_path.exists() else []
        rec["paras_total"] = len(rows)
        rec["paras_judged"] = sum(1 for r in rows if r.get("psych_domains") is not None)
        rec["annotated"] = rec["paras_judged"] > 0
        records.append(rec)
        annotations[rec["slug"]] = rows

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

    overview_dir.mkdir(parents=True, exist_ok=True)
    summary["domain_para_counts"] = build_domain_index(records, annotations, overview_dir)
    (overview_dir / "INDEX.json").write_bytes(
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
    (overview_dir / "INDEX.md").write_bytes(("\n".join(lines)).encode("utf-8"))

    if not quiet:
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
