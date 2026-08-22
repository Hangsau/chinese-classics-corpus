#!/usr/bin/env python3
"""逐條核對通讀報告的引句歸屬。

蔡中郎集那次假 FAIL 的引句「在語料裡確實存在」，只是存在於別章——
所以「引句出現在本群語料某處」不是有效檢查，必須對它被掛的那一個
(章名, 段序) 比對。本腳本做的就是這件事。

    PYTHONIOENCODING=utf-8 python scripts/check-reading-attribution.py <slug> [gNN ...]
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CH_RE = re.compile(r'^##\s+(.+?)（\d+\s*段）\s*$')
PARA_RE = re.compile(r'^\[(\d+)\]\s*(.*)$')
# 段序欄有時附註經注別，寫成 [2]（注）
IDX_RE = re.compile(r'^\[(\d+)\]\s*(?:[（(][^）)]*[）)])?$')
QUOTE_RE = re.compile(r'「([^「」]+)」')


# 風俗通義首版 16 條錨點對不上就是這一類；肉眼看不出來，必須機械分流
VARIANTS = str.maketrans({
    '爲': '為', '竝': '並', '皁': '皂', '菸': '於', '揔': '總',
    '“': '「', '”': '」', '‘': '『', '’': '』',
})


def fold(s: str) -> str:
    return s.translate(VARIANTS)


def norm_chapter(cell: str) -> str:
    """章名欄在不同群裡分別寫成 「X」／`X`／裸 X，一律剝成裸名。"""
    s = cell.strip()
    for a, b in (('「', '」'), ('`', '`'), ('“', '”')):
        if s.startswith(a) and s.endswith(b) and len(s) > len(a) + len(b) - 1:
            s = s[len(a):-len(b)]
    return s.strip()


def load_batches(slug: str) -> dict:
    """(章名, 段序) -> (批次, 段文)"""
    out = {}
    for path in sorted((ROOT / 'delegation' / slug).glob('b*.md')):
        chapter = None
        for line in path.read_text(encoding='utf-8').splitlines():
            m = CH_RE.match(line)
            if m:
                chapter = m.group(1).strip()
                continue
            m = PARA_RE.match(line)
            if m and chapter:
                out[(chapter, int(m.group(1)))] = (path.stem, m.group(2))
    return out


def check(slug: str, report: Path, batches: dict):
    rows = quotes = bad_key = 0
    kinds = {'掛錯段': 0, '異體字': 0, '查無': 0}
    problems = []
    folded = {k: fold(v[1]) for k, v in batches.items()}
    section = '(前言)'
    seen, parsed = {}, {}
    for lineno, line in enumerate(report.read_text(encoding='utf-8').splitlines(), 1):
        if line.startswith('## '):
            section = line[3:].strip()
            continue
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) < 3:
            continue
        if cells[1] == '段序':      # 這張表宣告了段序欄，底下每一列都該解析得到
            seen[section] = seen.get(section, 0)
            continue
        if set(cells[1]) <= set('-: '):
            continue
        if section in seen:
            seen[section] += 1
        m = IDX_RE.match(cells[1])
        if not m:
            continue
        parsed[section] = parsed.get(section, 0) + 1
        rows += 1
        chapter, idx = norm_chapter(cells[0]), int(m.group(1))
        key = (chapter, idx)
        if key not in batches:
            bad_key += 1
            problems.append(f'  L{lineno} 段不存在：{chapter}[{idx}]')
            continue
        _batch, text = batches[key]
        for q in QUOTE_RE.findall(' | '.join(cells[2:])):
            quotes += 1
            if q in text:
                continue
            if fold(q) in folded[key]:
                kind, where = '異體字', ''
            else:
                elsewhere = [f'{c}[{i}]' for (c, i), t in folded.items() if fold(q) in t]
                kind = '掛錯段' if elsewhere else '查無'
                where = f'（實在 {"、".join(elsewhere[:3])}）' if elsewhere else ''
            kinds[kind] += 1
            problems.append(
                f'  L{lineno} {kind} {chapter}[{idx}]：「{q[:28]}」{where}')
    # 「0 錯」可能只是解析器沒咬到：宣告了段序欄卻一列都沒解析出來要當失敗
    skipped = [(s, n) for s, n in seen.items() if n and not parsed.get(s)]
    bad_quote = sum(kinds.values())
    print(f'{report.name}  表列 {rows}  引句 {quotes}  段不存在 {bad_key}  '
          f'引句不合 {bad_quote}（掛錯段 {kinds["掛錯段"]} '
          f'異體字 {kinds["異體字"]} 查無 {kinds["查無"]}）')
    for s, n in skipped:
        print(f'  ⚠ 整節未解析：{s}（{n} 列有段序欄卻一列都沒咬到，格式可能又漂移了）')
    for p in problems[:40]:
        print(p)
    if len(problems) > 40:
        print(f'  …另有 {len(problems) - 40} 條')
    return rows, quotes, bad_key + bad_quote + len(skipped)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    slug = sys.argv[1]
    batches = load_batches(slug)
    if not batches:
        sys.exit(f'找不到 delegation/{slug}/b*.md')
    rdir = ROOT / 'delegation' / slug / 'reading'
    names = sys.argv[2:]
    reports = [rdir / f'{n}.md' for n in names] if names else sorted(rdir.glob('g*.md'))
    print(f'{slug}：語料 {len(batches)} 段，報告 {len(reports)} 份')
    tr = tq = tb = 0
    for r in reports:
        if not r.exists() or not r.stat().st_size:
            print(f'{r.name}  （缺或空）')
            continue
        a, b, c = check(slug, r, batches)
        tr, tq, tb = tr + a, tq + b, tb + c
    print(f'合計 表列 {tr}  引句 {tq}  錯 {tb}')
    return 1 if tb else 0


if __name__ == '__main__':
    sys.exit(main())
