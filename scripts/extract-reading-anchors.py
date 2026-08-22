#!/usr/bin/env python3
"""把通讀報告 §2–§6 的表格抽成結構化清單，並逐條回 raw/original.txt 對拍。

寫這支腳本的理由與 `check-reading-attribution.py` 相同：通讀報告的引句是寫 SPEC 錨點的唯一
素材，但人抄表格會漏、會走樣（蔡中郎集把他章引句抄進 SPEC 變成假 FAIL）。差別是那一支只查
「引句是否掛對段」，這一支還要把「它屬於哪一節（A 側／B 側／神異四側／考辨／超長段）」帶出來，
因為 SPEC 的三種錨點（必須命中／必須判空／禁填）各由不同節供料。

用法：
    PYTHONIOENCODING=utf-8 python scripts/extract-reading-anchors.py <slug> [gNN ...]
    PYTHONIOENCODING=utf-8 python scripts/extract-reading-anchors.py <slug> --json out.json

表格格式在各群之間會漂（章名寫成 `「X」`／`` `X` ``／裸 X，段序寫成 `[2]`／`[2]（注）`），
解析器一律寫寬——這是已經踩過兩次的「零列＝假合格」。凡認出的列數與報告篇幅不相稱，
先懷疑解析器沒咬到，不要相信 0 錯。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from corpus_text import split_paragraphs  # noqa: E402

SECTION_RE = re.compile(r"^##\s*§(\d+)")
PARA_RE = re.compile(r"\[(\d+)\]")
QUOTE_RE = re.compile(r"「([^「」]*(?:「[^「」]*」[^「」]*)*)」")

SECTION_KIND = {
    "2": "A",       # 傾向命中
    "3": "B",       # 傾向判空
    "4": "shen",    # 神異四側
    "5": "kaobian", # 考辨按語
    "6": "long",    # 超長段
}


def strip_shell(cell: str) -> str:
    """剝掉章名欄的各種殼：「」、`` ` ``、** **、以及尾隨的（注）（經）標記。"""
    s = cell.strip()
    s = re.sub(r"\*\*", "", s)
    s = s.strip()
    for a, b in (("「", "」"), ("`", "`"), ("《", "》")):
        if s.startswith(a) and s.endswith(b) and len(s) > 1:
            s = s[1:-1].strip()
    return s


def norm(s: str) -> str:
    """比對用正規化：只留漢字與常見異體折疊，去標點空白與 markdown。"""
    s = re.sub(r"<br\s*/?>", "", s)
    s = re.sub(r"[*`]", "", s)
    table = str.maketrans({"爲": "為", "竝": "並", "於": "于", "羣": "群", "牀": "床"})
    s = s.translate(table)
    return "".join(ch for ch in s if "一" <= ch <= "鿿")


def load_paras(slug: str) -> dict[tuple[str, int], str]:
    raw = ROOT / "translations" / slug / "raw" / "original.txt"
    out = {}
    for _, chapter, para_index, text in split_paragraphs(raw.read_text(encoding="utf-8")):
        out[(chapter, para_index)] = text
    return out


def parse_report(path: Path) -> list[dict]:
    rows = []
    section = None
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = SECTION_RE.match(line)
        if m:
            section = SECTION_KIND.get(m.group(1))
            continue
        if section is None or not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or set("".join(cells)) <= set("-: "):
            continue
        para = PARA_RE.search(cells[1]) if len(cells) > 1 else None
        if not para:
            continue
        chapter = strip_shell(cells[0])
        if not chapter:
            continue
        quotes = []
        for cell in cells[2:]:
            quotes.extend(QUOTE_RE.findall(cell))
        # 神異四側的「側」欄在第 3 格，抽出來當標籤
        label = ""
        for cell in cells[2:4]:
            for key in ("技術", "認證", "破除", "過度"):
                if key in cell and len(cell) <= 8:
                    label = key
        rows.append({
            "source": path.name,
            "line": lineno,
            "section": section,
            "chapter": chapter,
            "para_index": int(para.group(1)),
            "label": label,
            "quotes": quotes,
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("groups", nargs="*")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    reading = ROOT / "delegation" / args.slug / "reading"
    files = sorted(reading.glob("g*.md"))
    if args.groups:
        want = set(args.groups)
        files = [f for f in files if f.stem in want]
    if not files:
        print("no reading reports found under %s" % reading)
        return 2

    paras = load_paras(args.slug)
    rows = []
    for f in files:
        rows.extend(parse_report(f))

    ok = miswired = missing = 0
    problems = []
    for row in rows:
        text = paras.get((row["chapter"], row["para_index"]))
        row["exists"] = text is not None
        row["verified"] = []
        for q in row["quotes"]:
            nq = norm(q)
            if not nq:
                continue
            if text is not None and nq in norm(text):
                row["verified"].append(True)
                ok += 1
                continue
            elsewhere = [k for k, v in paras.items() if nq in norm(v)]
            row["verified"].append(False)
            if elsewhere:
                miswired += 1
                problems.append("掛錯段 %s %s[%d] → 實在 %s"
                                % (row["source"], row["chapter"], row["para_index"],
                                   "／".join("%s[%d]" % k for k in elsewhere[:3])))
            else:
                missing += 1
                problems.append("查無 %s %s[%d] 「%s」"
                                % (row["source"], row["chapter"], row["para_index"], q[:30]))

    by_section: dict[str, int] = {}
    for row in rows:
        by_section[row["section"]] = by_section.get(row["section"], 0) + 1
    print("報告 %d 份，表列 %d 列，引句 %d 條" % (len(files), len(rows), ok + miswired + missing))
    print("  分節：" + "／".join("%s %d" % kv for kv in sorted(by_section.items())))
    print("  對拍：符合 %d／掛錯段 %d／查無 %d" % (ok, miswired, missing))
    for p in problems:
        print("  " + p)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        print("寫入 %s" % args.json_out)
    return 1 if (miswired or missing) else 0


if __name__ == "__main__":
    raise SystemExit(main())
