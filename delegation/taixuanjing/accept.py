"""太玄經 A 類驗收（體裁陷阱，硬條件）＋ B 類數量提示（只 WARN，不擋收）。

錨點一律從 SPEC.md 的三張表（必須整章判空／必須判空／必須命中）與「一格都不得
填 XII」清單現場解析，本檔不手抄任何章名、段號、引句或領域——孔叢子那次 18 個
假 FAIL 的成因就是驗收器自己抄了一份沒被驗證過的清單。SPEC 改一個字，本檔行為
就跟著變，不需要改 Python。

用法：
  PYTHONIOENCODING=utf-8 python delegation/taixuanjing/accept.py --check-spec
      發包前跑：只拿 SPEC.md 對 b01.md–b04.md，驗批次表段數／章數、章名歸屬、
      錨點段號範圍與逐字引句是否真的存在。任一不符即 FAIL（SPEC 寫錯，發包會全批白做）。
  PYTHONIOENCODING=utf-8 python delegation/taixuanjing/accept.py [b01 ...]
      回收後跑；不給批次就檢查 out/ 底下所有已存在的批次。
  PYTHONIOENCODING=utf-8 python delegation/taixuanjing/accept.py --out-dir _selftest/perfect
      對指定目錄跑（驗收器自身的反向驗證用）。
"""
import argparse
import glob
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DOM_ORDER = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII', 'XIII']
DOMS = set(DOM_ORDER)
MODES = {'observation', 'proposition', 'prescription', 'formalization',
         'narrative', 'ritual', 'expression', 'worked_instance'}


# ---------------------------------------------------------------- 批次檔

def read_batches():
    """bNN.md → paras/chapter_len/batch_chapters；順便驗章標頭段數與實際行數一致。"""
    paras, chapter_len, batch_chapters, header_bad = {}, {}, {}, []
    for f in sorted(glob.glob(os.path.join(BASE, 'b0*.md'))):
        batch = os.path.basename(f)[:3]
        batch_chapters.setdefault(batch, [])
        chapter, counts = None, {}
        for line in open(f, encoding='utf-8'):
            m = re.match(r'^## (.+?)（(\d+) 段）\s*$', line)
            if m:
                chapter = m.group(1)
                chapter_len[chapter] = (batch, int(m.group(2)))
                batch_chapters[batch].append(chapter)
                continue
            m = re.match(r'^\[(\d+)\] (.*)$', line)
            if m and chapter is not None:
                paras[(chapter, int(m.group(1)))] = (batch, m.group(2).rstrip('\n'))
                counts[chapter] = counts.get(chapter, 0) + 1
        for ch in batch_chapters[batch]:
            if counts.get(ch, 0) != chapter_len[ch][1]:
                header_bad.append('%s %s 標頭寫 %d 段，實際 %d 段'
                                  % (batch, ch, chapter_len[ch][1], counts.get(ch, 0)))
    return paras, chapter_len, batch_chapters, header_bad


# ---------------------------------------------------------------- SPEC 解析

def _sections(spec):
    out = {}
    for sec in re.split(r'^## ', spec, flags=re.M):
        out[sec.split('\n', 1)[0].strip()] = sec
    return out


def parse_spec():
    """把 SPEC.md 解析成驗收所需的全部錨點與宣告值。本檔唯一的事實來源。"""
    spec = open(os.path.join(BASE, 'SPEC.md'), encoding='utf-8').read()
    secs = _sections(spec)
    s = {'empty_ch': [], 'empty': [], 'hit': [], 'xii_ch': [], 'xii_para': [],
         'batch_table': [], 'split_items': [], 'zero_modes': [], 'a8': None,
         'declared': {}, 'layers': {}, 'b_clauses': []}

    for head, body in secs.items():
        # 表一：必須整章判空 | 章 | 段數 | 批次 | 為什麼 |
        if head.startswith('必須整章判空的章'):
            for line in body.split('\n'):
                m = re.match(r'^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*(b0\d)\s*\|', line)
                if m:
                    s['empty_ch'].append((m.group(1), int(m.group(2)), m.group(3)))
        # 表二／表三：| 章[段] | 逐字引句 | 批次 | 為什麼／必須含 |
        elif head.startswith('必須判空的錨點') or head.startswith('必須命中的錨點'):
            key = 'empty' if head.startswith('必須判空') else 'hit'
            for line in body.split('\n'):
                m = re.match(r'^\|\s*`([^`]+)`\[(\d+)\]\s*\|\s*(.*?)\s*\|\s*(b0\d)\s*\|\s*(.*?)\s*\|\s*$',
                             line)
                if m:
                    s[key].append((m.group(1), int(m.group(2)), m.group(4),
                                   m.group(3), m.group(5)))
        # 一格都不得填 XII 的段
        elif head.startswith('一格都不得填 XII'):
            for m in re.finditer(r'`([^`]+)`(?:\[(\d+)\]|\s*全\s*(\d+)\s*段)', body):
                if m.group(3):
                    s['xii_ch'].append((m.group(1), int(m.group(3))))
                elif m.group(2):
                    s['xii_para'].append((m.group(1), int(m.group(2))))
        elif head.startswith('驗收條件'):
            a = body
            m = re.search(r'「必須整章判空」的 (\d+) 章共 (\d+) 段', a)
            if m:
                s['declared']['empty_ch'] = (int(m.group(1)), int(m.group(2)))
            m = re.search(r'「必須判空」的 (\d+) 段', a)
            if m:
                s['declared']['empty'] = int(m.group(1))
            m = re.search(r'「必須命中」的 (\d+) 段', a)
            if m:
                s['declared']['hit'] = int(m.group(1))
            for m in re.finditer(r'(b0\d) (\d+)', a):
                s['declared'].setdefault('rows', {})[m.group(1)] = int(m.group(2))
            for m in re.finditer(r'^\s*(\d+)\.\s*\*\*`([^`]+)`\s*一首之內[^：]*判開\*\*：(.+)$',
                                 a, re.M):
                s['split_items'].append((int(m.group(1)), m.group(2),
                                         [int(x) for x in
                                          re.findall(r'\[(\d+)\]', m.group(3))]))
            m = re.search(r'\*\*`([^`]+)`\s*(\d+) 段全判空且全部 `modes` 含 `([a-z_]+)`', a)
            if m:
                s['a8'] = (m.group(1), int(m.group(2)), m.group(3))
            s['zero_modes'] = re.findall(r'`([a-z_]+)` 全書 0 段', a)
            bsec = a.split('### B 類', 1)
            if len(bsec) == 2:
                for line in bsec[1].split('\n'):
                    if line.startswith('- '):
                        s['b_clauses'] += [c.strip() for c in line[2:].split('；') if c.strip()]

    # 批次表 | b01 | 章（段數）… | 段數 | 章數 |
    for line in spec.split('\n'):
        m = re.match(r'^\|\s*(b0\d)\s*\|\s*(.+?)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*$', line)
        if m:
            s['batch_table'].append((m.group(1), m.group(2), int(m.group(3)), int(m.group(4))))

    # 兩層定義（贊辭層 810 段＝81 首 × 10 段；玄傳七篇 64 段）
    m = re.search(r'\*\*贊辭層 (\d+) 段\*\*（(\d+) 首 × (\d+) 段）', spec)
    if m:
        s['layers']['zan'] = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r'玄傳七篇（([^）]+)）共 (\d+) 段', spec)
    if m:
        s['layers']['zhuan'] = ([x.split()[0] for x in m.group(1).split('、')],
                                int(m.group(2)))
    return s


def parse_batch_cell(cell):
    """「玄首序 1／中·周·…（30 首各 10 段）」→ [(章, 段數), ...]"""
    out = []
    for seg in cell.split('／'):
        seg = seg.strip()
        m = re.match(r'^(.+?)（(\d+) 首各 (\d+) 段）$', seg)
        if m:
            names = [x for x in m.group(1).split('·') if x]
            out += [(n, int(m.group(3))) for n in names]
            if len(names) != int(m.group(2)):
                out.append(('!首數不符:%s' % seg[:12], -1))
            continue
        m = re.match(r'^(.+?)\s+(\d+)$', seg)
        if m:
            out.append((m.group(1).strip(), int(m.group(2))))
        else:
            out.append(('!無法解析:%s' % seg[:12], -1))
    return out


def parse_req(cell):
    """「IX 或 XI（**不得含 XII**）」→ ('or', ['IX','XI'], True)"""
    forbid = ('不得含 XII' in cell) or ('不得填 XII' in cell)
    body = re.sub(r'（[^）]*）', '', cell).replace('*', '').strip()
    toks = [t for t in re.split(r'[^IVX]+', body) if t in DOMS]
    mode = 'and' if ('＋' in body or '+' in body) else 'or'
    return mode, toks, forbid


def forbid_xii_keys(s, chapter_len):
    """XII 禁用段展開成 (章, 段) 集合；再併入兩張表裡標了不得含 XII 的段。"""
    keys = set()
    for ch, n in s['xii_ch']:
        real = chapter_len.get(ch, (None, n))[1]
        keys |= {(ch, i) for i in range(1, real + 1)}
    keys |= set(s['xii_para'])
    for ch, idx, _b, _q, cell in s['hit'] + s['empty']:
        if '不得含 XII' in cell or '不得填 XII' in cell:
            keys.add((ch, idx))
    return keys


# ---------------------------------------------------------------- SPEC 自檢

def check_spec():
    paras, chapter_len, batch_chapters, header_bad = read_batches()
    s = parse_spec()
    bad = []

    print('批次檔：%d 章 %d 段' % (len(chapter_len), len(paras)))
    print('SPEC 解析：整章判空 %d 章／逐段判空 %d 段／必須命中 %d 段／XII 禁用 %d 章＋%d 段'
          % (len(s['empty_ch']), len(s['empty']), len(s['hit']),
             len(s['xii_ch']), len(s['xii_para'])))
    bad += ['S0 批次檔標頭：' + x for x in header_bad]

    # S1 SPEC 自宣告的數量 vs 三張表實際解析出的列數
    d = s['declared']
    if 'empty_ch' in d:
        n_ch, n_para = d['empty_ch']
        if len(s['empty_ch']) != n_ch:
            bad.append('S1 整章判空表 %d 章，A 類宣告 %d 章' % (len(s['empty_ch']), n_ch))
        tot = sum(n for _, n, _ in s['empty_ch'])
        if tot != n_para:
            bad.append('S1 整章判空表合計 %d 段，A 類宣告 %d 段' % (tot, n_para))
    if d.get('empty') is not None and len(s['empty']) != d['empty']:
        bad.append('S1 判空錨點表 %d 段，A 類宣告 %d 段' % (len(s['empty']), d['empty']))
    if d.get('hit') is not None and len(s['hit']) != d['hit']:
        bad.append('S1 命中錨點表 %d 段，A 類宣告 %d 段' % (len(s['hit']), d['hit']))

    # S2 批次表的段數／章數 vs 批次檔實況；章名歸屬（玄攡 在 b03 不在 b04）
    seen_ch = set()
    for batch, cell, n_para, n_ch in s['batch_table']:
        real_ch = batch_chapters.get(batch, [])
        real_para = sum(chapter_len[c][1] for c in real_ch)
        if real_para != n_para:
            bad.append('S2 %s 段數 SPEC 寫 %d，實際 %d' % (batch, n_para, real_para))
        if len(real_ch) != n_ch:
            bad.append('S2 %s 章數 SPEC 寫 %d，實際 %d' % (batch, n_ch, len(real_ch)))
        if d.get('rows', {}).get(batch) not in (None, n_para):
            bad.append('S2 %s A 類 rows 數 %d ≠ 批次表 %d'
                       % (batch, d['rows'][batch], n_para))
        for ch, n in parse_batch_cell(cell):
            seen_ch.add(ch)
            if n < 0:
                bad.append('S3 %s 章欄無法解析：%s' % (batch, ch))
            elif ch not in chapter_len:
                bad.append('S3 %s 章名不存在於任何批次檔：%s' % (batch, ch))
            elif chapter_len[ch][0] != batch:
                bad.append('S3 %s 宣告的章 %s 實際在 %s' % (batch, ch, chapter_len[ch][0]))
            elif chapter_len[ch][1] != n:
                bad.append('S3 %s %s 段數 SPEC 寫 %d，實際 %d'
                           % (batch, ch, n, chapter_len[ch][1]))
    for ch in chapter_len:
        if ch not in seen_ch:
            bad.append('S3 批次檔有章 %s，SPEC 批次表未列' % ch)

    # S4 整章判空表
    empty_ch_names = {c for c, _, _ in s['empty_ch']}
    for ch, n, batch in s['empty_ch']:
        if ch not in chapter_len:
            bad.append('S4 整章判空章名不存在：%s' % ch)
            continue
        if chapter_len[ch][1] != n:
            bad.append('S4 %s 段數 SPEC 寫 %d，實際 %d' % (ch, n, chapter_len[ch][1]))
        if chapter_len[ch][0] != batch:
            bad.append('S4 %s 批次 SPEC 寫 %s，實際 %s' % (ch, batch, chapter_len[ch][0]))

    # S5 兩張逐段表：章名／段號範圍／批次／逐字引句
    for label, rows in (('判空', s['empty']), ('命中', s['hit'])):
        for ch, idx, batch, quote_cell, _cell in rows:
            if ch not in chapter_len:
                bad.append('S5 %s錨點章名不存在：%s[%d]' % (label, ch, idx))
                continue
            n = chapter_len[ch][1]
            if not 1 <= idx <= n:
                bad.append('S5 %s[%d] 段號超出該章 1–%d' % (ch, idx, n))
                continue
            got = paras.get((ch, idx))
            if got is None:
                bad.append('S5 %s錨點段不存在：%s[%d]' % (label, ch, idx))
                continue
            if got[0] != batch:
                bad.append('S5 %s[%d] 批次 SPEC 寫 %s，實際 %s' % (ch, idx, batch, got[0]))
            for q in re.findall(r'「([^「」]+)」', quote_cell):
                if q not in got[1]:
                    bad.append('S6 引句不在原文：%s[%d]「%s」' % (ch, idx, q))
            if label == '命中' and ch in empty_ch_names:
                bad.append('S7 %s[%d] 在必須命中表，但 %s 整章判空，兩表相反'
                           % (ch, idx, ch))

    # S7 同一段同時落在判空表與命中表
    hit_keys = {(c, i) for c, i, *_ in s['hit']}
    for ch, idx, *_ in s['empty']:
        if (ch, idx) in hit_keys:
            bad.append('S7 %s[%d] 同時在判空表與命中表' % (ch, idx))

    # S8 命中表的「必須含」欄要解得出合法領域
    for ch, idx, _b, _q, cell in s['hit']:
        _mode, need, _f = parse_req(cell)
        if not need:
            bad.append('S8 %s[%d] 必須含欄解不出領域：%s' % (ch, idx, cell))
        for t in need:
            if t not in DOMS:
                bad.append('S8 %s[%d] 非法領域 %s' % (ch, idx, t))

    # S9 XII 禁用清單的章與段要存在
    for ch, n in s['xii_ch']:
        if ch not in chapter_len:
            bad.append('S9 XII 禁用章不存在：%s' % ch)
        elif chapter_len[ch][1] != n:
            bad.append('S9 XII 禁用章 %s 寫 %d 段，實際 %d' % (ch, n, chapter_len[ch][1]))
    for ch, idx in s['xii_para']:
        if (ch, idx) not in paras:
            bad.append('S9 XII 禁用段不存在：%s[%d]' % (ch, idx))
    for ch, idx, _b, _q, cell in s['hit']:
        if ('不得含 XII' in cell) and 'XII' in parse_req(cell)[1]:
            bad.append('S9 %s[%d] 同時必須含 XII 與不得含 XII' % (ch, idx))

    # S10 A6/A7 點名的段必須在兩張逐段表裡有對應錨點（否則驗收條款無從執行）
    anchor_keys = {(c, i) for c, i, *_ in s['empty']} | hit_keys
    if len(s['split_items']) < 2:
        bad.append('S10 A 類只解出 %d 條「一首之內判開」條款' % len(s['split_items']))
    for no, ch, idxs in s['split_items']:
        if ch not in chapter_len:
            bad.append('S10 第 %d 條判開章名不存在：%s' % (no, ch))
            continue
        if not idxs:
            bad.append('S10 第 %d 條（%s）解不出段號' % (no, ch))
        for i in idxs:
            if (ch, i) not in anchor_keys:
                bad.append('S10 %s[%d] 被第 %d 條點名，卻不在任一錨點表' % (ch, i, no))
    # S11 A8/A9 條款可解析
    if s['a8'] is None:
        bad.append('S11 A 類第 8 條解不出（章／段數／mode）')
    elif s['a8'][0] not in chapter_len or chapter_len[s['a8'][0]][1] != s['a8'][1]:
        bad.append('S11 A8 章 %s 段數與批次檔不符' % s['a8'][0])
    if not s['zero_modes']:
        bad.append('S11 A 類第 9 條解不出 0 段 mode 清單')
    for m in s['zero_modes']:
        if m not in MODES:
            bad.append('S11 A9 非法 mode：%s' % m)
    if not s['b_clauses']:
        bad.append('S11 B 類數量帶寬解不出任何條款')

    print('--- SPEC 自檢 FAIL：%d ---' % len(bad))
    for b in bad:
        print(b)
    return 0 if not bad else 1


# ---------------------------------------------------------------- 回收檢查

def load_out(out_dir, want):
    rows, batches, dup = {}, [], []
    for f in sorted(glob.glob(os.path.join(out_dir, 'b0*.json'))):
        b = os.path.basename(f)[:3]
        if want and b not in want:
            continue
        batches.append(b)
        data = json.load(open(f, encoding='utf-8'))
        for r in data.get('rows', []):
            key = (r.get('chapter'), int(r.get('para_index', 0)))
            if key in rows:
                dup.append(key)
            r['_batch'] = b
            rows[key] = r
    return rows, batches, dup


def a1_shape(rows, batches, chapter_len, batch_chapters, dup):
    """A1 rows 數／章名／para_index 連號／reason 非空／值域合法。"""
    f = []
    for k in dup[:5]:
        f.append('A1 重複段 %s[%d]' % k)
    for b in batches:
        got = [r for r in rows.values() if r['_batch'] == b]
        chs = batch_chapters.get(b, [])
        want = sum(chapter_len[c][1] for c in chs)
        if len(got) != want:
            f.append('A1 %s rows %d ≠ 該批段數 %d' % (b, len(got), want))
        valid = set(chs)
        strays = sorted({r.get('chapter') for r in got if r.get('chapter') not in valid})
        for c in strays[:5]:
            f.append('A1 %s 出現非該批章名：%s' % (b, c))
        for ch in chs:
            idxs = sorted(i for (c, i), r in rows.items()
                          if c == ch and r['_batch'] == b)
            n = chapter_len[ch][1]
            if idxs != list(range(1, n + 1)):
                f.append('A1 %s para_index 非 1–%d 連號，實得 %d 段 %s'
                         % (ch, n, len(idxs), idxs[:6]))
        noreason = [r for r in got if not str(r.get('reason', '')).strip()]
        if noreason:
            f.append('A1 %s 有 %d 段 reason 空白，例：%s[%s]'
                     % (b, len(noreason), noreason[0].get('chapter'),
                        noreason[0].get('para_index')))
    for (c, i), r in sorted(rows.items()):
        badd = [x for x in r.get('domains', []) if x not in DOMS]
        badm = [x for x in r.get('modes', []) if x not in MODES]
        if badd:
            f.append('A1 %s[%d] 非法 domain %s' % (c, i, badd))
        if badm:
            f.append('A1 %s[%d] 非法 mode %s' % (c, i, badm))
    return f


def a2_empty_chapters(rows, batches, s):
    f = []
    for ch, n, batch in s['empty_ch']:
        if batch not in batches:
            continue
        got = sorted((i, r) for (c, i), r in rows.items() if c == ch)
        if len(got) != n:
            f.append('A2 %s 應 %d 段，回收 %d 段' % (ch, n, len(got)))
        for i, r in got:
            if r.get('domains'):
                f.append('A2 整章判空章被填 %s[%d] → %s' % (ch, i, r['domains']))
    return f


def a3_empty_anchors(rows, batches, s):
    f = []
    for ch, idx, batch, _q, _c in s['empty']:
        if batch not in batches:
            continue
        r = rows.get((ch, idx))
        if r is None:
            f.append('A3 缺段 %s[%d]' % (ch, idx))
        elif r.get('domains'):
            f.append('A3 必須判空錨點被填 %s[%d] → %s' % (ch, idx, r['domains']))
    return f


def a4_hit_anchors(rows, batches, s):
    f = []
    for ch, idx, batch, _q, cell in s['hit']:
        if batch not in batches:
            continue
        r = rows.get((ch, idx))
        if r is None:
            f.append('A4 缺段 %s[%d]' % (ch, idx))
            continue
        mode, need, _forbid = parse_req(cell)
        d = r.get('domains', [])
        if mode == 'and':
            miss = [x for x in need if x not in d]
            if miss:
                f.append('A4 必須命中錨點缺格 %s[%d] 需 %s 全含，實得 %s' % (ch, idx, need, d))
        elif not any(x in d for x in need):
            f.append('A4 必須命中錨點缺格 %s[%d] 需 %s 至少一，實得 %s' % (ch, idx, need, d))
    return f


def a5_no_xii(rows, s, chapter_len):
    f = []
    for ch, idx in sorted(forbid_xii_keys(s, chapter_len)):
        r = rows.get((ch, idx))
        if r is not None and 'XII' in r.get('domains', []):
            f.append('A5 不得含 XII 的段被標 XII %s[%d] → %s' % (ch, idx, r['domains']))
    return f


def split_check(rows, batches, s, item_no, chapter):
    """A6／A7：同一首之內必須判開，逐段依錨點表各判各的，且不得判齊。"""
    f = []
    entry = [x for x in s['split_items'] if x[1] == chapter]
    if not entry:
        return ['A%d SPEC 解不出 %s 的判開條款' % (item_no, chapter)]
    idxs = entry[0][2]
    emap = {(c, i): (q, cell) for c, i, b, q, cell in s['empty']}
    hmap = {(c, i): (b, cell) for c, i, b, q, cell in s['hit']}
    verdicts, seen = [], False
    for i in idxs:
        if (chapter, i) in hmap:
            batch = hmap[(chapter, i)][0]
        else:
            batch = next((b for c, j, b, _q, _c in s['empty']
                          if c == chapter and j == i), None)
        if batch not in batches:
            continue
        seen = True
        r = rows.get((chapter, i))
        if r is None:
            f.append('A%d 缺段 %s[%d]' % (item_no, chapter, i))
            continue
        d = r.get('domains', [])
        verdicts.append(frozenset(d))
        if (chapter, i) in hmap:
            _b, cell = hmap[(chapter, i)]
            _m, need, forbid = parse_req(cell)
            if not any(x in d for x in need):
                f.append('A%d %s[%d] 應命中 %s，實得 %s'
                         % (item_no, chapter, i, ' 或 '.join(need), d))
            if forbid and 'XII' in d:
                f.append('A%d %s[%d] 不得含 XII 卻含 → %s' % (item_no, chapter, i, d))
        elif (chapter, i) in emap:
            if d:
                f.append('A%d %s[%d] 應判空卻命中 → %s' % (item_no, chapter, i, d))
    if seen and len(verdicts) > 1 and len(set(verdicts)) == 1:
        f.append('A%d %s 一首之內 %s 段判齊（全部 %s），必須判開'
                 % (item_no, chapter, len(verdicts),
                    sorted(verdicts[0]) if verdicts[0] else '[]'))
    return f


def a8_formalization(rows, batches, s, chapter_len):
    f = []
    if s['a8'] is None:
        return ['A8 SPEC 解不出第 8 條']
    ch, n, mode = s['a8']
    batch = chapter_len.get(ch, (None,))[0]
    if batch not in batches:
        return f
    got = sorted((i, r) for (c, i), r in rows.items() if c == ch)
    if len(got) != n:
        f.append('A8 %s 應 %d 段，回收 %d 段' % (ch, n, len(got)))
    for i, r in got:
        if r.get('domains'):
            f.append('A8 %s[%d] 應判空卻命中 → %s' % (ch, i, r['domains']))
        if mode not in r.get('modes', []):
            f.append('A8 %s[%d] modes 未含 %s → %s' % (ch, i, mode, r.get('modes')))
    return f


def a9_zero_modes(rows, s):
    f = []
    for m in s['zero_modes']:
        bad = [(c, i) for (c, i), r in rows.items() if m in r.get('modes', [])]
        if bad:
            f.append('A9 %s 應 0 段，實得 %d：%s' % (m, len(bad), sorted(bad)[:5]))
    return f


# ---------------------------------------------------------------- B 類（WARN）

def compute_stats(rows, chapter_len, s):
    zan_n = s['layers'].get('zan', (810, 81, 10))[2]
    zhuan = set(s['layers'].get('zhuan', ([], 0))[0])
    st = {'dom': {d: 0 for d in DOM_ORDER}, 'mode': {}, 'zan_total': 0,
          'zan_empty': 0, 'zhuan_total': 0, 'zhuan_hit': 0, 'empty': 0}
    for (c, i), r in rows.items():
        d, m = r.get('domains', []), r.get('modes', [])
        if not d:
            st['empty'] += 1
        for x in d:
            if x in st['dom']:
                st['dom'][x] += 1
        for x in m:
            st['mode'][x] = st['mode'].get(x, 0) + 1
        if chapter_len.get(c, (None, 0))[1] == zan_n:
            st['zan_total'] += 1
            if not d:
                st['zan_empty'] += 1
        if c in zhuan:
            st['zhuan_total'] += 1
            if d:
                st['zhuan_hit'] += 1
    st['n_dom_hit'] = sum(1 for d in DOM_ORDER if st['dom'][d])
    st['n_dom_zero'] = 13 - st['n_dom_hit']
    return st


def b_metric(clause, st):
    """把 B 類條款字面對到一個實測值；對不上就回 None（只影響 WARN 呈現）。"""
    if '贊辭層' in clause and '判空' in clause:
        return '贊辭層判空', st['zan_empty']
    if '玄傳' in clause and '命中' in clause:
        return '玄傳命中', st['zhuan_hit']
    if '命中領域' in clause:
        return '命中領域格數', st['n_dom_hit']
    if '零段' in clause:
        return '零段 domains 格數', st['n_dom_zero']
    m = re.match(r'^`([a-z_]+)`', clause)
    if m:
        return m.group(1), st['mode'].get(m.group(1), 0)
    m = re.match(r'^(XI{0,2}|[IVX]+) 全書', clause)
    if m and m.group(1) in DOMS:
        return m.group(1), st['dom'][m.group(1)]
    return None


def b_warnings(s, st):
    warns = []
    for c in s['b_clauses']:
        clause = c
        if '預期為最大' in clause:
            kind = 'mode' if 'mode' in clause else 'dom'
            name = re.match(r'^`?([A-Za-z_]+|[IVX]+)`?', clause.strip())
            if not name:
                continue
            name = name.group(1)
            table = st['mode'] if kind == 'mode' else st['dom']
            if not table:
                continue
            top = max(table.items(), key=lambda kv: kv[1])
            if top[0] != name:
                warns.append('B 「%s」實測最大是 %s=%d（%s=%d）'
                             % (clause, top[0], top[1], name, table.get(name, 0)))
            continue
        got = b_metric(clause, st)
        if got is None:
            continue
        label, val = got
        m = re.search(r'≥\s*(\d+)', c)
        if m and val < int(m.group(1)):
            warns.append('B 「%s」實測 %s=%d，低於下限 %s' % (clause, label, val, m.group(1)))
            continue
        m = re.search(r'≤\s*(\d+)', c)
        if m and val > int(m.group(1)):
            warns.append('B 「%s」實測 %s=%d，高於上限 %s' % (clause, label, val, m.group(1)))
            continue
        m = re.search(r'(\d+)[–\-](\d+)', c)
        if m and not int(m.group(1)) <= val <= int(m.group(2)):
            warns.append('B 「%s」實測 %s=%d，落在帶寬 %s–%s 之外'
                         % (clause, label, val, m.group(1), m.group(2)))
    return warns


# ---------------------------------------------------------------- main

def run(out_dir, want):
    _paras, chapter_len, batch_chapters, header_bad = read_batches()
    s = parse_spec()
    if not (s['empty_ch'] and s['empty'] and s['hit'] and s['split_items']):
        print('!! SPEC 三張錨點表未解析成功，先跑 --check-spec')
        return 2

    rows, batches, dup = load_out(out_dir, want)
    print('回收批次：%s，共 %d 段（來源 %s）'
          % (' '.join(batches) or '(無)', len(rows), os.path.relpath(out_dir, BASE)))
    if not rows:
        return 1

    fails = ['A1 批次檔標頭：' + x for x in header_bad]
    fails += a1_shape(rows, batches, chapter_len, batch_chapters, dup)
    fails += a2_empty_chapters(rows, batches, s)
    fails += a3_empty_anchors(rows, batches, s)
    fails += a4_hit_anchors(rows, batches, s)
    fails += a5_no_xii(rows, s, chapter_len)
    for no, ch, _idxs in s['split_items']:
        fails += split_check(rows, batches, s, no, ch)
    fails += a8_formalization(rows, batches, s, chapter_len)
    fails += a9_zero_modes(rows, s)

    skipped = sum(1 for _c, _i, b, _q, _x in s['empty'] + s['hit'] if b not in batches)
    skipped += sum(n for _c, n, b in s['empty_ch'] if b not in batches)

    st = compute_stats(rows, chapter_len, s)
    print('判空 %d/%d（%.0f%%）；贊辭層判空 %d/%d；玄傳命中 %d/%d'
          % (st['empty'], len(rows), 100 * st['empty'] / len(rows),
             st['zan_empty'], st['zan_total'], st['zhuan_hit'], st['zhuan_total']))
    print('領域： ' + '  '.join('%s=%d' % (d, st['dom'][d]) for d in DOM_ORDER))
    print('姿態： ' + '  '.join('%s=%d' % kv for kv in
                               sorted(st['mode'].items(), key=lambda kv: -kv[1])))

    warns = b_warnings(s, st) if len(batches) == len(batch_chapters) else []
    if len(batches) != len(batch_chapters):
        print('（未全批回收，B 類數量提示略過）')
    print('--- B 類 WARN：%d（不擋收）---' % len(warns))
    for w in warns:
        print(w)

    print('\n跳過（該批未回收）：%d 條錨點' % skipped)
    print('--- A 類 FAIL：%d ---' % len(fails))
    for x in fails:
        print(x)
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser(description='太玄經標註驗收（A 類硬條件＋B 類 WARN）')
    ap.add_argument('batches', nargs='*', help='只檢查這些批次，如 b01 b02；預設全部')
    ap.add_argument('--check-spec', action='store_true',
                    help='發包前自檢：只拿 SPEC.md 對 b01.md–b04.md')
    ap.add_argument('--out-dir', default=os.path.join(BASE, 'out'),
                    help='外包輸出目錄，預設 delegation/taixuanjing/out')
    args = ap.parse_args()
    if args.check_spec:
        return check_spec()
    out_dir = args.out_dir
    if not os.path.isabs(out_dir):
        out_dir = os.path.join(BASE, out_dir)
    return run(out_dir, args.batches)


if __name__ == '__main__':
    sys.exit(main())
