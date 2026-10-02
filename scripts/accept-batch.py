#!/usr/bin/env python3
"""通用逐批驗收：python scripts/accept-batch.py <slug> b05

錨點不在本檔手抄，現場解析 delegation/<slug>/SPEC.md 的「## 驗收錨點」表格
（| 章名 | 段 | 條件 | 依據 |，條件寫 `判空`／`必含 X`／`不得含 X`）。

A 類（任一不過即 FAIL）：
  A1 rows 恰好涵蓋 MANIFEST 該批的 (chapter, para_index)，不多不少不重複
  A2 domains／modes 值域合法、modes 1–2 個、domains 至多 3 個、reason 非空
  A3 位置錨點（SPEC 表格）
  A4 reason 引句逐字在本段（4 字以上的「…」／“…”，…… 節引分段比），不符 >1 條即 FAIL

    python scripts/accept-batch.py <slug> --check-spec   # 只驗 SPEC 錨點表本身：每列都解析得出、章段存在
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from corpus_text import read_paragraphs  # noqa: E402

DOMAINS = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII"}
MODES = {"observation", "proposition", "prescription", "formalization", "narrative", "ritual",
         "expression", "worked_instance"}
ROW_RE = re.compile(r"^\|\s*`?([^|`]+?)`?\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|")


def parse_anchors(spec: str) -> tuple[dict, int]:
    """回傳 ({(章, 段): [條件, ...]}, 表格資料列數)；條件總數與列數不等代表有列沒解析出來。"""
    sec = spec.split("## 驗收錨點", 1)[1].split("\n## ", 1)[0]
    rows = [l for l in sec.splitlines() if l.startswith("|") and not re.match(r"^\|\s*(章名|-)", l)]
    anchors = {}
    for l in rows:
        m = ROW_RE.match(l)
        if not m:
            continue
        cond = m.group(3)
        if cond == "判空":
            a = ("empty", None)
        elif c := re.fullmatch(r"必含\s*(\w+)", cond):
            a = ("has", c.group(1))
        elif c := re.fullmatch(r"不得含\s*(\w+)", cond):
            a = ("no", c.group(1))
        else:
            continue
        anchors.setdefault((m.group(1).strip(), int(m.group(2))), []).append(a)
    return anchors, len(rows)


def main(slug: str, b: str) -> int:
    base = ROOT / "delegation" / slug
    anchors, nrows = parse_anchors((base / "SPEC.md").read_text(encoding="utf-8"))
    text = {(c, i): t for _, c, i, t in read_paragraphs(ROOT / "translations" / slug)}
    if b == "--check-spec":
        bad = [k for k in anchors if k not in text]
        n = sum(map(len, anchors.values()))
        print(f"錨點條件 {n}／表格 {nrows} 列；不存在的章段 {bad}")
        return 0 if n == nrows and not bad and nrows else 1
    if sum(map(len, anchors.values())) != nrows:
        print(f"[FAIL] SPEC 錨點表 {nrows} 列只解析出 {sum(map(len, anchors.values()))} 條")
        return 1
    man = json.loads((base / "MANIFEST.json").read_text(encoding="utf-8"))
    batch = next(x for x in man["batches"] if x["file"] == f"{b}.md")
    expected = {(c["chapter"], p) for c in batch["chapters"] for p in c["para_indexes"]}
    fails, notes = [], []
    try:
        rows = json.loads((base / "out" / f"{b}.json").read_text(encoding="utf-8-sig"))["rows"]
    except Exception as e:
        print(f"[FAIL] {b}: 讀不到輸出 {e}")
        return 1
    seen, foreign = set(), 0
    for r in rows:
        k = (r.get("chapter"), r.get("para_index"))
        if k in seen:
            fails.append(f"A1 重複 {k}")
        seen.add(k)
        d, m, why = r.get("domains"), r.get("modes"), r.get("reason") or ""
        if not isinstance(d, list) or set(d) - DOMAINS or len(d) > 3:
            fails.append(f"A2 {k} domains 非法 {d}")
        if not isinstance(m, list) or set(m) - MODES or not 1 <= len(m) <= 2:
            fails.append(f"A2 {k} modes 非法 {m}")
        if not why.strip():
            fails.append(f"A2 {k} 缺 reason")
        for kind, dom in anchors.get(k, []) if isinstance(d, list) else []:
            if kind == "empty" and d:
                fails.append(f"A3 {k} 必須判空，得 {d}")
            if kind == "has" and dom not in d:
                fails.append(f"A3 {k} 必含 {dom}，得 {d}")
            if kind == "no" and dom in d:
                fails.append(f"A3 {k} 不得含 {dom}")
        body = text.get(k, "")
        for q in re.findall(r"「([^」]+)」|“([^”]+)”", why):
            q = q[0] or q[1]
            for part in re.split(r"……|…", q):
                if len(part) >= 4 and part not in body:
                    foreign += 1
                    notes.append(f"A4 {k} 引句不在本段：{part}")
    if seen - expected:
        fails.append(f"A1 多 {sorted(seen - expected)[:5]}")
    if expected - seen:
        fails.append(f"A1 缺 {sorted(expected - seen)[:5]}")
    if foreign > 1:
        fails.append(f"A4 引句不符 {foreign} 條")
    for n in notes:
        print(n)
    for f in fails:
        print("[FAIL]", f)
    hit = sum(1 for r in rows if r.get("domains"))
    print(f"{slug} {b}: {len(rows)} 段、命中 {hit}、{'0 FAIL' if not fails else f'{len(fails)} FAIL'}、引句不符 {foreign}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
