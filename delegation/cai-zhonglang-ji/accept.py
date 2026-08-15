"""蔡中郎集 A 類驗收（碑誄體陷阱，硬條件）。

錨點清單一律從 SPEC.md 的三張表現場解析，不在本檔手抄——孔叢子那次
18 個假 FAIL 的成因就是驗收器自己抄了一份沒被驗證過的清單。

用法：
  PYTHONIOENCODING=utf-8 python delegation/cai-zhonglang-ji/accept.py --check-spec
      發包前跑：驗證 SPEC 的章名、段號、引句在 bNN.md 裡逐字存在。
  PYTHONIOENCODING=utf-8 python delegation/cai-zhonglang-ji/accept.py [b01 ...]
      回收後跑；不給批次就檢查 out/ 底下所有已存在的批次。
"""
import glob
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DOMS = ['XIII', 'XII', 'XI', 'X', 'IX', 'VIII', 'VII', 'VI', 'V', 'IV', 'III', 'II', 'I']

N_EMPTY_CH, N_EMPTY_PARA = 18, 18  # 整章判空：章數／段數
N_EMPTY_ANCHOR = 19                # 逐段判空錨點
N_HIT = 30                         # 逐段命中錨點

# 同型異判的對照組：(判空章, 判空段, 命中章, 命中段, 差別)
PAIRS = [
    ('桓彬論', 1, '真定直父碑', 1, '全章一句品題，差別只在有無方法與後果'),
    ('盤銘', 1, '樽銘', 1, '同為器銘，差別只在有無轉出箴言'),
    ('《太傅安樂鄉文恭侯胡公碑》', 2, '《太傅安樂鄉文恭侯胡公碑》', 1, '同章相鄰兩段判相反方向'),
]


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
    empty_ch, empty, hit = [], [], []
    for sec in re.split(r'^## ', spec, flags=re.M):
        if sec.startswith('必須整章判空的章'):
            target, kind = empty_ch, 'ch'
        elif sec.startswith('必須判空的錨點'):
            target, kind = empty, 'para'
        elif sec.startswith('必須命中的錨點'):
            target, kind = hit, 'para'
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
    return empty_ch, empty, hit


def parse_req(cell):
    """把「必須含」欄解析成 (mode, [domains])。／ 是至少一，＋ 是全含。"""
    body = re.sub(r'（[^）]*）', '', cell).replace('*', '').strip()
    toks = [t for t in re.split(r'[^IVX]+', body) if t in DOMS]
    mode = 'and' if ('＋' in body or '+' in body) else 'or'
    return mode, toks


def check_spec():
    """發包前自檢：SPEC 宣告的每個錨點都要在 bNN.md 裡真的存在。"""
    paras, chapter_len = read_batches()
    empty_ch, empty, hit = parse_spec()
    bad = []

    print('批次檔：%d 章 %d 段' % (len(chapter_len), len(paras)))
    print('SPEC：整章判空 %d 章／逐段判空 %d 段／必須命中 %d 段'
          % (len(empty_ch), len(empty), len(hit)))

    if (len(empty_ch), len(empty), len(hit)) != (N_EMPTY_CH, N_EMPTY_ANCHOR, N_HIT):
        bad.append('S0 解析數與宣告的 %d/%d/%d 不符'
                   % (N_EMPTY_CH, N_EMPTY_ANCHOR, N_HIT))

    total = 0
    for ch, n, batch in empty_ch:
        if ch not in chapter_len:
            bad.append('S1 整章判空章名不存在：%s' % ch)
            continue
        real_batch, real_n = chapter_len[ch]
        if real_n != n:
            bad.append('S2 整章判空 %s 段數 SPEC 寫 %d，實際 %d' % (ch, n, real_n))
        if real_batch != batch:
            bad.append('S2 整章判空 %s 批次 SPEC 寫 %s，實際 %s' % (ch, batch, real_batch))
        total += real_n
    if total != N_EMPTY_PARA:
        bad.append('S3 整章判空段數合計 %d ≠ 宣告的 %d' % (total, N_EMPTY_PARA))

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

    for ch, idx, cell in [(c, i, r) for c, i, _, _, r in hit]:
        mode, need = parse_req(cell)
        if not need:
            bad.append('S9 %s[%d] 必須含欄解不出領域：%s' % (ch, idx, cell))

    # S10 對照組兩側都要在 SPEC 的表裡被寫死
    void_keys = {(c, i) for c, i, *_ in empty}
    for vc, vi, hc, hi, _ in PAIRS:
        if (vc, vi) not in void_keys and vc not in empty_ch_names:
            bad.append('S10 對照組判空側未寫死：%s[%d]' % (vc, vi))
        if (hc, hi) not in hit_keys:
            bad.append('S10 對照組命中側未寫死：%s[%d]' % (hc, hi))

    print('--- SPEC 自檢 FAIL：%d ---' % len(bad))
    for b in bad:
        print(b)
    return 0 if not bad else 1


def main():
    if '--check-spec' in sys.argv:
        return check_spec()

    empty_ch, empty, hit = parse_spec()
    if (len(empty_ch), len(empty), len(hit)) != (N_EMPTY_CH, N_EMPTY_ANCHOR, N_HIT):
        print('!! SPEC 解析數不符宣告值，先跑 --check-spec')
        return 2

    want = [a for a in sys.argv[1:] if not a.startswith('-')]
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

    # A4 逐段命中
    for ch, idx, batch, _, cell in hit:
        if batch not in got_batches:
            skipped += 1
            continue
        r = rows.get((ch, idx))
        if r is None:
            fails.append('A1 缺段 %s[%d]' % (ch, idx))
            continue
        mode, need = parse_req(cell)
        d = r['domains']
        if mode == 'and':
            if [x for x in need if x not in d]:
                fails.append('A4 缺格 %s[%d] 需 %s 全含，實得 %s' % (ch, idx, need, d))
        elif not any(x in d for x in need):
            fails.append('A4 缺格 %s[%d] 需 %s 至少一，實得 %s' % (ch, idx, need, d))

    # A5 同型異判的對照組（判準切得準不準的試金石）
    for vc, vi, hc, hi, why in PAIRS:
        rv, rh = rows.get((vc, vi)), rows.get((hc, hi))
        if rv is None or rh is None:
            continue
        if rv['domains']:
            fails.append('A5 對照組判空側卻命中 %s[%d] → %s（%s）' % (vc, vi, rv['domains'], why))
        if not rh['domains']:
            fails.append('A5 對照組命中側卻判空 %s[%d]（%s）' % (hc, hi, why))

    # A6 worked_instance 全書掛零
    bad = [(c, i) for (c, i), r in rows.items() if 'worked_instance' in r.get('modes', [])]
    if bad:
        fails.append('A6 worked_instance 應 0 段，實得 %d：%s' % (len(bad), bad[:5]))

    # A7 碑誄章群的判空率（詞面陷阱有沒有把整批撈走）
    n_empty = sum(1 for r in rows.values() if not r['domains'])
    print('判空 %d/%d（%.0f%%）' % (n_empty, len(rows), 100 * n_empty / len(rows)))
    print('\n跳過（該批未回收）：%d 條錨點' % skipped)
    print('--- A 類 FAIL：%d ---' % len(fails))
    for f in fails:
        print(f)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
