"""把 delegation/<slug>/out/*.json 回填進 translations/<slug>/annotations.json。

先跑 check-delegation-out.py 確認錨點與值域全過，這支才會動手；錨點對不上就整批
不寫，避免半套寫入後難以回復。

`tagged_by` 記實際下判斷的模型（發包時是外部 agent，不是本庫的 Claude），因為
判準的來源會影響日後重判時要不要信任既有標記。
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

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

    unmatched = [r["para_id"] for r in ann
                 if (r["anchor"]["chapter"], r["anchor"]["para_index"]) not in verdicts]
    if unmatched:
        print(f"[FAIL] {len(unmatched)} 段在骨架裡但發包結果沒有：{unmatched[:5]}")
        return 1
    orphan = set(verdicts) - {(r["anchor"]["chapter"], r["anchor"]["para_index"]) for r in ann}
    if orphan:
        print(f"[FAIL] {len(orphan)} 段在發包結果裡但骨架沒有：{sorted(orphan)[:5]}")
        return 1

    now = datetime.now(TZ).isoformat(timespec="seconds")
    for r in ann:
        v = verdicts[(r["anchor"]["chapter"], r["anchor"]["para_index"])]
        r["psych_domains"] = v["domains"]
        r["discourse_mode"] = v["modes"]
        r["note"] = v.get("reason") or None
        r["tagged_by"] = tagger[(r["anchor"]["chapter"], r["anchor"]["para_index"])]
        r["tagged_at"] = now

    if args.dry_run:
        print(f"[dry-run] 會寫 {len(ann)} 段")
        return 0

    ann_path.write_text(json.dumps(ann, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    print(f"[OK] 回填 {len(ann)} 段 -> {ann_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
