#!/usr/bin/env python3
"""淮南子逐批驗收：python delegation/huainanzi/accept.py b05

A 類（任一不過即 FAIL）：
  A1 rows 恰好涵蓋 MANIFEST 該批的 (chapter, para_index)，不多不少不重複
  A2 domains／modes 值域合法、modes 1–2 個、domains 至多 3 個、reason 非空
  A3 位置錨點（下方 ANCHORS，讀原文寫死）
  A4 reason 引句逐字在本段（4 字以上的「…」／“…”），不符 >1 條即 FAIL
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from corpus_text import read_paragraphs  # noqa: E402

BASE = Path(__file__).resolve().parent
DOMAINS = {"I","II","III","IV","V","VI","VII","VIII","IX","X","XI","XII","XIII"}
MODES = {"observation","proposition","prescription","formalization","narrative","ritual","expression","worked_instance"}
# (章, 段) -> ("empty", None) 必須判空 ／ ("has", "X") 必含某格 ／ ("no", "XII") 不得含某格
ANCHORS = {
    ("天文訓", 85): ("empty", None),      # 歲星占驗表
    ("天文訓", 40): ("empty", None),      # 歲星紀年
    ("墬形訓", 10): ("empty", None),      # 八極八門方位
    ("要略", 1): ("no", "XII"),
    ("精神訓", 6): ("has", "X"),          # 生寄也，死歸也
    ("覽冥訓", 1): ("has", "XII"),        # 上天之誅也……無所逃
    ("時則訓", 1): ("no", "XII"),         # 月令：其帝其神是曆法登錄
    ("時則訓", 2): ("no", "XII"),
    ("時則訓", 3): ("no", "XII"),
}


def main(b: str) -> int:
    man = json.loads((BASE / "MANIFEST.json").read_text(encoding="utf-8"))
    batch = next(x for x in man["batches"] if x["file"] == f"{b}.md")
    expected = {(c["chapter"], p) for c in batch["chapters"] for p in c["para_indexes"]}
    text = {(c, i): t for _, c, i, t in read_paragraphs(ROOT / "translations" / "huainanzi")}
    fails, notes = [], []
    try:
        rows = json.loads((BASE / "out" / f"{b}.json").read_text(encoding="utf-8"))["rows"]
    except Exception as e:
        print(f"[FAIL] {b}: 讀不到輸出 {e}")
        return 1
    seen = set()
    foreign = 0
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
        a = ANCHORS.get(k)
        if a and isinstance(d, list):
            kind, dom = a
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
    print(f"{b}: {len(rows)} 段、命中 {hit}、{'0 FAIL' if not fails else f'{len(fails)} FAIL'}、引句不符 {foreign}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
