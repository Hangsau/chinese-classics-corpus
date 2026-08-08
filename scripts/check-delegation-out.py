"""檢查 delegation/<slug>/out/*.json 是否可回填。

回填前的雙向錨點檢查：MANIFEST 說某批有哪些 (chapter, para_index)，輸出就必須
不多不少剛好涵蓋它們。少一個或多一個都會讓回填錯位，且錯位是靜默的。

同時擋掉三種非法值：不在 13 領域表裡的 domain、不在 8 值表裡的 mode，以及把
支流（Z-wisdom 等）填進 domains。
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DOMAINS = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII"}
MODES = {"observation", "proposition", "prescription", "formalization",
         "narrative", "ritual", "expression", "worked_instance"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    args = ap.parse_args()

    base = ROOT / "delegation" / args.slug
    manifest = json.loads((base / "MANIFEST.json").read_text(encoding="utf-8"))

    errors: list[str] = []
    hit_counts: dict[str, int] = {}
    mode_counts: dict[str, int] = {}
    total_rows = 0
    no_domain = 0

    for batch in manifest["batches"]:
        name = batch["file"].replace(".md", "")
        out = base / "out" / f"{name}.json"
        if not out.exists():
            errors.append(f"{name}: 輸出不存在")
            continue

        expected = {(c["chapter"], p) for c in batch["chapters"] for p in c["para_indexes"]}

        try:
            data = json.loads(out.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{name}: JSON 壞掉 {e}")
            continue

        seen: set[tuple[str, int]] = set()
        for row in data.get("rows", []):
            key = (row.get("chapter"), row.get("para_index"))
            if key in seen:
                errors.append(f"{name}: 重複 {key}")
            seen.add(key)

            doms = row.get("domains", [])
            modes = row.get("modes", [])
            bad_d = [d for d in doms if d not in DOMAINS]
            bad_m = [m for m in modes if m not in MODES]
            if bad_d:
                errors.append(f"{name} {key}: 非法 domain {bad_d}")
            if bad_m:
                errors.append(f"{name} {key}: 非法 mode {bad_m}")
            if not row.get("reason"):
                errors.append(f"{name} {key}: 缺 reason")

            total_rows += 1
            if not doms:
                no_domain += 1
            for d in doms:
                hit_counts[d] = hit_counts.get(d, 0) + 1
            for m in modes:
                mode_counts[m] = mode_counts.get(m, 0) + 1

        missing = expected - seen
        extra = seen - expected
        if missing:
            errors.append(f"{name}: 缺 {len(missing)} 段 {sorted(missing)[:5]}")
        if extra:
            errors.append(f"{name}: 多 {len(extra)} 段 {sorted(extra)[:5]}")

        print(f"{name}  {len(seen):3d}/{len(expected):3d} 段"
              f"{'  OK' if not missing and not extra else '  ✗'}")

    print(f"\n共 {total_rows} 段，其中 {no_domain} 段無領域"
          f"（{no_domain / total_rows * 100:.0f}%）" if total_rows else "")
    order = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII"]
    print("領域： " + "  ".join(f"{d}={hit_counts.get(d, 0)}" for d in order))
    print("姿態： " + "  ".join(f"{m}={c}" for m, c in sorted(
        mode_counts.items(), key=lambda kv: -kv[1])))

    if errors:
        print(f"\n[FAIL] {len(errors)} 個問題：")
        for e in errors[:40]:
            print("  " + e)
        return 1
    print("\n[OK] 錨點與值域全過，可回填")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
