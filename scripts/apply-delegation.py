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
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    base = ROOT / "delegation" / args.slug
    manifest = json.loads((base / "MANIFEST.json").read_text(encoding="utf-8"))

    verdicts: dict[tuple[str, int], dict] = {}
    for batch in manifest["batches"]:
        out = base / "out" / batch["file"].replace(".md", ".json")
        for row in json.loads(out.read_text(encoding="utf-8"))["rows"]:
            verdicts[(row["chapter"], row["para_index"])] = row

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
        r["tagged_by"] = args.tagged_by
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
