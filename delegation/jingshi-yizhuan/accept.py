"""京氏易傳 A 類驗收（體裁陷阱，硬條件）＋ B 類數量提示（只 WARN，不擋收）。

錨點與 A 類 9 條條款一律從 SPEC.md 現場解析，本檔不手抄任何章名、段號、引句、
領域或 mode——孔叢子那次 18 個假 FAIL 的成因就是驗收器自己抄了一份沒被驗證過
的清單。SPEC 改一個字，本檔行為就跟著變，不需要改 Python。

本書三個體裁性的解析限制（違反任何一條驗收就會失真）：

1. 章名是「卦符＋全形空格 U+3000＋下卦上卦＋全形空格＋卦名」，且乾／震／坎三章
   的上下卦在原始文本裡就寫反了。**全部逐字比對**，不正規化空格、不修卦序、
   不用卦名做模糊比對。
2. SPEC 的錨點表與條款用卦名簡稱（`家人`），批次檔用全名（`䷤　離下巽上　家人`）。
   簡稱→全名的映射由批次檔現場建立，並驗證一對一；一對多即 FAIL，不靜默挑一個。
3. 段落內有大量夾注 `〈…〉`，其中 `總結`[4]–[8] 是橫跨五段的未閉合區間、
   `算法`[22] 另有孤懸的 `〉`。**本檔不做任何括號配對或夾注剝除**，照行讀、照行存。

用法：
  PYTHONIOENCODING=utf-8 python delegation/jingshi-yizhuan/accept.py --check-spec
      發包前跑：只拿 SPEC.md 對 b01.md–b04.md，驗批次表段數／章數、章名歸屬、
      錨點段號範圍、逐字引句是否真的存在、簡稱映射是否一對一、A 類 9 條是否解得出來。
      任一不符即 FAIL（規格書寫錯，發包出去會全批白做）。
  PYTHONIOENCODING=utf-8 python delegation/jingshi-yizhuan/accept.py [b01 ...]
      回收後跑；不給批次就檢查 out/ 底下所有已存在的批次。
  PYTHONIOENCODING=utf-8 python delegation/jingshi-yizhuan/accept.py --out-dir _selftest/perfect
      對指定目錄跑（驗收器自身的反向驗證用）。
  --spec PATH 可指向 SPEC.md 的變異副本，用來反證 --check-spec 有牙齒。
"""
import argparse
import glob
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
IDEO_SPACE = '　'
DOM_ORDER = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII', 'XIII']
DOMS = set(DOM_ORDER)
MODES = {'observation', 'proposition', 'prescription', 'formalization',
         'narrative', 'ritual', 'expression', 'worked_instance'}

# `章`[段]、`章`[段][段]、`章`[段]–[段] 三種寫法；章名逐字，不做任何正規化
REF_RE = re.compile(r'`([^`\n]+?)`((?:\[\d+\](?:\s*[–—-]\s*\[\d+\])?)+)')
DASH = '[–—-]'


# ---------------------------------------------------------------- 批次檔

def read_batches(base=BASE):
    """bNN.md → paras / chapter_len / batch_chapters；順便驗章標頭與批次標頭的段數。

    段落一行一段，原文照存（含 `〈…〉` 夾注與未閉合區間），不做任何前處理。
    """
    paras, chapter_len, batch_chapters, header_bad = {}, {}, {}, []
    for f in sorted(glob.glob(os.path.join(base, 'b0*.md'))):
        batch = os.path.basename(f)[:3]
        batch_chapters.setdefault(batch, [])
        chapter, counts, declared = None, {}, None
        for line in open(f, encoding='utf-8'):
            m = re.match(r'^> 本批 (\d+) 段，含 (\d+) 章。', line)
            if m:
                declared = (int(m.group(1)), int(m.group(2)))
                continue
            m = re.match(r'^## (.+?)（(\d+) 段）\s*$', line)
            if m:
                chapter = m.group(1)
                if chapter in chapter_len:
                    header_bad.append('%s 章名重複出現：%s' % (batch, chapter))
                chapter_len[chapter] = (batch, int(m.group(2)))
                batch_chapters[batch].append(chapter)
                continue
            m = re.match(r'^\[(\d+)\]\s?(.*)$', line)
            if m and chapter is not None:
                key = (chapter, int(m.group(1)))
                if key in paras:
                    header_bad.append('%s %s[%s] 段號重複' % (batch, chapter, m.group(1)))
                paras[key] = (batch, m.group(2).rstrip('\n'))
                counts[chapter] = counts.get(chapter, 0) + 1
        for ch in batch_chapters[batch]:
            if counts.get(ch, 0) != chapter_len[ch][1]:
                header_bad.append('%s %s 標頭寫 %d 段，實際 %d 段'
                                  % (batch, ch, chapter_len[ch][1], counts.get(ch, 0)))
            idxs = sorted(i for (c, i) in paras if c == ch)
            if idxs != list(range(1, len(idxs) + 1)):
                header_bad.append('%s %s 段號非 1–N 連號：%s' % (batch, ch, idxs[:8]))
        if declared:
            tot = sum(chapter_len[c][1] for c in batch_chapters[batch])
            if declared[0] != tot:
                header_bad.append('%s 批次標頭寫 %d 段，實際 %d 段' % (batch, declared[0], tot))
            if declared[1] != len(batch_chapters[batch]):
                header_bad.append('%s 批次標頭寫 %d 章，實際 %d 章'
                                  % (batch, declared[1], len(batch_chapters[batch])))
    return paras, chapter_len, batch_chapters, header_bad


class Resolver:
    """簡稱（`家人`）→ 全名（`䷤　離下巽上　家人`）。映射由批次檔現場建立。

    全名的簡稱取最後一個全形空格之後的部分；書末三章沒有卦符前綴，簡稱即全名。
    一個簡稱對到多個全名時回 ambiguous（呼叫端報 FAIL），絕不靜默挑一個。
    """

    def __init__(self, chapter_len):
        self.chapter_len = chapter_len
        self.smap = {}
        for full in chapter_len:
            self.smap.setdefault(self.short_of(full), []).append(full)

    @staticmethod
    def short_of(full):
        return full.split(IDEO_SPACE)[-1] if IDEO_SPACE in full else full

    def ambiguous(self):
        return {s: v for s, v in self.smap.items() if len(v) > 1}

    def resolve(self, name):
        """→ (全名 or None, 'full'／'short'／'suffix'／'ambiguous'／'missing')"""
        if name in self.chapter_len:
            return name, 'full'
        v = self.smap.get(name)
        if v:
            return (v[0], 'short') if len(v) == 1 else (None, 'ambiguous')
        cands = sorted({f for s, fs in self.smap.items() if s.endswith(name) for f in fs})
        if len(cands) == 1:
            return cands[0], 'suffix'
        return (None, 'ambiguous') if cands else (None, 'missing')


# ---------------------------------------------------------------- SPEC 解析

def expand_refs(text):
    """把一段文字裡的 `章`[段] 全部展開成 [(章名原文, 段號), ...]。"""
    out = []
    for m in REF_RE.finditer(text):
        ch = m.group(1)
        for a, b in re.findall(r'\[(\d+)\](?:\s*%s\s*\[(\d+)\])?' % DASH, m.group(2)):
            if b:
                out += [(ch, k) for k in range(int(a), int(b) + 1)]
            else:
                out.append((ch, int(a)))
    return out


def refs_with_verdict(text):
    """條款文字裡每個 `章`[段] 指派給它後面第一個出現的「命中」或「判空」。

    A5「[18] 命中且含 XI，而 [11]／[9]／[10]／[4] 四段全部判空」這種一對多的
    成對條款靠這個拆開；只守一面就等於沒守。
    """
    marks = [(m.start(), m.group(0)) for m in re.finditer(r'命中|判空', text)]
    out = {'hit': [], 'empty': []}
    for m in REF_RE.finditer(text):
        nxt = next((w for p, w in marks if p >= m.end()), None)
        if nxt is None:
            continue
        out['hit' if nxt == '命中' else 'empty'] += expand_refs(m.group(0))
    return out


def table_rows(body):
    """markdown 表格 → 逐列 cell 陣列（跳過分隔列）。"""
    for line in body.split('\n'):
        line = line.strip()
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        if cells and all(set(c) <= set('-: ') and c for c in cells):
            continue
        yield cells


def parse_req(cell):
    """候選格欄 →〔必須合法的領域 id〕。`VII＋XI，**注文**…` → ['VII','XI']。"""
    body = re.sub(r'（[^）]*）', '', cell)
    body = re.split(r'[，。；]', body)[0]
    return [t for t in re.findall(r'[IVX]+', body) if t in DOMS]


def _sections(spec):
    out = {}
    for sec in re.split(r'^## ', spec, flags=re.M):
        out[sec.split('\n', 1)[0].strip()] = sec
    return out


def parse_spec(path=None):
    """把 SPEC.md 解析成驗收所需的全部錨點與 A/B 條款。本檔唯一的事實來源。"""
    path = path or os.path.join(BASE, 'SPEC.md')
    spec = open(path, encoding='utf-8').read()
    secs = _sections(spec)
    s = {'batch_table': [], 'empty': [], 'hit': [], 'a': {}, 'declared': {},
         'a4_dom': None, 'a5': None, 'a6': None, 'a7': None, 'a8': None,
         'a9': None, 'b_clauses': [], 'prose_refs': [], 'spec_path': path}

    # 批次表 | 批次 | 章 | 段數 | 章數 |（4 欄；錨點表是 5 欄，不會誤咬）
    for cells in table_rows(spec):
        if len(cells) == 4 and re.fullmatch(r'b0\d', cells[0]) \
                and cells[2].isdigit() and cells[3].isdigit():
            s['batch_table'].append((cells[0], cells[1], int(cells[2]), int(cells[3])))

    # 兩張錨點表 | 批次 | 章 | 段 | 逐字引句 | 誤撈／候選格 |
    for head, body in secs.items():
        if head.startswith('必須判空的錨點') or head.startswith('必須命中的錨點'):
            key = 'empty' if head.startswith('必須判空') else 'hit'
            for cells in table_rows(body):
                if len(cells) != 5 or not re.fullmatch(r'b0\d', cells[0]) \
                        or not cells[2].isdigit():
                    continue
                s[key].append({'batch': cells[0], 'ch': cells[1], 'idx': int(cells[2]),
                               'quote': cells[3], 'note': cells[4]})
        elif head.startswith('驗收條件'):
            a_body = body.split('### B 類', 1)[0]
            for m in re.finditer(r'^(\d+)\.\s+(.*)$', a_body, re.M):
                s['a'][int(m.group(1))] = m.group(2).strip()
            b_body = body.split('### B 類', 1)
            if len(b_body) == 2:
                for line in b_body[1].split('\n'):
                    if line.startswith('- '):
                        s['b_clauses'] += [c.strip() for c in
                                           re.split(r'[；，]', line[2:]) if c.strip()]

    a = s['a']
    m = re.search(r'上表 (\d+) 個必須判空錨點', a.get(2, ''))
    if m:
        s['declared']['empty'] = int(m.group(1))
    m = re.search(r'上表 (\d+) 個必須命中錨點', a.get(3, ''))
    if m:
        s['declared']['hit'] = int(m.group(1))
    m = re.search(r'全書 (\d+) 段', spec)
    if m:
        s['declared']['total'] = int(m.group(1))

    # A4 全書禁用領域
    m = re.search(r'不含\s*`([IVX]+)`', a.get(4, ''))
    if m:
        s['a4_dom'] = m.group(1)

    # A5／A6／A7 成對條款：`——` 之前是條款本體，之後是說明
    for no in (5, 6, 7):
        head = a.get(no, '').split('——')[0]
        if not head:
            continue
        v = refs_with_verdict(head)
        need = re.search(r'命中且含\s*([IVX]+)', head)
        s['a%d' % no] = {'hit': v['hit'], 'empty': v['empty'],
                         'need': need.group(1) if need else None}

    # A8 `算法`[22] 的 modes 含 expression、domains 含 VIII；其餘點名段全判空
    c8 = a.get(8, '')
    if c8:
        parts = c8.split('；')
        refs0 = expand_refs(parts[0])
        mm = re.search(r'`modes`\s*含\s*`([a-z_]+)`', parts[0])
        dm = re.search(r'`domains`\s*含\s*([IVX]+)', parts[0])
        s['a8'] = {'ref': refs0[0] if refs0 else None,
                   'mode': mm.group(1) if mm else None,
                   'dom': dm.group(1) if dm else None,
                   'empty': expand_refs(parts[1]) if len(parts) > 1 else []}

    # A9 全書 0 段的 mode；以及只准出現在某段的 mode
    c9 = a.get(9, '')
    if c9:
        p = c9.split('；')
        zero = re.search(r'不出現\s*(.+)$', p[0])
        zero = re.findall(r'`([a-z_]+)`', zero.group(1)) if zero else []
        only = None
        if len(p) > 1:
            om = re.search(r'`([a-z_]+)`\s*只出現在', p[1])
            if om:
                only = (om.group(1), expand_refs(p[1]))
        s['a9'] = {'zero': zero, 'only': only}

    # 全文散見的 `章`[段] 參照（規格書自證用的引例），用來驗章名／段號真的存在
    body_wo_tables = '\n'.join(l for l in spec.split('\n') if not l.strip().startswith('|'))
    s['prose_refs'] = expand_refs(body_wo_tables)
    return s


def parse_batch_cell(cell):
    """「蹇·謙·小過·歸妹·京氏易傳卷下 4／算法 22／總結 8」→ [(章, 段數 or None), ...]"""
    out = []
    for seg in cell.split('／'):
        for tok in seg.split('·'):
            tok = tok.strip()
            if not tok:
                continue
            m = re.match(r'^(.+?)\s+(\d+)$', tok)
            out.append((m.group(1).strip(), int(m.group(2))) if m else (tok, None))
    return out


def normalize(s, R):
    """把 SPEC 裡所有簡稱章名換成批次檔的全名；解不出來的原樣留著並記錄。"""
    seen = {}

    def fix(name):
        if name not in seen:
            seen[name] = R.resolve(name)
        return seen[name][0] or name

    for row in s['empty'] + s['hit']:
        row['full'] = fix(row['ch'])
    for k in ('a5', 'a6', 'a7'):
        if s[k]:
            for side in ('hit', 'empty'):
                s[k][side] = [(fix(c), i) for c, i in s[k][side]]
    if s['a8']:
        if s['a8']['ref']:
            s['a8']['ref'] = (fix(s['a8']['ref'][0]), s['a8']['ref'][1])
        s['a8']['empty'] = [(fix(c), i) for c, i in s['a8']['empty']]
    if s['a9'] and s['a9']['only']:
        mode, refs = s['a9']['only']
        s['a9']['only'] = (mode, [(fix(c), i) for c, i in refs])
    s['prose_refs'] = [(fix(c), i) for c, i in s['prose_refs']]
    s['name_map'] = seen
    return s


# ---------------------------------------------------------------- SPEC 自檢

def check_spec(spec_path=None, base=BASE):
    paras, chapter_len, batch_chapters, header_bad = read_batches(base)
    R = Resolver(chapter_len)
    s = normalize(parse_spec(spec_path), R)
    bad, notes = [], []

    total = sum(n for _b, n in chapter_len.values())
    print('批次檔：%d 章 %d 段（%s）'
          % (len(chapter_len), total, os.path.basename(s['spec_path'])))
    print('SPEC 解析：判空錨點 %d／命中錨點 %d／A 類條款 %d 條／B 類條款 %d 條'
          % (len(s['empty']), len(s['hit']), len(s['a']), len(s['b_clauses'])))
    bad += ['S0 批次檔：' + x for x in header_bad]

    # S1 簡稱→全名映射一對一
    for short, fulls in sorted(R.ambiguous().items()):
        bad.append('S1 簡稱 `%s` 對到 %d 個全名章，映射非一對一：%s'
                   % (short, len(fulls), fulls))
    for name, (full, how) in sorted(s['name_map'].items()):
        if full is None:
            bad.append('S1 SPEC 章名在批次檔不存在（%s）：`%s`' % (how, name))
        elif how == 'suffix':
            bad.append('S1 SPEC 用了非正式簡稱 `%s`，批次檔與錨點表寫 `%s`（僅靠後綴才對得上）'
                       % (name, R.short_of(full)))

    # S2 批次表段數／章數／章名歸屬
    if s['declared'].get('total') not in (None, total):
        bad.append('S2 SPEC 正文宣告全書 %d 段，批次檔實際 %d 段'
                   % (s['declared']['total'], total))
    tbl_total = 0
    seen_ch = set()
    for batch, cell, n_para, n_ch in s['batch_table']:
        tbl_total += n_para
        real_ch = batch_chapters.get(batch, [])
        real_para = sum(chapter_len[c][1] for c in real_ch)
        if real_para != n_para:
            bad.append('S2 %s 段數 SPEC 寫 %d，實際 %d' % (batch, n_para, real_para))
        if len(real_ch) != n_ch:
            bad.append('S2 %s 章數 SPEC 寫 %d，實際 %d' % (batch, n_ch, len(real_ch)))
        cell_chs = parse_batch_cell(cell)
        if len(cell_chs) != n_ch:
            bad.append('S3 %s 章欄列出 %d 章，章數欄寫 %d' % (batch, len(cell_chs), n_ch))
        for name, n in cell_chs:
            full, how = R.resolve(name)
            if full is None:
                bad.append('S3 %s 章欄章名解不出（%s）：%s' % (batch, how, name))
                continue
            seen_ch.add(full)
            if chapter_len[full][0] != batch:
                bad.append('S3 %s 宣告的章 %s 實際在 %s' % (batch, full, chapter_len[full][0]))
            if n is not None and chapter_len[full][1] != n:
                bad.append('S3 %s %s 段數 SPEC 寫 %d，實際 %d'
                           % (batch, full, n, chapter_len[full][1]))
    if s['batch_table'] and tbl_total != total:
        bad.append('S2 批次表段數合計 %d，批次檔實際 %d' % (tbl_total, total))
    for full in chapter_len:
        if full not in seen_ch:
            bad.append('S3 批次檔有章 %s，SPEC 批次表未列' % full)

    # S4 兩張錨點表的宣告筆數
    for key, label in (('empty', '判空'), ('hit', '命中')):
        d = s['declared'].get(key)
        if d is not None and len(s[key]) != d:
            bad.append('S4 %s錨點表 %d 列，A 類宣告 %d 個' % (label, len(s[key]), d))

    # S5 錨點列：章名／段號範圍／批次歸屬／逐字引句
    for key, label in (('empty', '判空'), ('hit', '命中')):
        for row in s[key]:
            full, idx = row['full'], row['idx']
            if full not in chapter_len:
                bad.append('S5 %s錨點章名不存在：%s[%d]' % (label, row['ch'], idx))
                continue
            n = chapter_len[full][1]
            if not 1 <= idx <= n:
                bad.append('S5 %s[%d] 段號超出該章 1–%d' % (row['ch'], idx, n))
                continue
            batch, text = paras[(full, idx)]
            if batch != row['batch']:
                bad.append('S5 %s[%d] 批次 SPEC 寫 %s，實際 %s'
                           % (row['ch'], idx, row['batch'], batch))
            for q in re.findall(r'「([^「」]+)」', row['quote']):
                if q not in text:
                    bad.append('S6 %s錨點逐字引句不在原文：%s[%d]「%s」'
                               % (label, row['ch'], idx, q))

    # S7 同一段不得同時落在兩張表；命中表的候選格要解得出合法領域且不得含禁用領域
    empty_keys = {(r['full'], r['idx']) for r in s['empty']}
    hit_keys = {(r['full'], r['idx']) for r in s['hit']}
    for k in sorted(empty_keys & hit_keys):
        bad.append('S7 %s[%d] 同時在判空表與命中表' % k)
    for row in s['hit']:
        need = parse_req(row['note'])
        if not need:
            bad.append('S7 %s[%d] 候選格解不出領域：%s' % (row['ch'], row['idx'], row['note']))
        if s['a4_dom'] and s['a4_dom'] in need:
            bad.append('S7 %s[%d] 候選格含全書禁用領域 %s'
                       % (row['ch'], row['idx'], s['a4_dom']))

    # S8 A 類 9 條全部要解得出來，且點名的段要存在、與兩張錨點表方向一致
    for no in range(1, 10):
        if no not in s['a']:
            bad.append('S8 驗收條件 A 類缺第 %d 條' % no)
    if not s['a4_dom']:
        bad.append('S8 A4 解不出全書禁用領域')
    elif s['a4_dom'] not in DOMS:
        bad.append('S8 A4 禁用領域非法：%s' % s['a4_dom'])

    def _clause_refs(no, spec_item):
        if spec_item is None:
            bad.append('S8 A%d 解不出條款內容' % no)
            return
        for side, keyset, label in (('hit', hit_keys, '命中'), ('empty', empty_keys, '判空')):
            for ch, idx in spec_item.get(side, []):
                if (ch, idx) not in paras:
                    bad.append('S8 A%d 點名的段不存在：%s[%d]' % (no, ch, idx))
                elif (ch, idx) not in keyset:
                    bad.append('S8 A%d 要求 %s[%d] %s，但它不在%s錨點表裡'
                               % (no, ch, idx, label, label))
        if not spec_item.get('hit') or not spec_item.get('empty'):
            bad.append('S8 A%d 只解出單向（命中 %d／判空 %d），成對條款只守一面等於沒守'
                       % (no, len(spec_item.get('hit', [])), len(spec_item.get('empty', []))))

    for no in (5, 6, 7):
        _clause_refs(no, s['a%d' % no])
    if s['a5'] and not s['a5']['need']:
        bad.append('S8 A5 解不出「命中且含 X」的領域')
    if s['a5'] and s['a5']['need'] and s['a5']['need'] not in DOMS:
        bad.append('S8 A5 領域非法：%s' % s['a5']['need'])

    if s['a8'] is None or s['a8']['ref'] is None:
        bad.append('S8 A8 解不出目標段')
    else:
        ref = s['a8']['ref']
        if ref not in paras:
            bad.append('S8 A8 目標段不存在：%s[%d]' % ref)
        elif ref not in hit_keys:
            bad.append('S8 A8 目標段 %s[%d] 不在命中錨點表' % ref)
        if s['a8']['mode'] not in MODES:
            bad.append('S8 A8 mode 非法或解不出：%s' % s['a8']['mode'])
        if s['a8']['dom'] not in DOMS:
            bad.append('S8 A8 領域非法或解不出：%s' % s['a8']['dom'])
        if not s['a8']['empty']:
            bad.append('S8 A8 解不出必須判空的段')
        for ch, idx in s['a8']['empty']:
            if (ch, idx) not in paras:
                bad.append('S8 A8 點名判空的段不存在：%s[%d]' % (ch, idx))
            if (ch, idx) in hit_keys:
                bad.append('S8 A8 要求 %s[%d] 判空，但它在命中錨點表' % (ch, idx))

    if s['a9'] is None or not s['a9']['zero']:
        bad.append('S8 A9 解不出全書 0 段的 mode 清單')
    else:
        for m in s['a9']['zero']:
            if m not in MODES:
                bad.append('S8 A9 非法 mode：%s' % m)
        only = s['a9']['only']
        if not only:
            bad.append('S8 A9 解不出「只出現在某段」的 mode')
        else:
            if only[0] not in MODES:
                bad.append('S8 A9 非法 mode：%s' % only[0])
            for ch, idx in only[1]:
                if (ch, idx) not in paras:
                    bad.append('S8 A9 點名的段不存在：%s[%d]' % (ch, idx))
    if not s['b_clauses']:
        bad.append('S8 B 類數量帶寬解不出任何條款')

    # S9 SPEC 散文裡自證用的 `章`[段] 也要真的存在（章名寫錯會連累判者對位）
    for ch, idx in sorted(set(s['prose_refs'])):
        if ch not in chapter_len:
            bad.append('S9 SPEC 散文引用的章不存在：`%s`[%d]' % (ch, idx))
        elif (ch, idx) not in paras:
            bad.append('S9 SPEC 散文引用的段超出範圍：%s[%d]（該章 %d 段）'
                       % (ch, idx, chapter_len[ch][1]))

    # 提示層：散文引號不是「逐字引句」欄，對不上只提醒不擋收
    notes += _prose_quote_notes(s, paras, R)

    print('--- SPEC 自檢 FAIL：%d ---' % len(bad))
    for b in bad:
        print(b)
    if notes:
        print('--- 提示（散文引句對不上原文，非 FAIL）：%d ---' % len(notes))
        for n in notes:
            print(n)
    return 0 if not bad else 1


def _prose_quote_notes(s, paras, R):
    """散文段落裡「`章`[段]「引句」」形式的自證，逐字對一次原文。只作提示。"""
    spec = open(s['spec_path'], encoding='utf-8').read()
    out = []
    pat = re.compile(r'`([^`\n]+?)`(\[\d+\])[^\n]{0,4}?「([^「」]{4,})」')
    for line in spec.split('\n'):
        if line.strip().startswith('|'):
            continue
        for m in pat.finditer(line):
            full, _how = R.resolve(m.group(1))
            key = (full, int(m.group(2).strip('[]')))
            if key in paras and m.group(3) not in paras[key][1]:
                out.append('N %s%s「%s」不是該段原文的子字串'
                           % (m.group(1), m.group(2), m.group(3)))
    return out


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


def _dom(rows, key):
    r = rows.get(key)
    return None if r is None else list(r.get('domains') or [])


def _refs(keys):
    """(章, 段) 序列 → 可讀字串；章名逐字照印，不用 repr（否則全形空格變 \\u3000）。"""
    return '、'.join('%s[%d]' % k for k in keys)


def _near_hint(name, chapter_len):
    """章名對不上時指出是哪一種改動：空白被正規化、或卦序被「修正」。"""
    if not isinstance(name, str):
        return ''
    flat = re.sub(r'\s', '', name)
    for full in chapter_len:
        ff = re.sub(r'\s', '', full)
        if ff == flat:
            return '（＝ %s，只差空白字元；全形空格 U+3000 不可換）' % full
        if sorted(ff) == sorted(flat):
            return '（＝ %s，字序被改；原始文本的錯序不可修）' % full
    return ''


def a1_shape(rows, batches, chapter_len, batch_chapters, dup):
    """A1 rows 段數與批次檔一致、章名逐字相符、para_index 連號、值域合法、reason 非空。"""
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
        strays = sorted({r.get('chapter') for r in got if r.get('chapter') not in valid},
                        key=str)
        for c in strays[:5]:
            f.append('A1 %s 出現非該批章名（須逐字照抄，含全形空格與乾／震／坎的錯序）：%s%s'
                     % (b, c, _near_hint(c, chapter_len)))
        for ch in chs:
            idxs = sorted(i for (c, i), r in rows.items() if c == ch and r['_batch'] == b)
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
        badd = [x for x in (r.get('domains') or []) if x not in DOMS]
        badm = [x for x in (r.get('modes') or []) if x not in MODES]
        if badd:
            f.append('A1 %s[%d] 非法 domain %s' % (c, i, badd))
        if badm:
            f.append('A1 %s[%d] 非法 mode %s' % (c, i, badm))
    return f


def a2_empty_anchors(rows, batches, s):
    """A2 判空錨點表全部 domains == []。"""
    f = []
    for row in s['empty']:
        if row['batch'] not in batches:
            continue
        d = _dom(rows, (row['full'], row['idx']))
        if d is None:
            f.append('A2 缺段 %s[%d]' % (row['full'], row['idx']))
        elif d:
            f.append('A2 必須判空錨點被填 %s[%d] → %s（易誤撈成 %s）'
                     % (row['full'], row['idx'], d, row['note']))
    return f


def a3_hit_anchors(rows, batches, s):
    """A3 命中錨點表全部 domains != []。"""
    f = []
    for row in s['hit']:
        if row['batch'] not in batches:
            continue
        d = _dom(rows, (row['full'], row['idx']))
        if d is None:
            f.append('A3 缺段 %s[%d]' % (row['full'], row['idx']))
        elif not d:
            f.append('A3 必須命中錨點被判空 %s[%d]（候選格 %s）'
                     % (row['full'], row['idx'], row['note']))
    return f


def a4_no_forbidden_domain(rows, s):
    """A4 全書任何一段的 domains 都不含 XII（整書級條件，不是錨點級）。"""
    dom = s['a4_dom']
    if not dom:
        return ['A4 SPEC 解不出全書禁用領域']
    bad = sorted((c, i) for (c, i), r in rows.items() if dom in (r.get('domains') or []))
    return ['A4 全書不得含 %s，實得 %d 段：%s'
            % (dom, len(bad), _refs(bad[:6]))] if bad else []


def _pair_clause(rows, batches, s, no, chapter_len):
    """A5／A6／A7：成對條款，一側必須命中、另一側必須判空，判齊即閘門判反。"""
    item = s['a%d' % no]
    if item is None:
        return ['A%d SPEC 解不出本條款' % no]
    f, seen = [], {}
    for side in ('hit', 'empty'):
        for ch, idx in item[side]:
            batch = chapter_len.get(ch, (None,))[0]
            if batch not in batches:
                continue
            d = _dom(rows, (ch, idx))
            if d is None:
                f.append('A%d 缺段 %s[%d]' % (no, ch, idx))
                continue
            seen[(ch, idx)] = (side, d)
            if side == 'hit':
                if not d:
                    f.append('A%d %s[%d] 必須命中卻判空' % (no, ch, idx))
                elif item['need'] and item['need'] not in d:
                    f.append('A%d %s[%d] 必須命中且含 %s，實得 %s'
                             % (no, ch, idx, item['need'], d))
            elif d:
                f.append('A%d %s[%d] 必須判空卻命中 → %s' % (no, ch, idx, d))
    hits = [(k, v[1]) for k, v in seen.items() if v[0] == 'hit']
    emps = [(k, v[1]) for k, v in seen.items() if v[0] == 'empty']
    for hk, hd in hits:
        for ek, ed in emps:
            if sorted(hd) == sorted(ed):
                f.append('A%d %s[%d] 與 %s[%d] 判齊（同為 %s），必須判反方向'
                         % (no, hk[0], hk[1], ek[0], ek[1], sorted(hd) or '[]'))
    return f


def a8_expression(rows, batches, s, chapter_len):
    """A8 晁公武自述段的 modes 含 expression、domains 含 VIII；書志與總結段全判空。"""
    item = s['a8']
    if item is None or item['ref'] is None:
        return ['A8 SPEC 解不出本條款']
    f = []
    ch, idx = item['ref']
    if chapter_len.get(ch, (None,))[0] in batches:
        r = rows.get((ch, idx))
        if r is None:
            f.append('A8 缺段 %s[%d]' % (ch, idx))
        else:
            if item['mode'] not in (r.get('modes') or []):
                f.append('A8 %s[%d] modes 未含 %s → %s'
                         % (ch, idx, item['mode'], r.get('modes')))
            if item['dom'] not in (r.get('domains') or []):
                f.append('A8 %s[%d] domains 未含 %s → %s'
                         % (ch, idx, item['dom'], r.get('domains')))
    for c, i in item['empty']:
        if chapter_len.get(c, (None,))[0] not in batches:
            continue
        d = _dom(rows, (c, i))
        if d is None:
            f.append('A8 缺段 %s[%d]' % (c, i))
        elif d:
            f.append('A8 %s[%d] 必須判空卻命中 → %s' % (c, i, d))
    return f


def a9_modes(rows, batches, s, chapter_len):
    """A9 narrative／ritual／worked_instance 全書 0 段；expression 只出現在指定段。"""
    item = s['a9']
    if item is None:
        return ['A9 SPEC 解不出本條款']
    f = []
    for m in item['zero']:
        bad = sorted((c, i) for (c, i), r in rows.items() if m in (r.get('modes') or []))
        if bad:
            f.append('A9 `%s` 應 0 段，實得 %d：%s' % (m, len(bad), _refs(bad[:5])))
    if item['only']:
        mode, allow = item['only']
        allowed = set(allow)
        bad = sorted((c, i) for (c, i), r in rows.items()
                     if mode in (r.get('modes') or []) and (c, i) not in allowed)
        if bad:
            f.append('A9 `%s` 只准出現在 %s，實得多 %d 段：%s'
                     % (mode, _refs(sorted(allowed)), len(bad), _refs(bad[:5])))
        for c, i in sorted(allowed):
            if chapter_len.get(c, (None,))[0] not in batches:
                continue
            r = rows.get((c, i))
            if r is not None and mode not in (r.get('modes') or []):
                f.append('A9 %s[%d] 應含 `%s`，實得 %s' % (c, i, mode, r.get('modes')))
    return f


# ---------------------------------------------------------------- B 類（WARN）

def compute_stats(rows):
    st = {'dom': {d: 0 for d in DOM_ORDER}, 'mode': {}, 'empty': 0, 'hit': 0}
    for r in rows.values():
        d, m = (r.get('domains') or []), (r.get('modes') or [])
        st['empty' if not d else 'hit'] += 1
        for x in d:
            if x in st['dom']:
                st['dom'][x] += 1
        for x in m:
            st['mode'][x] = st['mode'].get(x, 0) + 1
    st['n_dom_hit'] = sum(1 for d in DOM_ORDER if st['dom'][d])
    st['n_dom_zero'] = len(DOM_ORDER) - st['n_dom_hit']
    return st


def b_metric(clause, st):
    """B 類條款字面 → 一個實測值；對不上回 None（只影響 WARN 呈現，不擋收）。"""
    if '判空' in clause:
        return '判空段數', st['empty']
    if '命中總數' in clause:
        return '命中段數', st['hit']
    if '命中領域覆蓋' in clause:
        return '命中領域格數', st['n_dom_hit']
    if '零段' in clause:
        return '零段 domains 格數', st['n_dom_zero']
    m = re.match(r'^`([a-z_]+)`', clause)
    if m:
        return m.group(1), st['mode'].get(m.group(1), 0)
    m = re.match(r'^([IVX]+)\s*命中', clause)
    if m and m.group(1) in DOMS:
        return m.group(1), st['dom'][m.group(1)]
    return None


def b_warnings(s, st):
    warns = []
    for c in s['b_clauses']:
        got = b_metric(c, st)
        if got is None:
            continue
        label, val = got
        m = re.search(r'≥\s*(\d+)', c)
        if m:
            if val < int(m.group(1)):
                warns.append('B 「%s」實測 %s=%d，低於下限 %s' % (c, label, val, m.group(1)))
            continue
        m = re.search(r'≤\s*(\d+)', c)
        if m:
            if val > int(m.group(1)):
                warns.append('B 「%s」實測 %s=%d，高於上限 %s' % (c, label, val, m.group(1)))
            continue
        m = re.search(r'(\d+)\s*[–—-]\s*(\d+)', c)
        if m and not int(m.group(1)) <= val <= int(m.group(2)):
            warns.append('B 「%s」實測 %s=%d，落在帶寬 %s–%s 之外'
                         % (c, label, val, m.group(1), m.group(2)))
    return warns


# ---------------------------------------------------------------- main

def run(out_dir, want, spec_path=None, base=BASE):
    paras, chapter_len, batch_chapters, header_bad = read_batches(base)
    R = Resolver(chapter_len)
    s = normalize(parse_spec(spec_path), R)
    if not (s['empty'] and s['hit'] and len(s['a']) >= 9):
        print('!! SPEC 錨點表或 A 類條款未解析成功，先跑 --check-spec')
        return 2
    for name, (full, how) in sorted(s['name_map'].items()):
        if full is None:
            print('!! SPEC 章名 `%s` 對不到批次檔任何章（%s），相關條款會失效，先跑 --check-spec'
                  % (name, how))
        elif how == 'suffix':
            print('（注意：SPEC 用簡稱 `%s`，本檔按後綴對到 `%s`；請回頭修 SPEC）'
                  % (name, full))

    rows, batches, dup = load_out(out_dir, want)
    print('回收批次：%s，共 %d 段（來源 %s）'
          % (' '.join(batches) or '(無)', len(rows), os.path.relpath(out_dir, base)))
    if not rows:
        return 1

    fails = ['A1 批次檔標頭：' + x for x in header_bad]
    fails += a1_shape(rows, batches, chapter_len, batch_chapters, dup)
    fails += a2_empty_anchors(rows, batches, s)
    fails += a3_hit_anchors(rows, batches, s)
    fails += a4_no_forbidden_domain(rows, s)
    for no in (5, 6, 7):
        fails += _pair_clause(rows, batches, s, no, chapter_len)
    fails += a8_expression(rows, batches, s, chapter_len)
    fails += a9_modes(rows, batches, s, chapter_len)

    skipped = sum(1 for r in s['empty'] + s['hit'] if r['batch'] not in batches)

    st = compute_stats(rows)
    print('判空 %d/%d（%.0f%%）；命中 %d 段'
          % (st['empty'], len(rows), 100 * st['empty'] / len(rows), st['hit']))
    print('領域： ' + '  '.join('%s=%d' % (d, st['dom'][d]) for d in DOM_ORDER))
    print('姿態： ' + '  '.join('%s=%d' % kv for kv in
                               sorted(st['mode'].items(), key=lambda kv: -kv[1])))

    full_run = len(batches) == len(batch_chapters)
    warns = b_warnings(s, st) if full_run else []
    if not full_run:
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
    ap = argparse.ArgumentParser(description='京氏易傳標註驗收（A 類硬條件＋B 類 WARN）')
    ap.add_argument('batches', nargs='*', help='只檢查這些批次，如 b01 b02；預設全部')
    ap.add_argument('--check-spec', action='store_true',
                    help='發包前自檢：只拿 SPEC.md 對 b01.md–b04.md')
    ap.add_argument('--spec', default=None, help='改用指定的 SPEC 檔（變異副本反證用）')
    ap.add_argument('--out-dir', default=os.path.join(BASE, 'out'),
                    help='外包輸出目錄，預設 delegation/jingshi-yizhuan/out')
    args = ap.parse_args()
    spec = args.spec
    if spec and not os.path.isabs(spec):
        spec = os.path.join(BASE, spec)
    if args.check_spec:
        return check_spec(spec)
    out_dir = args.out_dir
    if not os.path.isabs(out_dir):
        out_dir = os.path.join(BASE, out_dir)
    return run(out_dir, args.batches, spec)


if __name__ == '__main__':
    sys.exit(main())
