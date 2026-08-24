"""呂氏春秋 A 類驗收（體裁陷阱，硬條件）＋ B 類數量提示（只 WARN，不擋收）。

錨點一律從 SPEC.md 的四張表（必須整章判空／必須判空／必須命中／必須非空）、
「一格都不得填 XII」清單與 A 類條文現場解析，本檔不手抄任何章名、段號、引句或
領域——孔叢子那次 18 個假 FAIL 的成因就是驗收器自己抄了一份沒被驗證過的清單。
SPEC 改一個字，本檔行為就跟著變，不需要改 Python。

用法：
  PYTHONIOENCODING=utf-8 python delegation/lushi-chunqiu/accept.py --check-spec
      發包前跑：只拿 SPEC.md 對 b01.md–b18.md，驗批次表段數／章數、章名歸屬、
      錨點段號範圍、逐字引句是否真的存在，以及條文與表格是否互相漂移。
  PYTHONIOENCODING=utf-8 python delegation/lushi-chunqiu/accept.py [b01 ...]
      回收後跑；不給批次就檢查 out/ 底下所有已存在的批次。
  PYTHONIOENCODING=utf-8 python delegation/lushi-chunqiu/accept.py --out-dir _selftest/perfect
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
CN_NUM = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6,
          '七': 7, '八': 8, '九': 9, '十': 10}
# 逐字引句：段末的 `章`[n] 後面緊接引號才算，中間隔了字的一律不當引句
QUOTED = re.compile(r'`([^`]+)`\[(\d+)\](?:「([^「」]+)」|“([^“”]+)”)')


# ---------------------------------------------------------------- 批次檔

def read_batches():
    """bNN.md → paras/chapter_len/batch_chapters；順便驗章標頭段數與實際行數一致。"""
    paras, chapter_len, batch_chapters, header_bad = {}, {}, {}, []
    for f in sorted(glob.glob(os.path.join(BASE, 'b[0-9][0-9].md'))):
        batch = os.path.basename(f)[:3]
        batch_chapters.setdefault(batch, [])
        chapter, counts = None, {}
        for line in open(f, encoding='utf-8'):
            m = re.match(r'^## (.+?)（(\d+) 段）\s*$', line)
            if m:
                chapter = m.group(1)
                if chapter in chapter_len:
                    header_bad.append('章名 %s 同時出現在 %s 與 %s'
                                      % (chapter, chapter_len[chapter][0], batch))
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


def _quotes(cell):
    return (re.findall(r'「([^「」]+)」', cell) + re.findall(r'“([^“”]+)”', cell))


def quote_ok(q, text):
    """引句對拍：`**` 是 markdown 不是原文，`…` 是我省略的中段，逐段順序比對。"""
    pos = 0
    for frag in re.split(r'…+', q.replace('**', '')):
        frag = frag.strip()
        if not frag:
            continue
        i = text.find(frag, pos)
        if i < 0:
            return False
        pos = i + len(frag)
    return True


def parse_spec():
    """把 SPEC.md 解析成驗收所需的全部錨點與宣告值。本檔唯一的事實來源。"""
    spec = open(os.path.join(BASE, 'SPEC.md'), encoding='utf-8').read()
    secs = _sections(spec)
    s = {'empty_ch': [], 'empty': [], 'hit': [], 'nonempty': [], 'gray': [],
         'xii_tokens': [], 'a9_tokens': [], 'batch_table': [], 'group_table': [],
         'split_items': [], 'equal_pairs': [], 'differ_pairs': [], 'forbid_dom': [],
         'zero_modes': [], 'max_dom': None, 'gate_chapters': {},
         'head': {}, 'declared': {}, 'b_clauses': [], 'prose_quotes': []}

    for head, body in secs.items():
        m = re.match(r'^(必須整章判空的章|必須判空的錨點|必須命中且必含指定領域的錨點'
                     r'|必須非空的錨點)（(\d+) [章段]', head)
        if m:
            s['head'][m.group(1)] = int(m.group(2))

        if head.startswith('必須整章判空的章'):
            for line in body.split('\n'):
                m = re.match(r'^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*(b\d\d)\s*\|\s*(E\d)\s*\|',
                             line)
                if m:
                    s['empty_ch'].append((m.group(1), int(m.group(2)),
                                          m.group(3), m.group(4)))
        elif head.startswith('必須判空的錨點') or head.startswith('必須命中且必含'):
            key = 'empty' if head.startswith('必須判空') else 'hit'
            for line in body.split('\n'):
                m = re.match(r'^\|\s*`([^`]+)`\[(\d+)\]\s*\|\s*(.*?)\s*\|\s*(b\d\d)\s*\|'
                             r'\s*(.*?)\s*\|\s*$', line)
                if m:
                    s[key].append((m.group(1), int(m.group(2)), m.group(4),
                                   m.group(3), m.group(5)))
            if key == 'empty':
                # 表外追加的第 21 條（`音初`[1]），批次留空由批次檔解析
                for line in body.split('\n'):
                    if line.startswith('**另**：') and '判空' in line:
                        for m in QUOTED.finditer(line):
                            s['empty'].append((m.group(1), int(m.group(2)), None,
                                               '「%s」' % (m.group(3) or m.group(4)),
                                               '表外第 21 條'))
        elif head.startswith('必須非空的錨點'):
            for line in body.split('\n'):
                m = re.match(r'^\|\s*(b\d\d)\s*\|\s*(.+?)\s*\|\s*$', line)
                if not m:
                    continue
                for part in m.group(2).split('／'):
                    mm = re.match(r'^\s*`([^`]+)`\[(\d+)\](.*)$', part)
                    if mm:
                        s['nonempty'].append((mm.group(1), int(mm.group(2)),
                                              m.group(1), mm.group(3)))
        elif head.startswith('一格都不得填 XII'):
            s['xii_tokens'] = _split_xii(body)
        elif head.startswith('我不設錨的灰區'):
            m = re.search(r'以下([一二三四五六七八九十]+)段', body)
            if m:
                s['declared']['gray'] = CN_NUM.get(m.group(1))
            for line in body.split('\n'):
                if line.startswith('- '):
                    mm = QUOTED.search(line)
                    if mm:
                        s['gray'].append((mm.group(1), int(mm.group(2)),
                                          mm.group(3) or mm.group(4)))
        elif head.startswith('驗收條件'):
            _parse_accept(s, body)
        elif head.startswith('閘門'):
            for sub in re.split(r'^### ', body, flags=re.M):
                mg = re.match(r'^(E\d)', sub)
                if mg:
                    s['gate_chapters'][mg.group(1)] = re.findall(r'`([^`\[]+)`', sub)

    # 批次表 | b01 | 4 | 19 | 孟春紀 本生 重己 貴公 |
    for line in spec.split('\n'):
        m = re.match(r'^\|\s*(b\d\d)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*$', line)
        if m:
            s['batch_table'].append((m.group(1), int(m.group(2)), int(m.group(3)),
                                     m.group(4).split()))
    # 五群表 | **E1 月令** | … | 12 章 85 段 | … |
    for line in spec.split('\n'):
        m = re.match(r'^\|\s*\*\*(E\d)[^|]*\|[^|]*\|\s*(\d+) 章 (\d+) 段\s*\|', line)
        if m:
            s['group_table'].append((m.group(1), int(m.group(2)), int(m.group(3))))
    m = re.search(r'全書 (\d+) 章 (\d+) 段', spec)
    if m:
        s['declared']['book'] = (int(m.group(1)), int(m.group(2)))

    # 全文的 `章`[n]「逐字引句」——配套散文裡的引句一樣要對拍
    for m in QUOTED.finditer(spec):
        s['prose_quotes'].append((m.group(1), int(m.group(2)),
                                  m.group(3) or m.group(4)))
    return s


def _split_xii(text):
    """「E1 全 12 章 85 段、`音律` 全 3 段、`有始`[2]–[13]、`召類`[1]」→ token 串。"""
    toks = []
    body = text.split('\n\n')[1] if '\n\n' in text else text
    body = re.sub(r'^#.*$', '', body, flags=re.M)
    for part in re.split(r'[、。]', body):
        part = part.strip()
        if not part:
            continue
        m = re.match(r'^(E\d) 全 (?:(\d+) 章 )?(\d+) 段$', part)
        if m:
            toks.append(('group', m.group(1),
                         int(m.group(2)) if m.group(2) else None, int(m.group(3))))
            continue
        m = re.match(r'^`([^`]+)` 全 (\d+) 段$', part)
        if m:
            toks.append(('chapter', m.group(1), int(m.group(2))))
            continue
        m = re.match(r'^`([^`]+)`\[(\d+)\][–\-]\[(\d+)\]$', part)
        if m:
            toks.append(('range', m.group(1), int(m.group(2)), int(m.group(3))))
            continue
        m = re.match(r'^`([^`]+)`\[(\d+)\]$', part)
        if m:
            toks.append(('para', m.group(1), int(m.group(2))))
            continue
        if '`' in part or re.search(r'\bE\d\b', part):
            toks.append(('!', part[:24]))
    return toks


def _parse_accept(s, body):
    d = s['declared']
    m = re.search(r'「必須整章判空」的 (\d+) 章共 (\d+) 段', body)
    if m:
        d['empty_ch'] = (int(m.group(1)), int(m.group(2)))
    m = re.search(r'「必須判空」的 (\d+) 段', body)
    if m:
        d['empty'] = int(m.group(1))
    m = re.search(r'判空段合計 (\d+)', body)
    if m:
        d['empty_total'] = int(m.group(1))
    m = re.search(r'「必須命中且必含指定領域」的 (\d+) 段', body)
    if m:
        d['hit'] = int(m.group(1))
    m = re.search(r'「必須非空」的 (\d+) 段', body)
    if m:
        d['nonempty'] = int(m.group(1))
    m = re.search(r'合計 (\d+)）', body)
    if m:
        d['total'] = int(m.group(1))
    for m in re.finditer(r'(b\d\d) (\d+)', body):
        d.setdefault('rows', {})[m.group(1)] = int(m.group(2))
    m = re.search(r'這 (\d+) 段的 `modes` 全部含 `(\w+)` 或 `(\w+)`', body)
    if m:
        d['empty_ch_modes'] = (int(m.group(1)), m.group(2), m.group(3))

    s['a9_tokens'] = _split_xii(
        re.search(r'標了「不得含 XII」的段一律不含 XII\*\*，含(.*)', body).group(1)
        if re.search(r'標了「不得含 XII」的段一律不含 XII\*\*，含(.*)', body) else '')
    for m in re.finditer(r'`([^`]+)`\[(\d+)\] 判空而((?:\s*\[\d+\])+) 非空', body):
        s['split_items'].append((m.group(1), int(m.group(2)),
                                 [int(x) for x in re.findall(r'\d+', m.group(3))]))
    m = re.search(r'`([^`]+)`\[(\d+)\] 與 `([^`]+)`\[(\d+)\] 的 `domains` 與 `modes` '
                  r'必須完全一致', body)
    if m:
        s['equal_pairs'].append((m.group(1), int(m.group(2)), m.group(3), int(m.group(4))))
    m = re.search(r'`([^`]+)`\[(\d+)\] 與 `([^`]+)`\[(\d+)\] 的 `domains` 不得完全一致', body)
    if m:
        s['differ_pairs'].append((m.group(1), int(m.group(2)), m.group(3), int(m.group(4))))
    for m in re.finditer(r'`([^`]+)`\[(\d+)\] 不得含 ([IVX]+)\*\*', body):
        s['forbid_dom'].append((m.group(1), int(m.group(2)), m.group(3)))
    s['zero_modes'] = re.findall(r'`(\w+)` 全書 0 段', body)
    m = re.search(r'`domains` 長度 ≤ (\d+)', body)
    if m:
        s['max_dom'] = int(m.group(1))
    # A6／A7：條文點名的段，回頭要求命中表真的那樣寫
    m = re.search(r'`([^`]+)`\[(\d+)\] 與 `([^`]+)`\[(\d+)\] 必須同時含 ([IVX]+) 與 ([IVX]+)',
                  body)
    if m:
        s['a6'] = (m.group(1), int(m.group(2)), m.group(3), int(m.group(4)),
                   m.group(5), m.group(6))
    m = re.search(r'`([^`]+)`\[(\d+)\] 含 ([IVX]+) 與 ([IVX]+) 且不含 ([IVX]+)', body)
    if m:
        s['a7'] = (m.group(1), int(m.group(2)), m.group(3), m.group(4), m.group(5))
    bsec = body.split('### B 類', 1)
    if len(bsec) == 2:
        for line in bsec[1].split('\n'):
            if line.startswith('- '):
                s['b_clauses'] += [c.strip() for c in line[2:].split('；') if c.strip()]


def parse_req(cell):
    """「V 或 VII（說辭側，**不得含 XII**）」→ ('or', ['V','VII'], ['XII'])"""
    forbid = re.findall(r'不得含 ([IVX]+)', cell)
    body = re.sub(r'（[^）]*）', '', cell).replace('*', '')
    body = re.sub(r'，?且?不得含 [IVX]+', '', body).strip()
    toks = [t for t in re.split(r'[^IVX]+', body) if t in DOMS]
    mode = 'and' if ('＋' in body or '+' in body) else 'or'
    return mode, toks, forbid


def expand_xii(toks, s, chapter_len):
    """XII 禁用 token 串展開成 (章, 段) 集合；順便回報解不開的 token。"""
    keys, bad = set(), []
    e1 = {c: n for c, n, _b, g in s['empty_ch'] if g == 'E1'}
    for t in toks:
        if t[0] == 'group':
            _k, g, n_ch, n_para = t
            members = {c: n for c, n, _b, gg in s['empty_ch'] if gg == g} if g != 'E1' else e1
            if (n_ch is not None and len(members) != n_ch) or sum(members.values()) != n_para:
                bad.append('%s 宣告 %d 章 %d 段，整章判空表實得 %d 章 %d 段'
                           % (g, n_ch or len(members), n_para,
                              len(members), sum(members.values())))
            for c, n in members.items():
                keys |= {(c, i) for i in range(1, n + 1)}
        elif t[0] == 'chapter':
            _k, c, n = t
            real = chapter_len.get(c)
            if real is None:
                bad.append('章不存在：%s' % c)
            else:
                if real[1] != n:
                    bad.append('%s 宣告 %d 段，實際 %d 段' % (c, n, real[1]))
                keys |= {(c, i) for i in range(1, real[1] + 1)}
        elif t[0] == 'range':
            _k, c, a, b = t
            keys |= {(c, i) for i in range(a, b + 1)}
        elif t[0] == 'para':
            keys.add((t[1], t[2]))
        else:
            bad.append('無法解析的 token：%s' % t[1])
    return keys, bad


def all_forbid_xii(s, chapter_len):
    keys, _bad = expand_xii(s['xii_tokens'], s, chapter_len)
    for ch, idx, _b, _q, cell in s['hit'] + s['empty']:
        if 'XII' in parse_req(cell)[2]:
            keys.add((ch, idx))
    return keys


# ---------------------------------------------------------------- SPEC 自檢

def check_spec():
    paras, chapter_len, batch_chapters, header_bad = read_batches()
    s = parse_spec()
    bad = []

    print('批次檔：%d 批 %d 章 %d 段'
          % (len(batch_chapters), len(chapter_len), len(paras)))
    print('SPEC 解析：整章判空 %d 章／判空錨點 %d 段／命中錨點 %d 段／非空錨點 %d 段／'
          '灰區 %d 段' % (len(s['empty_ch']), len(s['empty']), len(s['hit']),
                          len(s['nonempty']), len(s['gray'])))
    bad += ['S0 批次檔標頭：' + x for x in header_bad]

    # S1 章節標題宣告的數量 vs 表格實際列數 vs A 類條文宣告的數量
    d = s['declared']
    for key, n_row in (('必須整章判空的章', len(s['empty_ch'])),
                       ('必須判空的錨點', len(s['empty']) - 1),
                       ('必須命中且必含指定領域的錨點', len(s['hit'])),
                       ('必須非空的錨點', len(s['nonempty']))):
        if key not in s['head']:
            bad.append('S1 章節標題解不出數量：%s' % key)
        elif s['head'][key] != n_row:
            bad.append('S1 %s 標題寫 %d，表格實得 %d' % (key, s['head'][key], n_row))
    if 'empty_ch' in d:
        n_ch, n_para = d['empty_ch']
        if len(s['empty_ch']) != n_ch:
            bad.append('S1 整章判空表 %d 章，A 類宣告 %d 章' % (len(s['empty_ch']), n_ch))
        tot = sum(n for _c, n, _b, _g in s['empty_ch'])
        if tot != n_para:
            bad.append('S1 整章判空表合計 %d 段，A 類宣告 %d 段' % (tot, n_para))
    if d.get('empty') is not None and len(s['empty']) != d['empty']:
        bad.append('S1 判空錨點 %d 段（含表外第 21 條），A 類宣告 %d 段'
                   % (len(s['empty']), d['empty']))
    if d.get('hit') is not None and len(s['hit']) != d['hit']:
        bad.append('S1 命中錨點表 %d 段，A 類宣告 %d 段' % (len(s['hit']), d['hit']))
    if d.get('nonempty') is not None and len(s['nonempty']) != d['nonempty']:
        bad.append('S1 非空錨點表 %d 段，A 類宣告 %d 段' % (len(s['nonempty']), d['nonempty']))
    if d.get('gray') is not None and len(s['gray']) != d['gray']:
        bad.append('S1 灰區條列 %d 段，正文宣告 %d 段' % (len(s['gray']), d['gray']))
    if d.get('empty_total') is not None:
        tot = sum(n for _c, n, _b, _g in s['empty_ch']) + len(s['empty'])
        if tot != d['empty_total']:
            bad.append('S1 判空段合計實得 %d，A 類宣告 %d' % (tot, d['empty_total']))
    if d.get('empty_ch_modes'):
        n, m1, m2 = d['empty_ch_modes']
        if n != sum(x for _c, x, _b, _g in s['empty_ch']):
            bad.append('S1 A3 條的段數 %d 與整章判空表合計不符' % n)
        for mm in (m1, m2):
            if mm not in MODES:
                bad.append('S1 A3 條非法 mode：%s' % mm)

    # S2 批次表章數／段數／章名歸屬
    seen_ch = set()
    for batch, n_ch, n_para, names in s['batch_table']:
        real_ch = batch_chapters.get(batch)
        if real_ch is None:
            bad.append('S2 SPEC 有批次 %s，批次檔不存在' % batch)
            continue
        real_para = sum(chapter_len[c][1] for c in real_ch)
        if real_para != n_para:
            bad.append('S2 %s 段數 SPEC 寫 %d，實際 %d' % (batch, n_para, real_para))
        if len(real_ch) != n_ch:
            bad.append('S2 %s 章數 SPEC 寫 %d，實際 %d' % (batch, n_ch, len(real_ch)))
        if len(names) != n_ch:
            bad.append('S2 %s 章名欄 %d 個，章數欄寫 %d' % (batch, len(names), n_ch))
        if names != real_ch:
            bad.append('S2 %s 章名或順序不符\n    SPEC：%s\n    實際：%s'
                       % (batch, ' '.join(names), ' '.join(real_ch)))
        if d.get('rows', {}).get(batch) not in (None, n_para):
            bad.append('S2 %s A1 條寫 %d 段，批次表寫 %d'
                       % (batch, d['rows'][batch], n_para))
        seen_ch |= set(names)
    for ch in chapter_len:
        if ch not in seen_ch:
            bad.append('S2 批次檔有章 %s，SPEC 批次表未列' % ch)
    if d.get('total') is not None and d['total'] != len(paras):
        bad.append('S2 A1 條合計 %d 段，批次檔實得 %d 段' % (d['total'], len(paras)))
    if d.get('book') and d['book'] != (len(chapter_len), len(paras)):
        bad.append('S2 正文宣告全書 %d 章 %d 段，批次檔實得 %d 章 %d 段'
                   % (d['book'][0], d['book'][1], len(chapter_len), len(paras)))
    gt = {g: (a, b) for g, a, b in s['group_table']}
    if gt:
        add = [g for g in gt if g != 'E4']
        tot_ch = sum(gt[g][0] for g in add)
        tot_pa = sum(gt[g][1] for g in add)
        if tot_pa != len(paras):
            bad.append('S2 五群表（E4 不計）合計 %d 段，批次檔 %d 段' % (tot_pa, len(paras)))
        if tot_ch != len(chapter_len):
            bad.append('S2 五群表（E4 不計）合計 %d 章，批次檔 %d 章' % (tot_ch, len(chapter_len)))
        real = {}
        for c, (_b, n) in chapter_len.items():
            g = group_of(c, s)
            real.setdefault(g, [0, 0])
            real[g][0] += 1
            real[g][1] += n
        for g in add:
            got = real.get(g, [0, 0])
            if [gt[g][0], gt[g][1]] != got:
                bad.append('S2 五群表 %s 寫 %d 章 %d 段，依章名歸群實得 %d 章 %d 段'
                           % (g, gt[g][0], gt[g][1], got[0], got[1]))

    # S3 整章判空表
    empty_ch_names = {c for c, _n, _b, _g in s['empty_ch']}
    for ch, n, batch, _g in s['empty_ch']:
        if ch not in chapter_len:
            bad.append('S3 整章判空章名不存在：%s' % ch)
            continue
        if chapter_len[ch][1] != n:
            bad.append('S3 %s 段數 SPEC 寫 %d，實際 %d' % (ch, n, chapter_len[ch][1]))
        if chapter_len[ch][0] != batch:
            bad.append('S3 %s 批次 SPEC 寫 %s，實際 %s' % (ch, batch, chapter_len[ch][0]))

    # S4 三張逐段表：章名／段號範圍／批次／逐字引句
    for label, rows in (('判空', [(c, i, b, q) for c, i, b, q, _x in s['empty']]),
                        ('命中', [(c, i, b, q) for c, i, b, q, _x in s['hit']]),
                        ('非空', s['nonempty'])):
        for ch, idx, batch, quote_cell in rows:
            if ch not in chapter_len:
                bad.append('S4 %s錨點章名不存在：%s[%d]' % (label, ch, idx))
                continue
            n = chapter_len[ch][1]
            if not 1 <= idx <= n:
                bad.append('S4 %s[%d] 段號超出該章 1–%d' % (ch, idx, n))
                continue
            got = paras[(ch, idx)]
            if batch is not None and got[0] != batch:
                bad.append('S4 %s[%d] 批次 SPEC 寫 %s，實際 %s' % (ch, idx, batch, got[0]))
            for q in _quotes(quote_cell):
                if not quote_ok(q, got[1]):
                    bad.append('S5 引句不在原文：%s[%d]「%s」' % (ch, idx, q))
            if label != '判空' and ch in empty_ch_names:
                bad.append('S6 %s[%d] 在%s表，但 %s 整章判空，兩表相反' % (ch, idx, label, ch))

    # S6 同一段不可同時落在互斥的表
    key_empty = {(c, i) for c, i, *_ in s['empty']}
    key_hit = {(c, i) for c, i, *_ in s['hit']}
    key_non = {(c, i) for c, i, *_ in s['nonempty']}
    key_gray = {(c, i) for c, i, _q in s['gray']}
    for a, b, na, nb in ((key_empty, key_hit, '判空', '命中'),
                         (key_empty, key_non, '判空', '非空'),
                         (key_hit, key_non, '命中', '非空'),
                         (key_gray, key_empty | key_hit | key_non, '灰區', '錨點')):
        for c, i in sorted(a & b):
            bad.append('S6 %s[%d] 同時在%s表與%s表' % (c, i, na, nb))
    for ch, idx, _q in s['gray']:
        if (ch, idx) not in paras:
            bad.append('S6 灰區段不存在：%s[%d]' % (ch, idx))
        elif ch in empty_ch_names:
            bad.append('S6 灰區段 %s[%d] 所在章卻整章判空' % (ch, idx))

    # S7 全文散文裡的 `章`[n]「引句」也要對拍（配套散文是判準的來源）
    for ch, idx, q in s['prose_quotes']:
        if (ch, idx) not in paras:
            bad.append('S7 散文引到不存在的段：%s[%d]' % (ch, idx))
        elif not quote_ok(q, paras[(ch, idx)][1]):
            bad.append('S7 散文引句不在原文：%s[%d]「%s」' % (ch, idx, q))

    # S8 命中表的「必須含」欄
    for ch, idx, _b, _q, cell in s['hit']:
        mode, need, forbid = parse_req(cell)
        if not need:
            bad.append('S8 %s[%d] 必須含欄解不出領域：%s' % (ch, idx, cell))
        for t in need + forbid:
            if t not in DOMS:
                bad.append('S8 %s[%d] 非法領域 %s' % (ch, idx, t))
        if mode == 'and' and set(need) & set(forbid):
            bad.append('S8 %s[%d] 同一格既必須含又不得含' % (ch, idx))

    # S9 XII 禁用清單：token 可解析、A9 條文與清單一致
    keys, xbad = expand_xii(s['xii_tokens'], s, chapter_len)
    bad += ['S9 XII 清單：' + x for x in xbad]
    for ch, idx in sorted(keys):
        if (ch, idx) not in paras:
            bad.append('S9 XII 禁用段不存在：%s[%d]' % (ch, idx))
    a9keys, a9bad = expand_xii(s['a9_tokens'], s, chapter_len)
    bad += ['S9 A9 條文：' + x for x in a9bad]
    if not s['a9_tokens']:
        bad.append('S9 A 類第 9 條解不出禁用清單')
    elif a9keys != keys:
        diff = (a9keys ^ keys)
        bad.append('S9 A 類第 9 條與「不得填 XII」節不一致，差 %d 段：%s'
                   % (len(diff), sorted(diff)[:6]))
    for ch, idx, _b, _q, cell in s['hit']:
        mode, need, forbid = parse_req(cell)
        if 'XII' in forbid and 'XII' in need:
            bad.append('S9 %s[%d] 同時必須含 XII 與不得含 XII' % (ch, idx))
        if (ch, idx) in keys and 'XII' in need:
            bad.append('S9 %s[%d] 在 XII 禁用清單卻要求命中 XII' % (ch, idx))

    # S10 A 類條文點名的段，必須在對應的表裡真的那樣寫
    if len(s['split_items']) != 3:
        bad.append('S10 A13 只解出 %d 條判開條款（應 3 條）' % len(s['split_items']))
    for ch, e_idx, n_idxs in s['split_items']:
        if (ch, e_idx) not in key_empty:
            bad.append('S10 A13 說 %s[%d] 判空，但它不在判空錨點表' % (ch, e_idx))
        for i in n_idxs:
            if (ch, i) not in key_non | key_hit:
                bad.append('S10 A13 說 %s[%d] 非空，但它不在非空／命中表' % (ch, i))
    if not s['equal_pairs']:
        bad.append('S10 A11 解不出必須判齊的段對')
    if not s['differ_pairs']:
        bad.append('S10 A12 解不出必須判異的段對')
    for c1, i1, c2, i2 in s['equal_pairs'] + s['differ_pairs']:
        for c, i in ((c1, i1), (c2, i2)):
            if (c, i) not in paras:
                bad.append('S10 段對點名不存在的段：%s[%d]' % (c, i))
    for c1, i1, c2, i2 in s['equal_pairs']:
        t1, t2 = paras.get((c1, i1), (0, ''))[1], paras.get((c2, i2), (0, ''))[1]
        if t1 and t2 and t1 not in t2 and t2 not in t1:
            bad.append('S10 A11 宣告 %s[%d] 與 %s[%d] 逐字相同，實際互不包含'
                       % (c1, i1, c2, i2))
    for c1, i1, c2, i2 in s['differ_pairs']:
        t1, t2 = paras.get((c1, i1), (0, ''))[1], paras.get((c2, i2), (0, ''))[1]
        if t1 and t1 == t2:
            bad.append('S10 A12 宣告 %s[%d] 與 %s[%d] 必須判異，兩段原文卻完全相同'
                       % (c1, i1, c2, i2))
    if not s['forbid_dom']:
        bad.append('S10 A10 解不出「某段不得含某領域」')
    for ch, idx, dom in s['forbid_dom']:
        if (ch, idx) not in paras:
            bad.append('S10 A10 點名不存在的段：%s[%d]' % (ch, idx))
        if dom not in DOMS:
            bad.append('S10 A10 非法領域 %s' % dom)
    a6 = s.get('a6')
    if not a6:
        bad.append('S10 A6 解不出「必須同時含」的兩段')
    else:
        c1, i1, c2, i2, d1, d2 = a6
        hmap = {(c, i): cell for c, i, _b, _q, cell in s['hit']}
        for c, i in ((c1, i1), (c2, i2)):
            cell = hmap.get((c, i))
            if cell is None:
                bad.append('S10 A6 點名 %s[%d]，但它不在命中表' % (c, i))
                continue
            mode, need, _f = parse_req(cell)
            if mode != 'and' or d1 not in need or d2 not in need:
                bad.append('S10 A6 要求 %s[%d] 同時含 %s＋%s，命中表寫的是「%s」'
                           % (c, i, d1, d2, cell))
    a7 = s.get('a7')
    if not a7:
        bad.append('S10 A7 解不出「含 X 與 Y 且不含 Z」')
    else:
        c, i, d1, d2, d3 = a7
        cell = {(x, y): cc for x, y, _b, _q, cc in s['hit']}.get((c, i))
        if cell is None:
            bad.append('S10 A7 點名 %s[%d]，但它不在命中表' % (c, i))
        else:
            mode, need, forbid = parse_req(cell)
            if mode != 'and' or d1 not in need or d2 not in need or d3 not in forbid:
                bad.append('S10 A7 要求 %s[%d] 含 %s＋%s 不含 %s，命中表寫的是「%s」'
                           % (c, i, d1, d2, d3, cell))
    if not s['zero_modes']:
        bad.append('S10 A14 解不出 0 段 mode')
    for m in s['zero_modes']:
        if m not in MODES:
            bad.append('S10 A14 非法 mode：%s' % m)
    if s['max_dom'] is None:
        bad.append('S10 A15 解不出 domains 長度上限')
    if not s['b_clauses']:
        bad.append('S10 B 類數量帶寬解不出任何條款')

    # S11 閘門節點名的章要存在（判準分派錯章＝那一群整批垮）
    for g, names in s['gate_chapters'].items():
        for c in names:
            if c in chapter_len or c in MODES or c in DOMS:
                continue
            if re.match(r'^[a-z_]+$', c) or c.startswith('[') or '」' in c:
                continue
            bad.append('S11 閘門 %s 節點名的章不存在：%s' % (g, c))

    print('XII 禁用展開：%d 段' % len(keys))
    print('--- SPEC 自檢 FAIL：%d ---' % len(bad))
    for b in bad:
        print(b)
    return 0 if not bad else 1


# ---------------------------------------------------------------- 回收檢查

def load_out(out_dir, want):
    rows, batches, dup = {}, [], []
    for f in sorted(glob.glob(os.path.join(out_dir, 'b[0-9][0-9].json'))):
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


def a1_shape(rows, batches, chapter_len, batch_chapters, dup, s):
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
        d, m = r.get('domains', []), r.get('modes', [])
        for x in d:
            if x not in DOMS:
                f.append('A15 %s[%d] 非法 domain %s' % (c, i, x))
        for x in m:
            if x not in MODES:
                f.append('A15 %s[%d] 非法 mode %s' % (c, i, x))
        if len(d) != len(set(d)):
            f.append('A15 %s[%d] domains 重複 %s' % (c, i, d))
        if s['max_dom'] is not None and len(d) > s['max_dom']:
            f.append('A15 %s[%d] domains %d 格超過上限 %d → %s'
                     % (c, i, len(d), s['max_dom'], d))
    return f


def a2_empty_chapters(rows, batches, s):
    """A2 整章判空＋A3 該章 modes 必含 formalization 或 ritual。"""
    f = []
    want_modes = s['declared'].get('empty_ch_modes')
    for ch, n, batch, _g in s['empty_ch']:
        if batch not in batches:
            continue
        got = sorted((i, r) for (c, i), r in rows.items() if c == ch)
        if len(got) != n:
            f.append('A2 %s 應 %d 段，回收 %d 段' % (ch, n, len(got)))
        for i, r in got:
            if r.get('domains'):
                f.append('A2 整章判空章被填 %s[%d] → %s' % (ch, i, r['domains']))
            if want_modes and not set(want_modes[1:]) & set(r.get('modes', [])):
                f.append('A3 %s[%d] modes 未含 %s 或 %s → %s'
                         % (ch, i, want_modes[1], want_modes[2], r.get('modes')))
    return f


def a4_empty_anchors(rows, batches, s, chapter_len):
    f = []
    for ch, idx, batch, _q, _c in s['empty']:
        batch = batch or chapter_len.get(ch, (None,))[0]
        if batch not in batches:
            continue
        r = rows.get((ch, idx))
        if r is None:
            f.append('A4 缺段 %s[%d]' % (ch, idx))
        elif r.get('domains'):
            f.append('A4 必須判空錨點被填 %s[%d] → %s' % (ch, idx, r['domains']))
    return f


def a5_hit_anchors(rows, batches, s):
    f = []
    for ch, idx, batch, _q, cell in s['hit']:
        if batch not in batches:
            continue
        r = rows.get((ch, idx))
        if r is None:
            f.append('A5 缺段 %s[%d]' % (ch, idx))
            continue
        mode, need, _forbid = parse_req(cell)
        d = r.get('domains', [])
        if mode == 'and':
            miss = [x for x in need if x not in d]
            if miss:
                f.append('A5 必須命中錨點缺格 %s[%d] 需 %s 全含，實得 %s'
                         % (ch, idx, '＋'.join(need), d))
        elif not any(x in d for x in need):
            f.append('A5 必須命中錨點缺格 %s[%d] 需 %s 至少一，實得 %s'
                     % (ch, idx, ' 或 '.join(need), d))
    return f


def a8_nonempty(rows, batches, s):
    f = []
    for ch, idx, batch, _q in s['nonempty']:
        if batch not in batches:
            continue
        r = rows.get((ch, idx))
        if r is None:
            f.append('A8 缺段 %s[%d]' % (ch, idx))
        elif not r.get('domains'):
            f.append('A8 必須非空錨點判空 %s[%d]' % (ch, idx))
    return f


def a9_no_xii(rows, s, chapter_len):
    f = []
    for ch, idx in sorted(all_forbid_xii(s, chapter_len)):
        r = rows.get((ch, idx))
        if r is not None and 'XII' in r.get('domains', []):
            f.append('A9 不得含 XII 的段被標 XII %s[%d] → %s' % (ch, idx, r['domains']))
    return f


def a10_forbid_dom(rows, s):
    f = []
    for ch, idx, dom in s['forbid_dom']:
        r = rows.get((ch, idx))
        if r is not None and dom in r.get('domains', []):
            f.append('A10 %s[%d] 不得含 %s 卻含 → %s' % (ch, idx, dom, r['domains']))
    return f


def a11_a12_pairs(rows, s):
    f = []
    for c1, i1, c2, i2 in s['equal_pairs']:
        r1, r2 = rows.get((c1, i1)), rows.get((c2, i2))
        if r1 is None or r2 is None:
            continue
        if sorted(r1.get('domains', [])) != sorted(r2.get('domains', [])):
            f.append('A11 %s[%d] 與 %s[%d] domains 不一致：%s vs %s'
                     % (c1, i1, c2, i2, r1.get('domains'), r2.get('domains')))
        if sorted(r1.get('modes', [])) != sorted(r2.get('modes', [])):
            f.append('A11 %s[%d] 與 %s[%d] modes 不一致：%s vs %s'
                     % (c1, i1, c2, i2, r1.get('modes'), r2.get('modes')))
    for c1, i1, c2, i2 in s['differ_pairs']:
        r1, r2 = rows.get((c1, i1)), rows.get((c2, i2))
        if r1 is None or r2 is None:
            continue
        if sorted(r1.get('domains', [])) == sorted(r2.get('domains', [])):
            f.append('A12 %s[%d] 與 %s[%d] domains 判齊（都是 %s），必須判異'
                     % (c1, i1, c2, i2, r1.get('domains')))
    return f


def a13_splits(rows, s):
    f = []
    for ch, e_idx, n_idxs in s['split_items']:
        re_ = rows.get((ch, e_idx))
        if re_ is not None and re_.get('domains'):
            f.append('A13 %s[%d] 應判空卻命中 → %s' % (ch, e_idx, re_['domains']))
        for i in n_idxs:
            r = rows.get((ch, i))
            if r is not None and not r.get('domains'):
                f.append('A13 %s[%d] 應非空卻判空' % (ch, i))
    return f


def a14_zero_modes(rows, s):
    f = []
    for m in s['zero_modes']:
        bad = [(c, i) for (c, i), r in rows.items() if m in r.get('modes', [])]
        if bad:
            f.append('A14 %s 應 0 段，實得 %d：%s' % (m, len(bad), sorted(bad)[:5]))
    return f


# ---------------------------------------------------------------- B 類（WARN）

def group_of(chapter, s):
    e1 = {c for c, _n, _b, g in s['empty_ch'] if g == 'E1'}
    if chapter in e1:
        return 'E1'
    for g in ('E2', 'E5'):
        if chapter in set(s['gate_chapters'].get(g, [])):
            return g
    return 'E3'


def compute_stats(rows, s):
    st = {'dom': {d: 0 for d in DOM_ORDER}, 'mode': {}, 'empty': 0,
          'grp': {g: [0, 0] for g in ('E1', 'E2', 'E3', 'E5')}}
    for (c, _i), r in rows.items():
        d, m = r.get('domains', []), r.get('modes', [])
        if not d:
            st['empty'] += 1
        for x in d:
            if x in st['dom']:
                st['dom'][x] += 1
        for x in m:
            st['mode'][x] = st['mode'].get(x, 0) + 1
        g = group_of(c, s)
        st['grp'][g][0] += 1
        if d:
            st['grp'][g][1] += 1
    st['n_dom_hit'] = sum(1 for d in DOM_ORDER if st['dom'][d])
    st['n_dom_zero'] = 13 - st['n_dom_hit']
    return st


def b_warnings(s, st):
    warns = []
    for c in s['b_clauses']:
        if '預期為 E3 群最大 mode' in c or '預期為最大兩格' in c:
            names = re.findall(r'`(\w+)`', c) or re.findall(r'\b([IVX]+)\b', c)
            table = st['mode'] if '`' in c else st['dom']
            if not table or not names:
                continue
            top = [k for k, _v in sorted(table.items(), key=lambda kv: -kv[1])][:len(names)]
            if set(names) - set(top):
                warns.append('B 「%s」實測前 %d 名是 %s' % (c, len(names), top))
            continue
        val = label = None
        m = re.match(r'^`(\w+)`', c)
        if m:
            label, val = m.group(1), st['mode'].get(m.group(1), 0)
        elif c.startswith('E3 群'):
            g = st['grp']['E3']
            label, val = 'E3 命中率', (100 * g[1] // g[0] if g[0] else 0)
        elif 'XII 全書' in c:
            label, val = 'XII', st['dom']['XII']
        elif 'XI 全書' in c:
            label, val = 'XI', st['dom']['XI']
        elif '命中領域' in c:
            label, val = '命中領域格數', st['n_dom_hit']
        elif '零段' in c:
            label, val = '零段 domains 格數', st['n_dom_zero']
        elif c.startswith('E1＋E2'):
            g1, g2 = st['grp']['E1'], st['grp']['E2']
            tot = g1[0] + g2[0]
            label, val = 'E1＋E2 判空率', (100 * (tot - g1[1] - g2[1]) // tot if tot else 0)
        if val is None:
            continue
        m = re.search(r'≥ ?(\d+)', c)
        if m and val < int(m.group(1)):
            warns.append('B 「%s」實測 %s=%d，低於下限 %s' % (c, label, val, m.group(1)))
            continue
        m = re.search(r'≤ ?(\d+)', c)
        if m and val > int(m.group(1)):
            warns.append('B 「%s」實測 %s=%d，高於上限 %s' % (c, label, val, m.group(1)))
            continue
        m = re.search(r'(\d+)[–\-](\d+)', c)
        if m and not int(m.group(1)) <= val <= int(m.group(2)):
            warns.append('B 「%s」實測 %s=%d，落在帶寬 %s–%s 之外'
                         % (c, label, val, m.group(1), m.group(2)))
        elif '預期 100%' in c and val != 100:
            warns.append('B 「%s」實測 %s=%d%%' % (c, label, val))
    return warns


# ---------------------------------------------------------------- main

def collect_fails(out_dir, want):
    """A 類的唯一計算路徑；run() 與 _selftest 共用，不讓兩邊各存一份條款清單。"""
    _paras, chapter_len, batch_chapters, header_bad = read_batches()
    s = parse_spec()
    rows, batches, dup = load_out(out_dir, want)
    fails = ['A1 批次檔標頭：' + x for x in header_bad]
    if rows:
        fails += a1_shape(rows, batches, chapter_len, batch_chapters, dup, s)
        fails += a2_empty_chapters(rows, batches, s)
        fails += a4_empty_anchors(rows, batches, s, chapter_len)
        fails += a5_hit_anchors(rows, batches, s)
        fails += a8_nonempty(rows, batches, s)
        fails += a9_no_xii(rows, s, chapter_len)
        fails += a10_forbid_dom(rows, s)
        fails += a11_a12_pairs(rows, s)
        fails += a13_splits(rows, s)
        fails += a14_zero_modes(rows, s)
    return {'rows': rows, 'batches': batches, 's': s, 'fails': fails,
            'chapter_len': chapter_len, 'batch_chapters': batch_chapters}


def run(out_dir, want):
    got = collect_fails(out_dir, want)
    s, rows, batches = got['s'], got['rows'], got['batches']
    chapter_len, batch_chapters = got['chapter_len'], got['batch_chapters']
    if not (s['empty_ch'] and s['empty'] and s['hit'] and s['nonempty']):
        print('!! SPEC 四張錨點表未解析成功，先跑 --check-spec')
        return 2

    print('回收批次：%s，共 %d 段（來源 %s）'
          % (' '.join(batches) or '(無)', len(rows), os.path.relpath(out_dir, BASE)))
    if not rows:
        return 1
    fails = got['fails']

    # 表外第 21 條沒有批次欄，批次由章名回查，否則會被誤算成「未回收」
    skipped = sum(1 for c, _i, b, _q, _x in s['empty'] + s['hit']
                  if (b or chapter_len.get(c, (None,))[0]) not in batches)
    skipped += sum(1 for _c, _i, b, _q in s['nonempty'] if b not in batches)
    skipped += sum(n for _c, n, b, _g in s['empty_ch'] if b not in batches)

    st = compute_stats(rows, s)
    print('判空 %d/%d（%.0f%%）' % (st['empty'], len(rows), 100 * st['empty'] / len(rows)))
    print('分群： ' + '  '.join('%s 命中 %d/%d' % (g, v[1], v[0])
                                for g, v in sorted(st['grp'].items()) if v[0]))
    print('領域： ' + '  '.join('%s=%d' % (d, st['dom'][d]) for d in DOM_ORDER))
    print('姿態： ' + '  '.join('%s=%d' % kv for kv in
                               sorted(st['mode'].items(), key=lambda kv: -kv[1])))

    full = len(batches) == len(batch_chapters)
    warns = b_warnings(s, st) if full else []
    if not full:
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
    ap = argparse.ArgumentParser(description='呂氏春秋標註驗收（A 類硬條件＋B 類 WARN）')
    ap.add_argument('batches', nargs='*', help='只檢查這些批次，如 b01 b02；預設全部')
    ap.add_argument('--check-spec', action='store_true',
                    help='發包前自檢：只拿 SPEC.md 對 b01.md–b18.md')
    ap.add_argument('--out-dir', default=os.path.join(BASE, 'out'),
                    help='外包輸出目錄，預設 delegation/lushi-chunqiu/out')
    args = ap.parse_args()
    if args.check_spec:
        return check_spec()
    out_dir = args.out_dir
    if not os.path.isabs(out_dir):
        out_dir = os.path.join(BASE, out_dir)
    return run(out_dir, args.batches)


if __name__ == '__main__':
    sys.exit(main())
