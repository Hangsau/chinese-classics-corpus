"""把 delegation/<slug>/out/*.json 回填進 translations/<slug>/annotations.json。

先跑 check-delegation-out.py 確認錨點與值域全過，這支才會動手；錨點對不上就整批
不寫，避免半套寫入後難以回復。

`tagged_by` 記實際下判斷的模型（發包時是外部 agent，不是本庫的 Claude），因為
判準的來源會影響日後重判時要不要信任既有標記。

一部書可能有段落刻意不發包（與另一部書重出）。`--inherit-from` 讓逐字相同的段落
沿用另一部的判讀，`--leave-null-chapter` 讓沿用不了的整章留 null；兩者都要顯式
指定，其餘缺判讀的段落照舊整批拒寫。
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_text import split_paragraphs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TZ = timezone(timedelta(hours=8))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--tagged-by", required=True, help="實際下判斷的模型")
    ap.add_argument("--tagged-by-batch", action="append", default=[],
                    metavar="bNN=model",
                    help="某幾批換人判時逐批覆寫，可重複。一部書中途換判讀者要據實記錄，"
                         "否則日後重判時無從判斷該信任哪些既有標記")
    ap.add_argument("--inherit-from", metavar="SLUG",
                    help="逐字相同的段落沿用該書的既有標註（本書發包時已扣除，不重判）")
    ap.add_argument("--leave-null-chapter", metavar="CHAPTER", action="append", default=[],
                    help="整章留 null（重出但切段粒度不同，沿用不了也不重判）；可重複，"
                         "與 make-delegation-input.py --exclude-chapter 對應")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    overrides = {}
    for item in args.tagged_by_batch:
        b, _, model = item.partition("=")
        if not model:
            print(f"[FAIL] --tagged-by-batch 格式應為 bNN=model，收到 {item!r}")
            return 1
        overrides[b] = model

    base = ROOT / "delegation" / args.slug
    manifest = json.loads((base / "MANIFEST.json").read_text(encoding="utf-8"))

    verdicts: dict[tuple[str, int], dict] = {}
    tagger: dict[tuple[str, int], str] = {}
    for batch in manifest["batches"]:
        stem = batch["file"].replace(".md", "")
        out = base / "out" / f"{stem}.json"
        for row in json.loads(out.read_text(encoding="utf-8"))["rows"]:
            key = (row["chapter"], row["para_index"])
            verdicts[key] = row
            tagger[key] = overrides.get(stem, args.tagged_by)

    unknown = set(overrides) - {b["file"].replace(".md", "") for b in manifest["batches"]}
    if unknown:
        print(f"[FAIL] --tagged-by-batch 指定了不存在的批次：{sorted(unknown)}")
        return 1

    ann_path = ROOT / "translations" / args.slug / "annotations.json"
    ann = json.loads(ann_path.read_text(encoding="utf-8"))

    # 一部書可能有段落刻意不發包（與另一部書逐字重出）。那些段落沿用另一部的判讀而不
    # 重判：重判會讓同一段文字在索引裡有兩份互不相通的判斷。沿用一律逐字比對，比對不
    # 上就不寫。
    inherited: dict[tuple[str, int], dict] = {}
    if args.inherit_from:
        src = ROOT / "translations" / args.inherit_from / "annotations.json"
        if not src.exists():
            print(f"[FAIL] --inherit-from {args.inherit_from} 沒有 annotations.json")
            return 1
        # annotations.json 的 excerpt 只留 40 字，拿來比對會把長段全部漏掉。段落文字
        # 一律由 split_paragraphs 從兩書的 raw/original.txt 重算，與發包時同一來源。
        def texts(s: str) -> dict[tuple[str, int], str]:
            raw = (ROOT / "translations" / s / "raw" / "original.txt").read_text(encoding="utf-8")
            return {(label, idx): t.strip() for _, label, idx, t in split_paragraphs(raw)}

        src_text = texts(args.inherit_from)
        by_text = {}
        for r in json.loads(src.read_text(encoding="utf-8")):
            if r.get("psych_domains") is None:
                continue
            t = src_text.get((r["anchor"]["chapter"], r["anchor"]["para_index"]))
            if t:
                by_text[t] = r
        self_text = texts(args.slug)
        for r in ann:
            key = (r["anchor"]["chapter"], r["anchor"]["para_index"])
            if key in verdicts:
                continue
            hit = by_text.get(self_text.get(key, ""))
            if hit is not None:
                inherited[key] = hit
        print(f"沿用 {args.inherit_from} 的逐字相同段落：{len(inherited)} 段")

    null_chapters = set(args.leave_null_chapter)
    unmatched = [r["para_id"] for r in ann
                 if (r["anchor"]["chapter"], r["anchor"]["para_index"]) not in verdicts
                 and (r["anchor"]["chapter"], r["anchor"]["para_index"]) not in inherited
                 and r["anchor"]["chapter"] not in null_chapters]
    if unmatched:
        print(f"[FAIL] {len(unmatched)} 段在骨架裡但發包結果沒有：{unmatched[:5]}")
        return 1
    for label in null_chapters:
        if not any(r["anchor"]["chapter"] == label for r in ann):
            print(f"[FAIL] --leave-null-chapter〈{label}〉在本書找不到")
            return 1
    orphan = set(verdicts) - {(r["anchor"]["chapter"], r["anchor"]["para_index"]) for r in ann}
    if orphan:
        print(f"[FAIL] {len(orphan)} 段在發包結果裡但骨架沒有：{sorted(orphan)[:5]}")
        return 1

    now = datetime.now(TZ).isoformat(timespec="seconds")
    n_written = 0
    for r in ann:
        key = (r["anchor"]["chapter"], r["anchor"]["para_index"])
        if key in verdicts:
            v = verdicts[key]
            r["psych_domains"] = v["domains"]
            r["discourse_mode"] = v["modes"]
            r["note"] = v.get("reason") or None
            r["tagged_by"] = tagger[key]
        elif key in inherited:
            v = inherited[key]
            r["psych_domains"] = v["psych_domains"]
            r["discourse_mode"] = v["discourse_mode"]
            r["note"] = v.get("note")
            r["tagged_by"] = f"{v.get('tagged_by')}（沿用 {args.inherit_from} 逐字相同段）"
        else:
            continue  # --leave-null-chapter，留 null 表示未標
        r["tagged_at"] = now
        n_written += 1

    if args.dry_run:
        print(f"[dry-run] 會寫 {n_written}/{len(ann)} 段")
        return 0

    ann_path.write_text(json.dumps(ann, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    print(f"[OK] 回填 {n_written}/{len(ann)} 段 -> {ann_path}"
          + (f"（{len(ann) - n_written} 段留 null）" if n_written != len(ann) else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
