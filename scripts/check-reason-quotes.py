"""檢查 delegation/<slug>/out/*.json 的 reason 引句是否逐字出自該段自己的正文。

CLAUDE.md 規定回收後要主動查兩件事，第一件是「命中段的 reason 有沒有引到本段自己
的文字（而不是複述 spec）」。這是蔡中郎集踩過的破口：通讀報告的理由欄引號有三種
來源（本段逐字、**他章的對照引句**、通讀者自己的概括），抄進 SPEC 或寫進 reason
後，按段對拍就會變成假 FAIL 或假 PASS。

判準：reason 裡每一段 `「…」` 或 `“…”` 都必須是該段正文的子字串。
- **兩種引號都要抽**：本庫底本的引號體例逐批不同（吳越春秋 b02–b05、b10 用彎引號，
  b01 用直角引號），judge 會跟著底本走。只抽 `「…」` 會把彎引號批次整批誤判成
  「有格無引句」，而總結行仍印「0 條不在本段」——綠得像通過，實際只比對了
  125 段裡的 16 段。這與晏子 S11 是同一種靜默失效：斷言還活著，但覆蓋率悄悄掉了。
- 節引用 `……` 連接的，逐段各自比對（`嬰之族……待嬰以祀其先人者五百家` 算合法）
- 太短的引號（少於 4 字）多半是詞語標記不是承重句，不比對
- 有 domains 卻一句都沒引，單獨列出——那是複述 spec 的徵候

用法:
    python scripts/check-reason-quotes.py --slug yanzi-chunqiu
    python scripts/check-reason-quotes.py --slug yanzi-chunqiu --batch b02
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_LEN = 4


def load_paragraphs(base: Path) -> dict[tuple[str, int], str]:
    """從發包單位 b*.md 讀回每段正文。"""
    para: dict[tuple[str, int], str] = {}
    for f in sorted(base.glob("b*.md")):
        chapter = None
        for line in f.read_bytes().decode("utf-8").split("\n"):
            m = re.match(r"^## (.+?)（\d+ 段）", line)
            if m:
                chapter = m.group(1)
                continue
            m = re.match(r"^\[(\d+)\] (.*)", line)
            if m and chapter:
                para[(chapter, int(m.group(1)))] = m.group(2)
    return para


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--batch", help="只查單一批次，例如 b02")
    args = ap.parse_args()

    base = ROOT / "delegation" / args.slug
    para = load_paragraphs(base)
    if not para:
        print(f"{base} 底下讀不到 b*.md 的段落")
        return 1

    pattern = f"{args.batch}.json" if args.batch else "*.json"
    files = sorted((base / "out").glob(pattern))
    if not files:
        print(f"{base / 'out'} 底下沒有 {pattern}")
        return 1

    foreign: list[str] = []
    silent: list[str] = []
    checked = 0

    for f in files:
        for row in json.loads(f.read_bytes().decode("utf-8"))["rows"]:
            key = (row["chapter"], row["para_index"])
            text = para.get(key)
            if text is None:
                foreign.append(f"{f.name} {key} 不在語料裡")
                continue
            reason = str(row.get("reason") or "")
            quotes = [q for q in (re.findall(r"「([^」]+)」", reason)
                                  + re.findall(r"“([^”]+)”", reason))
                      if len(q.replace("……", "")) >= MIN_LEN]
            if row.get("domains") and not quotes:
                silent.append(f"{key[0]}[{key[1]}] 標了 "
                              f"{len(row['domains'])} 格卻沒有引句")
            for q in quotes:
                for piece in [p for p in q.split("……") if len(p) >= MIN_LEN]:
                    checked += 1
                    if piece not in text:
                        foreign.append(f"{key[0]}[{key[1]}] 引句不在本段：{piece[:40]}")

    for line in foreign:
        print(f"[FOREIGN] {line}")
    for line in silent:
        print(f"[NOQUOTE] {line}")
    print(f"\n{len(files)} 批 / 比對 {checked} 段引句："
          f"{len(foreign)} 條不在本段、{len(silent)} 段有格無引句")
    return 0 if not foreign and not silent else 1


if __name__ == "__main__":
    sys.exit(main())
