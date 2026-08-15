"""獨斷 A 類驗收（體裁陷阱，硬條件）。

錨點清單一律從 SPEC.md 的四張表現場解析，不在本檔手抄——孔叢子那次
18 個假 FAIL 的成因就是驗收器自己抄了一份沒被驗證過的清單。

用法：
  PYTHONIOENCODING=utf-8 python delegation/duduan/accept.py --check-spec
      發包前跑：驗證 SPEC 的章名、段號、引句在 bNN.md 裡逐字存在。
  PYTHONIOENCODING=utf-8 python delegation/duduan/accept.py [b01 ...]
      回收後跑；不給批次就檢查 out/ 底下所有已存在的批次。
"""
import glob
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DOMS = ['XIII', 'XII', 'XI', 'X', 'IX', 'VIII', 'VII', 'VI', 'V', 'IV', 'III', 'II', 'I']

N_EMPTY_CH, N_EMPTY_PARA = 10, 84  # 整章判空：章數／段數
N_EMPTY_ANCHOR = 25                 # 逐段判空錨點
N_HIT = 9                           # 逐段命中錨點
N_RITUAL_CH, N_RITUAL_PARA = 10, 16  # 祭祀章群：章數／段數


def read_batches():
    """bNN.md -> {(chapter, para_index): (batch, text)}；同時回傳每章段數。"""
    paras, chapter_len = {}, {}
    for f in sorted(glob.glob(os.path.join(BASE, 'b0*.md'))):
        batch = os.path.basename(f)[:3]
        chapter = None
        for line in open(f, encoding='utf-8'):
            m = re.match(r'^## (.+?)（(\d+) 段）\s*$', line)
            if m:
                chapter = m.group(1)
                chapter_len[chapter] = (batch, int(m.group(2)))
                continue
            m = re.match(r'^\[(\d+)\] (.*)$', line)
            if m and chapter is not None:
                paras[(chapter, int(m.group(1)))] = (batch, m.group(2).rstrip('\n'))
    return paras, chapter_len


def parse_spec():
    spec = open(os.path.join(BASE, 'SPEC.md'), encoding='utf-8').read()
    empty_ch, empty, hit, ritual_ch = [], [], [], []
    for sec in re.split(r'^## ', spec, flags=re.M):
        if sec.startswith('必須整章判空的章'):
            target, kind = empty_ch, 'ch'
        elif sec.startswith('必須判空的錨點'):
            target, kind = empty, 'para'
        elif sec.startswith('必須命中的錨點'):
            target, kind = hit, 'para'
        elif sec.startswith('祭祀章群'):
            target, kind = ritual_ch, 'ch'
        else:
            continue
        for line in sec.split('\n'):
            if kind == 'ch':
                m = re.match(r'^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*段?\s*\|\s*(b0\d)\s*\|', line)
                if m:
                    target.append((m.group(1), int(m.group(2)), m.group(3)))
            else:
                m = re.match(r'^\|\s*`([^`]+)`\[(\d+)\]\s*\|\s*(.*?)\s*\|\s*(b0\d)\s*\|\s*(.*?)\s*\|\s*$',
                             line)
                if m:
                    target.append((m.group(1), int(m.group(2)), m.group(4),
                                   m.group(3), m.group(5)))
    return empty_ch, empty, hit, ritual_ch


def parse_req(cell):
    """把「必須含」欄解析成 (mode, [domains], forbid_xii)。"""
    forbid = '不得含 XII' in cell
    body = re.sub(r'（[^）]*）', '', cell).replace('*', '').strip()
    toks = [t for t in re.split(r'[^IVX]+', body) if t in DOMS]
    mode = 'and' if ('＋' in body or '+' in body) else 'or'
    return mode, toks, forbid


def check_spec():
    """發包前自檢：SPEC 宣告的每個錨點都要在 bNN.md 裡真的存在。"""
    paras, chapter_len = read_batches()
    empty_ch, empty, hit, ritual_ch = parse_spec()
    bad = []

    print('批次檔：%d 章 %d 段' % (len(chapter_len), len(paras)))
    print('SPEC：整章判空 %d 章／逐段判空 %d 段／必須命中 %d 段／祭祀章群 %d 章'
          % (len(empty_ch), len(empty), len(hit), len(ritual_ch)))

    if (len(empty_ch), len(empty), len(hit), len(ritual_ch)) != \
            (N_EMPTY_CH, N_EMPTY_ANCHOR, N_HIT, N_RITUAL_CH):
        bad.append('S0 解析數與宣告的 %d/%d/%d/%d 不符'
                   % (N_EMPTY_CH, N_EMPTY_ANCHOR, N_HIT, N_RITUAL_CH))

    for name, rows, want_total in (('整章判空', empty_ch, N_EMPTY_PARA),
                                   ('祭祀章群', ritual_ch, N_RITUAL_PARA)):
        total = 0
        for ch, n, batch in rows:
            if ch not in chapter_len:
                bad.append('S1 %s 章名不存在：%s' % (name, ch))
                continue
            real_batch, real_n = chapter_len[ch]
            if real_n != n:
                bad.append('S2 %s %s 段數 SPEC 寫 %d，實際 %d' % (name, ch, n, real_n))
            if real_batch != batch:
                bad.append('S2 %s %s 批次 SPEC 寫 %s，實際 %s' % (name, ch, batch, real_batch))
            total += real_n
        if total != want_total:
            bad.append('S3 %s 段數合計 %d ≠ 宣告的 %d' % (name, total, want_total))

    empty_ch_names = {c for c, _, _ in empty_ch}
    for label, rows in (('判空', empty), ('命中', hit)):
        for ch, idx, batch, quote_cell, _ in rows:
            got = paras.get((ch, idx))
            if got is None:
                bad.append('S4 %s錨點不存在：%s[%d]' % (label, ch, idx))
                continue
            if got[0] != batch:
                bad.append('S5 %s[%d] 批次 SPEC 寫 %s，實際 %s' % (ch, idx, batch, got[0]))
            for q in re.findall(r'「([^「」]+)」', quote_cell):
                if q not in got[1]:
                    bad.append('S6 引句不在原文：%s[%d]「%s」' % (ch, idx, q))
            if ch in empty_ch_names:
                bad.append('S7 %s[%d] 同時落在整章判空表，重複' % (ch, idx))

    hit_keys = {(c, i) for c, i, *_ in hit}
    for ch, idx, *_ in empty:
        if (ch, idx) in hit_keys:
            bad.append('S8 %s[%d] 同時在判空表與命中表' % (ch, idx))

    for ch, idx, batch, cell in [(c, i, b, r) for c, i, b, _, r in hit]:
        mode, need, _ = parse_req(cell)
        if not need:
            bad.append('S9 %s[%d] 必須含欄解不出領域：%s' % (ch, idx, cell))

    print('--- SPEC 自檢 FAIL：%d ---' % len(bad))
    for b in bad:
        print(b)
    return 0 if not bad else 1


def main():
    if '--check-spec' in sys.argv:
        return check_spec()

    empty_ch, empty, hit, ritual_ch = parse_spec()
    if (len(empty_ch), len(empty), len(hit), len(ritual_ch)) != \
            (N_EMPTY_CH, N_EMPTY_ANCHOR, N_HIT, N_RITUAL_CH):
        print('!! SPEC 解析數不符宣告值，先跑 --check-spec')
        return 2

    want = sys.argv[1:]
    rows, got_batches = {}, []
    for f in sorted(glob.glob(os.path.join(BASE, 'out', 'b0*.json'))):
        b = os.path.basename(f)[:3]
        if want and b not in want:
            continue
        got_batches.append(b)
        data = json.load(open(f, encoding='utf-8'))
        for r in data['rows']:
            rows[(r['chapter'], int(r['para_index']))] = r
    print('回收批次：%s，共 %d 段' % (' '.join(got_batches) or '(無)', len(rows)))
    if not rows:
        return 1

    fails, skipped = [], 0

    # A2 整章判空
    for ch, n, batch in empty_ch:
        if batch not in got_batches:
            skipped += n
            continue
        got = [(i, r) for (c, i), r in rows.items() if c == ch]
        if len(got) != n:
            fails.append('A2 %s 應 %d 段，回收 %d 段' % (ch, n, len(got)))
        for i, r in sorted(got):
            if r['domains']:
                fails.append('A2 應判空卻命中 %s[%d] → %s' % (ch, i, r['domains']))

    # A3 逐段判空
    for ch, idx, batch, _, _ in empty:
        if batch not in got_batches:
            skipped += 1
            continue
        r = rows.get((ch, idx))
        if r is None:
            fails.append('A1 缺段 %s[%d]' % (ch, idx))
        elif r['domains']:
            fails.append('A3 應判空卻命中 %s[%d] → %s' % (ch, idx, r['domains']))

    # A4/A5 逐段命中
    for ch, idx, batch, _, cell in hit:
        if batch not in got_batches:
            skipped += 1
            continue
        r = rows.get((ch, idx))
        if r is None:
            fails.append('A1 缺段 %s[%d]' % (ch, idx))
            continue
        mode, need, forbid = parse_req(cell)
        d = r['domains']
        if mode == 'and':
            if [x for x in need if x not in d]:
                fails.append('A4 缺格 %s[%d] 需 %s 全含，實得 %s' % (ch, idx, need, d))
        elif not any(x in d for x in need):
            fails.append('A4 缺格 %s[%d] 需 %s 至少一，實得 %s' % (ch, idx, need, d))
        if forbid and 'XII' in d:
            fails.append('A5 不得含 XII 卻含 %s[%d] → %s' % (ch, idx, d))

    # A6 祭祀章群 ＋ 卷下[1] 不得含 XII
    ritual_names = {c for c, _, _ in ritual_ch}
    for (c, i), r in rows.items():
        if c in ritual_names and 'XII' in r['domains']:
            fails.append('A6 祭祀章群含 XII %s[%d] → %s' % (c, i, r['domains']))
    r = rows.get(('卷下', 1))
    if r is not None and 'XII' in r['domains']:
        fails.append('A6 卷下[1] 五德相生譜含 XII → %s' % r['domains'])

    # A7 五祀之別名 vs 五祀之別名（祀臣五義）
    wu = [(i, r) for (c, i), r in rows.items() if c == '五祀之別名']
    if len(wu) == 3 and any(r['domains'] for _, r in wu):
        fails.append('A7 五祀之別名 應 3 段全判空，實得 %s' % [r['domains'] for _, r in wu])
    si = rows.get(('五祀之別名（祀臣五義）', 1))
    if si is not None and not si['domains']:
        fails.append('A7 五祀之別名（祀臣五義）[1] 應命中卻判空')

    # A8 稱謂避諱章
    zh = [(i, r) for (c, i), r in rows.items() if c == '天子正號之別名']
    if len(zh) == 18:
        n_hit = sum(1 for _, r in zh if r['domains'])
        print('天子正號之別名命中 %d/18' % n_hit)
        if n_hit > 3:
            fails.append('A8 天子正號之別名命中 %d > 3，稱謂避諱被硬撈' % n_hit)
        r9 = dict(zh).get(9)
        if r9 is not None and not r9['domains']:
            fails.append('A8 天子正號之別名[9] 應命中卻判空')

    # A9 兩個 mode 全書掛零
    for m in ('worked_instance', 'expression'):
        bad = [(c, i) for (c, i), r in rows.items() if m in r.get('modes', [])]
        if bad:
            fails.append('A9 %s 應 0 段，實得 %d：%s' % (m, len(bad), bad[:5]))

    n_empty = sum(1 for r in rows.values() if not r['domains'])
    print('判空 %d/%d（%.0f%%）' % (n_empty, len(rows), 100 * n_empty / len(rows)))
    print('\n跳過（該批未回收）：%d 條錨點' % skipped)
    print('--- A 類 FAIL：%d ---' % len(fails))
    for f in fails:
        print(f)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
