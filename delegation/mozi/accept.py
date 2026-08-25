"""墨子 A 類驗收（體裁陷阱，硬條件）＋ B 類數量提示（只 WARN，不擋收）。

錨點一律從 SPEC.md 的四張表（必須整章判空／必須判空／必須命中／必須非空）、
「一格都不得填 XII」清單與 A 類 19 條條文現場解析，本檔不手抄任何章名、段號、
引句或領域——孔叢子那次 18 個假 FAIL 的成因就是驗收器自己抄了一份沒被驗證過的
清單。SPEC 改一個字，本檔行為就跟著變，不需要改 Python。
本檔只寫死 schema 常數：13 個領域 id 與 8 個 mode id，而且開機時回頭跟 SPEC 的
兩張 id 表對拍。

異體字：本版 `爲` 1,387／`為` 0、`衆` 162／`眾` 0，`�` `□` 是底本既有狀態。
引句比對**一律逐字、零正規化**——正規化會讓打錯的 SPEC 引句蒙混過關。

用法：
  PYTHONIOENCODING=utf-8 python delegation/mozi/accept.py --check-spec
      發包前跑：只拿 SPEC.md 對 b01.md–b17.md，驗批次表／五群表／四張錨點表／
      底本事實／條文與表格漂移／跨批盲測宣稱。
  PYTHONIOENCODING=utf-8 python delegation/mozi/accept.py [b01 ...]
      回收後跑；不給批次就檢查 out/ 底下所有已存在的批次。
  PYTHONIOENCODING=utf-8 python delegation/mozi/accept.py --out-dir _selftest/perfect
      對指定目錄跑（驗收器自身的反向驗證用）。
"""
import argparse
import difflib
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
          '七': 7, '八': 8, '九': 9, '十': 10, '十一': 11, '十二': 12}

# 段落引用：`章名`[n]、`章名`[n][m][k]、`章名`[a]–[b]。章名不含括號引號空白，
# 才不會把 `reason` 用「`[1]` 內第 N 條」這種句子誤讀成章名。
REF = re.compile(r'`([^`\[\]「」（）\s]+)`((?:\[\d+\])+(?:[–\-]\[\d+\])?)')
# 逐字引句：`章`[n] 後面「緊接」引號才算，中間隔了字的一律不當引句
QUOTED = re.compile(r'`([^`\[\]「」（）\s]+)`\[(\d+)\]「([^「」]+)」')


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


# ---------------------------------------------------------------- 小工具

def _sections(spec):
    out = {}
    for sec in re.split(r'^## ', spec, flags=re.M):
        out[sec.split('\n', 1)[0].strip()] = sec
    return out


def _quotes(cell):
    return re.findall(r'「([^「」]+)」', cell)


def quote_ok(q, text):
    """引句對拍：`**` 是 markdown 不是原文，`…` 是我省略的中段，逐段順序比對。
    **不做任何字元正規化**——`爲`／`為` 對不上就是對不上。"""
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


def _refs(text):
    """把一段文字裡所有 `章`[n] 展開成 (章, 段) 串，支援 [n][m] 與 [a]–[b]。"""
    out = []
    for m in REF.finditer(text):
        name, idxs = m.group(1), m.group(2)
        rng = re.match(r'^\[(\d+)\][–\-]\[(\d+)\]$', idxs)
        if rng:
            out += [(name, i) for i in range(int(rng.group(1)), int(rng.group(2)) + 1)]
        else:
            out += [(name, int(x)) for x in re.findall(r'\[(\d+)\]', idxs)]
    return out


def _dom_list(txt):
    return [t for t in re.split(r'[^IVX]+', txt) if t in DOMS]


def _num(x):
    return int(str(x).replace(',', ''))


def _batch_range(cell):
    """「b02–b08」→ ['b02'…'b08']；「b01」→ ['b01']。"""
    m = re.match(r'^(b\d\d)(?:[–\-](b\d\d))?$', cell.strip())
    if not m:
        return None
    a = int(m.group(1)[1:])
    b = int(m.group(2)[1:]) if m.group(2) else a
    return ['b%02d' % i for i in range(a, b + 1)]


def _pct(hit, tot):
    return 100 * hit // tot if tot else 0


# ---------------------------------------------------------------- SPEC 解析

def parse_spec():
    """把 SPEC.md 解析成驗收所需的全部錨點與宣告值。本檔唯一的事實來源。"""
    spec = open(os.path.join(BASE, 'SPEC.md'), encoding='utf-8').read()
    secs = _sections(spec)
    s = {'spec': spec, 'empty_ch': [], 'empty': [], 'hit': [], 'hit_subs': [],
         'nonempty': [], 'gray': [], 'xii_tokens': [], 'a9_tokens': [],
         'batch_table': [], 'group_table': [], 'gate': [], 'gate_chapters': {},
         'polarity': [], 'forbid_dom': [], 'table_forbid': [], 'zero_modes': [],
         'max_dom': None, 'a6': None, 'a7': [], 'id_forbid': [],
         'head': {}, 'declared': {}, 'clauses': {}, 'b_clauses': [],
         'blind': None, 'spec_doms': [], 'spec_modes': []}

    for head, body in secs.items():
        m = re.match(r'^(必須整章判空的章|必須判空的錨點|必須命中且必含指定領域的錨點'
                     r'|必須非空的錨點)（(\d+) ([章段])(?:\s*(\d+) 段)?', head)
        if m:
            s['head'][m.group(1)] = int(m.group(2))
            if m.group(4):
                s['head'][m.group(1) + '.段'] = int(m.group(4))

        if head.startswith('必須整章判空的章'):
            for line in body.split('\n'):
                m = re.match(r'^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*(b\d\d)\s*\|'
                             r'\s*(G\d)\s*\|', line)
                if m:
                    s['empty_ch'].append((m.group(1), int(m.group(2)),
                                          m.group(3), m.group(4)))
            m = re.search(r'這 (\d+) 段的 `modes` 必須含 `(\w+)`', body)
            if m:
                s['declared']['empty_ch_modes_sec'] = (int(m.group(1)), m.group(2))
        elif head.startswith('必須判空的錨點'):
            for line in body.split('\n'):
                m = re.match(r'^\|\s*`([^`]+)`\[(\d+)\]\s*\|\s*(.*?)\s*\|\s*(b\d\d)\s*\|'
                             r'\s*(.*?)\s*\|\s*$', line)
                if m:
                    s['empty'].append((m.group(1), int(m.group(2)), m.group(4),
                                       m.group(3), m.group(5)))
            m = re.search(r'判空錨點合計 (\d+) ＋ (\d+) ＝ (\d+) 段', body)
            if m:
                s['declared']['empty_sum'] = tuple(int(m.group(i)) for i in (1, 2, 3))
        elif head.startswith('必須命中且必含'):
            for sub in re.split(r'^### ', body, flags=re.M)[1:]:
                title = sub.split('\n', 1)[0].strip()
                mt = re.search(r'（(\d+) 段(?:，必含 \*?\*?([IVX]+)\*?\*?)?）', title)
                rows = []
                for line in sub.split('\n'):
                    m = re.match(r'^\|\s*`([^`]+)`\[(\d+)\]\s*\|\s*(.*?)\s*\|'
                                 r'\s*(b\d\d)\s*\|\s*(.*?)\s*\|\s*$', line)
                    if m:
                        rows.append((m.group(1), int(m.group(2)), m.group(4),
                                     m.group(3), m.group(5)))
                s['hit_subs'].append((title, int(mt.group(1)) if mt else None,
                                      mt.group(2) if mt else None, rows))
                s['hit'] += rows
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
                        s['gray'].append((mm.group(1), int(mm.group(2)), mm.group(3)))
        elif head.startswith('13 個領域'):
            s['spec_doms'] = [x for x in re.findall(r'^\|\s*([IVX]+)\s*\|', body, re.M)]
            s['id_forbid'] += [x for x in re.findall(r'`([\w-]+)`[、，]?', body)
                               if '-' in x]
        elif head.startswith('8 個 discourse_mode'):
            s['spec_modes'] = re.findall(r'^\|\s*`(\w+)`\s*\|', body, re.M)
            m = re.search(r'`modes` 不要疊到([一二三四五六七八九十]+)個以上', body)
            if m:
                s['declared']['mode_cap'] = CN_NUM.get(m.group(1))
        elif head.startswith('硬規則'):
            m = re.search(r'不得標到([一二三四五六七八九十]+)個', body)
            if m:
                s['declared']['hard_max_dom'] = CN_NUM.get(m.group(1))
        elif head.startswith('驗收條件'):
            _parse_accept(s, body)
        elif head.startswith('閘門'):
            for sub in re.split(r'^### ', body, flags=re.M)[1:]:
                title = sub.split('\n', 1)[0]
                m = re.match(r'^(G\d)[^（]*（(\d+) 章 (\d+) 段，'
                             r'(b\d\d(?:[–\-]b\d\d)?)）', title)
                if m:
                    s['gate'].append((m.group(1), int(m.group(2)), int(m.group(3)),
                                      _batch_range(m.group(4))))
                mg = re.match(r'^(G\d)', title)
                if mg:
                    s['gate_chapters'][mg.group(1)] = re.findall(r'〈([^〉]+)〉', sub)

    # 批次表 | b01 | G1 | 7 | 30 | 親士 修身 … |（比呂覽多一個「群」欄）
    for line in spec.split('\n'):
        m = re.match(r'^\|\s*(b\d\d)\s*\|\s*(G\d)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|'
                     r'\s*(.+?)\s*\|\s*$', line)
        if m:
            s['batch_table'].append((m.group(1), m.group(2), int(m.group(3)),
                                     int(m.group(4)), m.group(5).split()))
    # 五群表 | **G1 前期雜論** | … | 7 章 30 段 | b01 | … |
    for line in spec.split('\n'):
        m = re.match(r'^\|\s*\*\*(G\d)[^|]*\|[^|]*\|\s*(\d+) 章 (\d+) 段\s*\|'
                     r'\s*([^|]+?)\s*\|', line)
        if m:
            s['group_table'].append((m.group(1), int(m.group(2)), int(m.group(3)),
                                     _batch_range(m.group(4))))
    m = re.search(r'全書 (\d+) 章 (\d+) 段 ([\d,]+) 字', spec)
    if m:
        s['declared']['book'] = (int(m.group(1)), int(m.group(2)), _num(m.group(3)))
    m = re.search(r'《墨子》現存 (\d+) 篇', spec)
    if m:
        s['declared']['pian'] = int(m.group(1))

    # 表格「為什麼」欄裡的「不得含／填／讀成 X」——條文沒接住的一律回報
    for ch, idx, _b, _q, cell in s['empty'] + s['hit']:
        for mm in re.finditer(r'不得(?:含|填|讀成) ([IVX]+(?:[／/＋+][IVX]+)*)', cell):
            for d in _dom_list(mm.group(1)):
                s['table_forbid'].append((ch, idx, d))

    # 全文的 `章`[n]「逐字引句」——配套散文裡的引句一樣要對拍
    s['prose_quotes'] = [(m.group(1), int(m.group(2)), m.group(3))
                         for m in QUOTED.finditer(spec)]
    s['prose_refs'] = _refs(spec)
    return s


def _split_xii(text):
    """「G5 全 11 章 82 段（`備城門` …）、`明鬼下`[2]、`小取`[10]」→ token 串。"""
    toks = []
    body = text.split('\n\n')[1] if '\n\n' in text else text
    body = re.sub(r'^#.*$', '', body, flags=re.M).replace('*', '')
    for part in re.split(r'[、。]', body):
        part = part.strip()
        if not part:
            continue
        m = re.match(r'^(?:含\s*)?(G\d) 全 (?:(\d+) 章 )?(\d+) 段(?:（(.*)）)?$', part)
        if m:
            toks.append(('group', m.group(1),
                         int(m.group(2)) if m.group(2) else None, int(m.group(3)),
                         re.findall(r'`([^`]+)`', m.group(4) or '')))
            continue
        m = re.match(r'^(?:含\s*)?`([^`]+)` 全 (\d+) 段$', part)
        if m:
            toks.append(('chapter', m.group(1), int(m.group(2))))
            continue
        m = re.match(r'^(?:含\s*)?`([^`]+)`\[(\d+)\][–\-]\[(\d+)\]$', part)
        if m:
            toks.append(('range', m.group(1), int(m.group(2)), int(m.group(3))))
            continue
        m = re.match(r'^(?:含\s*)?`([^`]+)`((?:\[\d+\])+)$', part)
        if m:
            for i in re.findall(r'\[(\d+)\]', m.group(2)):
                toks.append(('para', m.group(1), int(i)))
            continue
        if '`' in part or re.search(r'\bG\d\b', part):
            toks.append(('!', part[:28]))
    return toks


def _parse_polarity(no, txt):
    """A10–A14：「`X`[a] 非空；`Y`[b]`Y`[c] 判空」→ [(no, 章, 段, 極性)]。
    先剝 （…）——A11 的括號裡既有 `；` 又有一個裸章名，不剝會解錯。"""
    out = []
    txt = re.sub(r'（[^）]*）', '', txt).replace('*', '')
    for part in txt.split('；'):
        pol = '非空' if '非空' in part else ('判空' if '判空' in part else None)
        if pol is None:
            continue
        for ch, idx in _refs(part):
            out.append((no, ch, idx, pol))
    return out


def _parse_forbid(no, txt):
    """A15–A17：「`X`[a] 不含 III＋IV；`Y`[b] 不含 IV」→ [(no, 章, 段, 領域)]。"""
    out = []
    txt = re.sub(r'（[^）]*）', '', txt).replace('*', '')
    for part in txt.split('；'):
        if '不含' not in part:
            continue
        head, tail = part.split('不含', 1)
        for ch, idx in _refs(head):
            for d in _dom_list(tail):
                out.append((no, ch, idx, d))
    return out


def _parse_accept(s, body):
    """A 類 19 條逐條現場解析；解不出東西的條款會在 --check-spec 被點名。"""
    d = s['declared']
    abody, bbody = body, ''
    if '### B 類' in body:
        abody, bbody = body.split('### B 類', 1)
    for m in re.finditer(r'^(\d+)\. (.*)$', abody, flags=re.M):
        s['clauses'][int(m.group(1))] = m.group(2)
    c = s['clauses']

    t = c.get(1, '')
    for m in re.finditer(r'(b\d\d) (\d+)', t):
        d.setdefault('rows', {})[m.group(1)] = int(m.group(2))
    m = re.search(r'合計 (\d+)', t)
    if m:
        d['total'] = int(m.group(1))

    t = c.get(2, '')
    m = re.search(r'「必須整章判空」的 (\d+) 章共 (\d+) 段', t)
    if m:
        d['empty_ch'] = (int(m.group(1)), int(m.group(2)))
    d['empty_ch_rows'] = [(x, int(y)) for x, y in
                          re.findall(r'`([^`]+)` (\d+)', re.sub(r'^[^（]*', '', t))]

    m = re.search(r'這 (\d+) 段的 `modes` 全部含 `(\w+)`', c.get(3, ''))
    if m:
        d['empty_ch_modes'] = (int(m.group(1)), m.group(2))

    t = c.get(4, '')
    m = re.search(r'「必須判空」的 (\d+) 段', t)
    if m:
        d['empty'] = int(m.group(1))
    m = re.search(r'判空錨點合計 (\d+) 段', t)
    if m:
        d['empty_total'] = int(m.group(1))
    d['zero_overlap'] = '零重疊' in t

    m = re.search(r'「必須命中且必含指定領域」的 (\d+) 段', c.get(5, ''))
    if m:
        d['hit'] = int(m.group(1))

    t = c.get(6, '')
    refs6 = _refs(t)
    if refs6 and '含' in t:
        s['a6'] = (refs6[0][0], refs6[0][1], _dom_list(t.split('含', 1)[1]))

    for part in re.sub(r'（[^）]*）', '', c.get(7, '')).replace('*', '').split('；'):
        if '含' not in part:
            continue
        if '不含' in part:
            head, forb = part.split('不含', 1)
        else:
            head, forb = part, ''
        refs = _refs(head)
        if refs and '含' in head:
            s['a7'].append((refs[0][0], refs[0][1],
                            _dom_list(head.split('含', 1)[1]), _dom_list(forb)))

    m = re.search(r'「必須非空」的 (\d+) 段', c.get(8, ''))
    if m:
        d['nonempty'] = int(m.group(1))

    m = re.search(r'一律不含 XII\*\*，含(.*)$', c.get(9, ''))
    s['a9_tokens'] = _split_xii(m.group(1)) if m else []

    for no in (10, 11, 12, 13, 14):
        s['polarity'] += _parse_polarity(no, c.get(no, ''))
    for no in (15, 16, 17):
        s['forbid_dom'] += _parse_forbid(no, c.get(no, ''))

    s['zero_modes'] = re.findall(r'`(\w+)` 全書 (?:0|零) 段', c.get(18, ''))

    t = c.get(19, '')
    s['id_forbid'] += [x for x in re.findall(r'`([\w-]+)`', t) if '-' in x]
    m = re.search(r'`domains` 長度 ≤ (\d+)', t)
    if m:
        s['max_dom'] = int(m.group(1))

    # B 類：以 `；` 切；G4 那條把兩個預期用 `，` 併在一行，帶著群號往後傳
    for line in bbody.split('\n'):
        if not line.startswith('- '):
            continue
        if '盲測' in line:
            continue
        body_line = re.sub(r'（[^）]*）', '', line[2:].strip())
        g = None
        for frag in body_line.split('；'):
            mg = re.search(r'(?<![A-Za-z])G(\d)(?!\d)', frag)
            if mg:
                g = 'G' + mg.group(1)
            parts = [frag]
            if frag.count('預期') > 1:
                parts = [p for p in frag.split('，') if '預期' in p]
            for p in parts:
                s['b_clauses'].append((p.strip(), g))
    m = re.search(r'`([^`]+)`\[(\d+)\]（(b\d\d)）與 `([^`]+)`\[(\d+)\]（(b\d\d)）'
                  r'相似度 ([\d.]+)，是全書唯一通過 ≥([\d.]+) 門檻', bbody)
    if m:
        s['blind'] = {'a': (m.group(1), int(m.group(2))), 'ab': m.group(3),
                      'b': (m.group(4), int(m.group(5))), 'bb': m.group(6),
                      'ratio': float(m.group(7)), 'thr': float(m.group(8))}
        mm = re.search(r'相似度 ([\d.]+)[–\-]([\d.]+)', bbody)
        if mm:
            s['blind']['band'] = (float(mm.group(1)), float(mm.group(2)))


def parse_req(cell):
    """「V 或 VII（說辭側，**不得含 XII**）」→ ('or', ['V','VII'], ['XII'])。
    `不得含` 一定要在剝 （…） 之前撈——好幾條的禁令就寫在括號裡。"""
    forbid = []
    for m in re.finditer(r'不得含 ([IVX]+(?:[／/＋+][IVX]+)*)', cell):
        forbid += _dom_list(m.group(1))
    body = re.sub(r'（[^）]*）', '', cell).replace('*', '')
    body = re.sub(r'，?且?不得含 [IVX／/＋+]+', '', body).strip()
    toks = _dom_list(body)
    mode = 'and' if ('＋' in body or '+' in body) else 'or'
    return mode, toks, forbid


def group_map(s, chapter_len):
    """章 → 體例群：批次表給 批→群，批次檔給 章→批。零手抄章名。"""
    b2g = {b: g for b, g, _c, _p, _n in s['batch_table']}
    return {c: b2g.get(v[0]) for c, v in chapter_len.items()}


def expand_xii(toks, gmap, chapter_len):
    """XII 禁用 token 串展開成 (章, 段) 集合；順便回報解不開或對不上的 token。"""
    keys, bad = set(), []
    for t in toks:
        if t[0] == 'group':
            _k, g, n_ch, n_para, names = t
            members = [c for c in chapter_len if gmap.get(c) == g]
            tot = sum(chapter_len[c][1] for c in members)
            if n_ch is not None and len(members) != n_ch:
                bad.append('%s 宣告 %d 章，依批次表歸群實得 %d 章' % (g, n_ch, len(members)))
            if tot != n_para:
                bad.append('%s 宣告 %d 段，依批次表歸群實得 %d 段' % (g, n_para, tot))
            if names and set(names) != set(members):
                bad.append('%s 括號內章名與歸群結果不符，差：%s'
                           % (g, sorted(set(names) ^ set(members))))
            for c in members:
                keys |= {(c, i) for i in range(1, chapter_len[c][1] + 1)}
        elif t[0] == 'chapter':
            _k, c, n = t
            if c not in chapter_len:
                bad.append('章不存在：%s' % c)
            else:
                if chapter_len[c][1] != n:
                    bad.append('%s 宣告 %d 段，實際 %d 段' % (c, n, chapter_len[c][1]))
                keys |= {(c, i) for i in range(1, chapter_len[c][1] + 1)}
        elif t[0] == 'range':
            keys |= {(t[1], i) for i in range(t[2], t[3] + 1)}
        elif t[0] == 'para':
            keys.add((t[1], t[2]))
        else:
            bad.append('無法解析的 token：%s' % t[1])
    return keys, bad


def all_forbid_xii(s, gmap, chapter_len):
    """A9 的清單 ＋ 任何表格儲存格自己寫了「不得含 XII」的段。"""
    keys, _bad = expand_xii(s['xii_tokens'], gmap, chapter_len)
    for ch, idx, _b, _q, cell in s['hit'] + s['empty']:
        if 'XII' in parse_req(cell)[2]:
            keys.add((ch, idx))
    return keys


# ---------------------------------------------------------------- 相似度

def _bigrams(t):
    return set(t[i:i + 2] for i in range(len(t) - 1))


def similar_pairs(paras, thr):
    """全書跨批兩兩掃描；先用 bigram Jaccard 粗篩再算 difflib ratio。"""
    items = [(k, v[0], v[1], _bigrams(v[1])) for k, v in sorted(paras.items())]
    out = []
    for i in range(len(items)):
        ka, ba, ta, ga = items[i]
        if not ga:
            continue
        for j in range(i + 1, len(items)):
            kb, bb, tb, gb = items[j]
            if ba == bb or not gb:
                continue
            inter = len(ga & gb)
            if not inter or inter / float(len(ga | gb)) < 0.12:
                continue
            r = difflib.SequenceMatcher(None, ta, tb).ratio()
            if r >= thr:
                out.append((r, ka, ba, kb, bb))
    out.sort(reverse=True)
    return out


# ---------------------------------------------------------------- 發包前自檢

def check_spec():
    """只拿 SPEC.md 對批次檔，發包前跑。FAIL 擋發包，NOTE 是我自己要裁定的落差。"""
    paras, chapter_len, batch_chapters, header_bad = read_batches()
    s = parse_spec()
    d = s['declared']
    F, N = [], []
    gmap = group_map(s, chapter_len)
    text_all = ''.join(v[1] for v in paras.values())

    # ---- S0 批次檔自身
    for x in header_bad:
        F.append('S0 批次檔 %s' % x)

    # ---- S1 條文宣告 vs 表格列數 vs 章節標題
    pairs = [('必須整章判空的章', len(s['empty_ch']), '章'),
             ('必須判空的錨點', len(s['empty']), '段'),
             ('必須命中且必含指定領域的錨點', len(s['hit']), '段'),
             ('必須非空的錨點', len(s['nonempty']), '段')]
    for name, got, unit in pairs:
        want = s['head'].get(name)
        if want is not None and want != got:
            F.append('S1 節標題「%s」寫 %d %s，表格實際 %d 列' % (name, want, unit, got))
    if s['head'].get('必須整章判空的章.段') != sum(x[1] for x in s['empty_ch']):
        F.append('S1 節標題「必須整章判空的章」寫 %s 段，表格段數欄合計 %d'
                 % (s['head'].get('必須整章判空的章.段'), sum(x[1] for x in s['empty_ch'])))
    for key, got, label in [('empty_ch', len(s['empty_ch']), 'A2 章數'),
                            ('empty', len(s['empty']), 'A4 判空段數'),
                            ('hit', len(s['hit']), 'A5 命中段數'),
                            ('nonempty', len(s['nonempty']), 'A8 非空段數')]:
        v = d.get(key)
        v = v[0] if isinstance(v, tuple) else v
        if v is not None and v != got:
            F.append('S1 %s 條文宣告 %d，表格實際 %d' % (label, v, got))
    if d.get('empty_ch') and d['empty_ch'][1] != sum(x[1] for x in s['empty_ch']):
        F.append('S1 A2 條文宣告共 %d 段，表格段數欄合計 %d'
                 % (d['empty_ch'][1], sum(x[1] for x in s['empty_ch'])))
    if d.get('empty_ch_rows') and d['empty_ch_rows'] != [(x[0], x[1]) for x in s['empty_ch']]:
        F.append('S1 A2 括號內逐章段數 %s 與表格 %s 不符'
                 % (d['empty_ch_rows'], [(x[0], x[1]) for x in s['empty_ch']]))
    for key, label in [('empty_ch_modes', 'A3'), ('empty_ch_modes_sec', '整章判空節末')]:
        v = d.get(key)
        if v and v[0] != sum(x[1] for x in s['empty_ch']):
            F.append('S1 %s 宣告 %d 段含 `%s`，整章判空表實際 %d 段'
                     % (label, v[0], v[1], sum(x[1] for x in s['empty_ch'])))
    if d.get('empty_ch_modes') and d.get('empty_ch_modes_sec') \
            and d['empty_ch_modes'][1] != d['empty_ch_modes_sec'][1]:
        F.append('S1 A3 與整章判空節末指定的 mode 不同：%s vs %s'
                 % (d['empty_ch_modes'][1], d['empty_ch_modes_sec'][1]))
    tot_empty = sum(x[1] for x in s['empty_ch']) + len(s['empty'])
    for key, label in [('empty_total', 'A4'), ('empty_sum', '判空表節末')]:
        v = d.get(key)
        v = v[2] if isinstance(v, tuple) else v
        if v is not None and v != tot_empty:
            F.append('S1 %s 宣告判空錨點合計 %d 段，兩表實際 %d 段' % (label, v, tot_empty))
    if isinstance(d.get('empty_sum'), tuple):
        a, b, _c = d['empty_sum']
        if a != sum(x[1] for x in s['empty_ch']) or b != len(s['empty']):
            F.append('S1 判空表節末寫 %d ＋ %d，兩表實際 %d ＋ %d'
                     % (a, b, sum(x[1] for x in s['empty_ch']), len(s['empty'])))
    if d.get('gray') is not None and d['gray'] != len(s['gray']):
        F.append('S1 灰區宣告 %d 段，實際列出 %d 條' % (d['gray'], len(s['gray'])))

    # ---- S2 批次表 vs 批次檔
    if len(s['batch_table']) != len(batch_chapters):
        F.append('S2 批次表 %d 列，批次檔 %d 個' % (len(s['batch_table']), len(batch_chapters)))
    seen_b = set()
    for b, g, nch, npara, names in s['batch_table']:
        seen_b.add(b)
        if b not in batch_chapters:
            F.append('S2 批次表有 %s 但找不到 %s.md' % (b, b))
            continue
        real = batch_chapters[b]
        if names != real:
            F.append('S2 %s 章名或順序不符\n      SPEC：%s\n      實際：%s'
                     % (b, ' '.join(names), ' '.join(real)))
        if nch != len(real):
            F.append('S2 %s 章數宣告 %d，實際 %d' % (b, nch, len(real)))
        rp = sum(chapter_len[c][1] for c in real)
        if npara != rp:
            F.append('S2 %s 段數宣告 %d，實際 %d' % (b, npara, rp))
        if d.get('rows', {}).get(b) not in (None, npara):
            F.append('S2 A1 條文寫 %s %d 段，批次表寫 %d'
                     % (b, d['rows'][b], npara))
        if d.get('rows', {}).get(b) not in (None, rp):
            F.append('S2 A1 條文寫 %s %d 段，批次檔實際 %d 段' % (b, d['rows'][b], rp))
    for b in batch_chapters:
        if b not in seen_b:
            F.append('S2 %s.md 存在但批次表沒列' % b)
    if d.get('total') is not None and d['total'] != len(paras):
        F.append('S2 A1 合計 %d 段，批次檔實際 %d 段' % (d['total'], len(paras)))

    # ---- S3 五群表／閘門標題／批次表三方對拍
    gt = {g: (nc, np, bs) for g, nc, np, bs in s['group_table']}
    gate = {g: (nc, np, bs) for g, nc, np, bs in s['gate']}
    b2g = {b: g for b, g, _c, _p, _n in s['batch_table']}
    for g in sorted(set(list(gt) + list(gate))):
        members = sorted([c for c in chapter_len if gmap.get(c) == g])
        real = (len(members), sum(chapter_len[c][1] for c in members),
                sorted({chapter_len[c][0] for c in members}))
        for src, tbl in (('五群表', gt), ('閘門標題', gate)):
            if g not in tbl:
                F.append('S3 %s 缺 %s' % (src, g))
                continue
            nc, np, bs = tbl[g]
            if (nc, np) != real[:2]:
                F.append('S3 %s %s 宣告 %d 章 %d 段，依批次表歸群實得 %d 章 %d 段'
                         % (src, g, nc, np, real[0], real[1]))
            if sorted(bs or []) != real[2]:
                F.append('S3 %s %s 批次欄 %s，實際涵蓋 %s'
                         % (src, g, bs, real[2]))
    for b in sorted(batch_chapters):
        gs = {gmap.get(c) for c in batch_chapters[b]}
        if len(gs) != 1 or None in gs:
            F.append('S3 %s 跨群或無群：%s' % (b, gs))
    if d.get('book'):
        nc, np, nz = d['book']
        real = (len(chapter_len), len(paras), len(text_all))
        if (nc, np, nz) != real:
            F.append('S3 全書宣告 %d 章 %d 段 %d 字，實際 %d 章 %d 段 %d 字'
                     % (nc, np, nz, real[0], real[1], real[2]))
    if d.get('pian') is not None and d['pian'] != len(chapter_len):
        F.append('S3 「現存 %d 篇」，批次檔實際 %d 章' % (d['pian'], len(chapter_len)))

    # ---- S4 整章判空表
    for ch, n, b, g in s['empty_ch']:
        if ch not in chapter_len:
            F.append('S4 整章判空表章不存在：%s' % ch)
            continue
        if chapter_len[ch][1] != n:
            F.append('S4 %s 段數欄 %d，實際 %d 段' % (ch, n, chapter_len[ch][1]))
        if chapter_len[ch][0] != b:
            F.append('S4 %s 批欄 %s，實際在 %s' % (ch, b, chapter_len[ch][0]))
        if gmap.get(ch) != g:
            F.append('S4 %s 群欄 %s，依批次表歸群為 %s' % (ch, g, gmap.get(ch)))

    # ---- S5 三張逐段錨點表：章、段號、批次歸屬、逐字引句
    def rowchk(tag, ch, idx, batch, quote):
        if ch not in chapter_len:
            F.append('S5 %s 章不存在：%s' % (tag, ch))
            return
        if (ch, idx) not in paras:
            F.append('S5 %s %s[%d] 超出範圍（該章 %d 段）' % (tag, ch, idx, chapter_len[ch][1]))
            return
        if batch and chapter_len[ch][0] != batch:
            F.append('S5 %s %s[%d] 批欄 %s，實際在 %s'
                     % (tag, ch, idx, batch, chapter_len[ch][0]))
        for q in _quotes(quote or ''):
            if not quote_ok(q, paras[(ch, idx)][1]):
                F.append('S5 %s %s[%d] 引句對不上原文：%s' % (tag, ch, idx, q[:30]))

    for ch, idx, b, q, _cell in s['empty']:
        rowchk('判空表', ch, idx, b, q)
    for ch, idx, b, q, _cell in s['hit']:
        rowchk('命中表', ch, idx, b, q)
    for ch, idx, b, rest in s['nonempty']:
        rowchk('非空表', ch, idx, b, rest)
    for ch, idx, q in s['gray']:
        rowchk('灰區', ch, idx, None, '「%s」' % q)

    # ---- S6 四表互斥與零重疊宣告
    ech_keys = set()
    for ch, _n, _b, _g in s['empty_ch']:
        ech_keys |= {(ch, i) for i in range(1, chapter_len.get(ch, ('', 0))[1] + 1)}
    tbl = [('整章判空', ech_keys),
           ('判空表', {(c, i) for c, i, _b, _q, _x in s['empty']}),
           ('命中表', {(c, i) for c, i, _b, _q, _x in s['hit']}),
           ('非空表', {(c, i) for c, i, _b, _r in s['nonempty']}),
           ('灰區', {(c, i) for c, i, _q in s['gray']})]
    for i in range(len(tbl)):
        for j in range(i + 1, len(tbl)):
            both = tbl[i][1] & tbl[j][1]
            if both:
                F.append('S6 %s 與 %s 重疊 %d 段：%s'
                         % (tbl[i][0], tbl[j][0], len(both), sorted(both)[:5]))
    if d.get('zero_overlap') and (tbl[0][1] & tbl[1][1]):
        F.append('S6 A4 宣告與第 2 條零重疊，實際有交集')
    for name, rows in [('判空表', [(c, i) for c, i, _b, _q, _x in s['empty']]),
                       ('命中表', [(c, i) for c, i, _b, _q, _x in s['hit']]),
                       ('非空表', [(c, i) for c, i, _b, _r in s['nonempty']])]:
        dup = sorted({k for k in rows if rows.count(k) > 1})
        if dup:
            F.append('S6 %s 自身重複列：%s' % (name, dup))

    # ---- S7 配套散文裡的段落引用與引句
    anchor_keys = set().union(*[t[1] for t in tbl])
    for ch, idx in set(s['prose_refs']):
        if ch not in chapter_len:
            continue
        if (ch, idx) not in paras:
            F.append('S7 散文引用 %s[%d] 超出範圍（該章 %d 段）'
                     % (ch, idx, chapter_len[ch][1]))
    for ch, idx, q in s['prose_quotes']:
        if (ch, idx) in paras and not quote_ok(q, paras[(ch, idx)][1]):
            F.append('S7 散文引句對不上原文 %s[%d]：%s' % (ch, idx, q[:30]))

    # ---- S8 命中表儲存格
    for title, want, forced, rows in s['hit_subs']:
        if want is not None and want != len(rows):
            F.append('S8 子表「%s」標題寫 %d 段，實際 %d 列' % (title, want, len(rows)))
        for ch, idx, _b, _q, cell in rows:
            mode, need, forbid = parse_req(cell)
            if not need:
                F.append('S8 %s[%d]「必須含」欄解不出領域：%s' % (ch, idx, cell[:30]))
            for x in need + forbid:
                if x not in DOMS:
                    F.append('S8 %s[%d] 出現非法領域 id %s' % (ch, idx, x))
            if forced and forced not in need:
                F.append('S8 子表「%s」宣告必含 %s，但 %s[%d] 的欄位是 %s'
                         % (title, forced, ch, idx, need))
            if set(need) & set(forbid):
                F.append('S8 %s[%d] 同一格既要求又禁止：%s' % (ch, idx, cell[:40]))
    if d.get('hit') is not None and d['hit'] != sum(len(r) for _t, _w, _f, r in s['hit_subs']):
        F.append('S8 A5 宣告 %d 段，子表列數合計 %d'
                 % (d['hit'], sum(len(r) for _t, _w, _f, r in s['hit_subs'])))

    # ---- S9 XII 禁用清單
    if not s['xii_tokens']:
        F.append('S9 「一格都不得填 XII」清單解析不出任何 token')
    norm = lambda ts: sorted(t[:4] if t[0] == 'group' else t for t in ts)
    if norm(s['xii_tokens']) != norm(s['a9_tokens']):
        F.append('S9 A9 條文的清單與「一格都不得填 XII」節不一致\n'
                 '      節：%s\n      A9：%s' % (norm(s['xii_tokens']), norm(s['a9_tokens'])))
    xii_keys, bad = expand_xii(s['xii_tokens'], gmap, chapter_len)
    for x in bad:
        F.append('S9 %s' % x)
    for ch, idx, _b, _q, cell in s['hit']:
        if (ch, idx) in xii_keys and 'XII' in parse_req(cell)[1]:
            F.append('S9 %s[%d] 在命中表要求 XII，卻也在不得填 XII 的清單裡' % (ch, idx))
    for ch, idx, dom in s['table_forbid']:
        if dom == 'XII' and (ch, idx) not in xii_keys:
            N.append('S9 表格欄寫 %s[%d] 不得含 XII，但不在 A9 清單裡（A9 仍會擋，只是兩處未對齊）'
                     % (ch, idx))

    # ---- S10 A 類條文與四張表交叉
    empty_all = tbl[0][1] | tbl[1][1]
    hit_keys, nonempty_keys = tbl[2][1], tbl[3][1]
    for no in range(1, 20):
        if no not in s['clauses']:
            F.append('S10 A%d 條文找不到' % no)
    if not s['a6']:
        F.append('S10 A6 解不出目標')
    else:
        ch, idx, need = s['a6']
        if (ch, idx) not in paras:
            F.append('S10 A6 目標 %s[%d] 不存在' % (ch, idx))
        elif (ch, idx) in empty_all:
            F.append('S10 A6 要求 %s[%d] 含 %s，但它在判空錨點裡' % (ch, idx, need))
        if not need:
            F.append('S10 A6 解不出領域')
    for ch, idx, need, forb in s['a7']:
        if (ch, idx) not in paras:
            F.append('S10 A7 目標 %s[%d] 不存在' % (ch, idx))
        elif (ch, idx) in empty_all:
            F.append('S10 A7 要求 %s[%d] 含 %s，但它在判空錨點裡' % (ch, idx, need))
        if set(need) & set(forb):
            F.append('S10 A7 %s[%d] 既要求又禁止 %s' % (ch, idx, set(need) & set(forb)))
    if len(s['a7']) == 2 and s['a7'][0][:2] == s['a7'][1][:2]:
        F.append('S10 A7 兩側指向同一段，方向護欄失效')
    for no, ch, idx, pol in s['polarity']:
        if (ch, idx) not in paras:
            F.append('S10 A%d 目標 %s[%d] 不存在' % (no, ch, idx))
            continue
        if pol == '判空' and (ch, idx) in (hit_keys | nonempty_keys):
            F.append('S10 A%d 要 %s[%d] 判空，但它在命中／非空表裡' % (no, ch, idx))
        if pol == '非空' and (ch, idx) in empty_all:
            F.append('S10 A%d 要 %s[%d] 非空，但它在判空錨點裡' % (no, ch, idx))
    pol_keys = {}
    for no, ch, idx, pol in s['polarity']:
        if pol_keys.setdefault((ch, idx), pol) != pol:
            F.append('S10 %s[%d] 在 A 類條文裡同時被要求判空與非空' % (ch, idx))
    for no, ch, idx, dom in s['forbid_dom']:
        if (ch, idx) not in paras:
            F.append('S10 A%d 目標 %s[%d] 不存在' % (no, ch, idx))
            continue
        for c2, i2, _b, _q, cell in s['hit']:
            if (c2, i2) == (ch, idx) and dom in parse_req(cell)[1]:
                F.append('S10 A%d 禁 %s[%d] 含 %s，命中表卻要求它含 %s'
                         % (no, ch, idx, dom, dom))
    covered = {(c, i, x) for _n, c, i, x in s['forbid_dom']}
    for ch, idx, dom in s['table_forbid']:
        if dom != 'XII' and (ch, idx, dom) not in covered:
            N.append('S10 表格欄寫 %s[%d] 不得含 %s，A15–A17 沒接住這一條' % (ch, idx, dom))
    if s['max_dom'] is not None and d.get('hard_max_dom') is not None \
            and s['max_dom'] + 1 != d['hard_max_dom']:
        F.append('S10 A19 寫 domains ≤ %d，硬規則寫不得標到 %d 個，兩者不相接'
                 % (s['max_dom'], d['hard_max_dom']))
    if d.get('mode_cap') is not None and d['mode_cap'] != 3:
        N.append('S10 modes 上限提示為 %d，非慣用的 3' % d['mode_cap'])
    for m in s['zero_modes']:
        if m not in MODES:
            F.append('S10 A18 指定的 mode `%s` 不在 8 個 id 裡' % m)
    if sorted(s['spec_doms']) != sorted(DOM_ORDER):
        F.append('S10 SPEC 領域表 %s 與本檔 schema 常數不符' % s['spec_doms'])
    if set(s['spec_modes']) != MODES:
        F.append('S10 SPEC mode 表 %s 與本檔 schema 常數不符' % sorted(s['spec_modes']))
    for x in set(s['id_forbid']):
        if x in DOMS or x in MODES:
            F.append('S10 SPEC 宣告不可出現的 id `%s` 竟在合法清單裡' % x)

    # ---- S11 閘門段落點名的章要落在該群
    for g, names in s['gate_chapters'].items():
        for nm in names:
            if nm in chapter_len and gmap.get(nm) != g:
                F.append('S11 閘門 %s 段點名〈%s〉，但它歸在 %s' % (g, nm, gmap.get(nm)))

    # ---- S12 底本事實
    spec = s['spec']
    for m in re.finditer(r'`(.)` ([\d,]+) 次而 `(.)` \*\*(\d+)\*\* 次', spec):
        for chx, want in ((m.group(1), _num(m.group(2))), (m.group(3), _num(m.group(4)))):
            got = text_all.count(chx)
            if got != want:
                F.append('S12 `%s` 宣告 %d 次，實際 %d 次' % (chx, want, got))
    for m in re.finditer(r'`(.)`（([\d,]+) 處(?:，(\d+) 段)?）', spec):
        chx, want = m.group(1), _num(m.group(2))
        got = text_all.count(chx)
        if got != want:
            F.append('S12 `%s` 宣告 %d 處，實際 %d 處' % (chx, want, got))
        if m.group(3):
            n = len([1 for v in paras.values() if chx in v[1]])
            if n != int(m.group(3)):
                F.append('S12 `%s` 宣告分布 %s 段，實際 %d 段' % (chx, m.group(3), n))
    m = re.search(r'`(.)`（[\d,]+ 處，\d+ 段）與 `(.)`（[\d,]+ 處）[^。]*?分布在((?:〈[^〉]+〉)+)', spec)
    if m:
        want = set(re.findall(r'〈([^〉]+)〉', m.group(3)))
        got = {c for (c, _i), v in paras.items() if m.group(1) in v[1] or m.group(2) in v[1]}
        if want != got:
            F.append('S12 缺字符號分布宣告 %s，實際 %s' % (sorted(want), sorted(got)))
    m = re.search(r'`([〈〉（）〔〕【】]+)` 一個都沒有', spec)
    if m:
        for chx in m.group(1):
            if text_all.count(chx):
                F.append('S12 宣告沒有 `%s`，實際 %d 個' % (chx, text_all.count(chx)))
    m = re.search(r'引號全書只有 `(..)`，沒有 `(..)`', spec)
    if m:
        for chx in m.group(2):
            if text_all.count(chx):
                F.append('S12 宣告沒有 `%s`，實際 %d 個' % (chx, text_all.count(chx)))
        if not text_all.count(m.group(1)[0]):
            F.append('S12 宣告全書有 `%s`，實際 0 個' % m.group(1))

    def _chapter(nm, last):
        if nm in chapter_len:
            return nm, nm
        if last and len(nm) == 1 and last[:-1] + nm in chapter_len:
            return last[:-1] + nm, last[:-1] + nm
        return None, last

    last = None
    for m in re.finditer(r'〈([^〉]+)〉([\d,]+) 字', spec):
        nm, last = _chapter(m.group(1), last)
        if nm is None:
            N.append('S12 〈%s〉N 字：認不出這是哪一章' % m.group(1))
            continue
        got = sum(len(v[1]) for (c, _i), v in paras.items() if c == nm)
        if got != _num(m.group(2)):
            F.append('S12 〈%s〉宣告 %s 字，實際 %d 字' % (nm, m.group(2), got))
    for m in re.finditer(r'〈([^〉]+)〉(\d+) 條', spec):
        nm = m.group(1)
        if nm in chapter_len and chapter_len[nm][1] != int(m.group(2)):
            F.append('S12 〈%s〉宣告 %s 條，實際切出 %d 段' % (nm, m.group(2), chapter_len[nm][1]))
    for m in re.finditer(r'〈([^〉]+)〉三篇 (\d+) 段', spec):
        mem = [c for c in chapter_len if c.startswith(m.group(1)) and c != m.group(1)]
        got = sum(chapter_len[c][1] for c in mem)
        if got != int(m.group(2)):
            F.append('S12 〈%s〉三篇宣告 %s 段，實際 %d 章 %d 段'
                     % (m.group(1), m.group(2), len(mem), got))
    for m in re.finditer(r'〈([^〉]+)〉(\d+) 段', spec):
        nm = m.group(1)
        if nm in chapter_len and chapter_len[nm][1] != int(m.group(2)):
            F.append('S12 〈%s〉宣告 %s 段，實際 %d 段' % (nm, m.group(2), chapter_len[nm][1]))
    m = re.search(r'〈([^〉]+)〉三篇 (\d+) 段與〈([^〉]+)〉(\d+) 段共 (\d+) 段', spec)
    if m and int(m.group(2)) + int(m.group(4)) != int(m.group(5)):
        F.append('S12 %s ＋ %s ≠ 宣告的共 %s 段' % (m.group(2), m.group(4), m.group(5)))
    m = re.search(r'((?:〈[^〉]+〉)+)在傳世本即亡佚', spec)
    if m:
        for nm in re.findall(r'〈([^〉]+)〉', m.group(1)):
            for one in ([nm] if len(nm) <= 3 else
                        [nm[:2] + x for x in nm[2:]]):
                if one in chapter_len:
                    F.append('S12 宣告〈%s〉亡佚，批次檔卻有這一章' % one)
    m = re.search(r'你只會看到((?:〈[^〉]+〉)+)', spec)
    if m:
        for nm in re.findall(r'〈([^〉]+)〉', m.group(1)):
            if nm not in chapter_len:
                F.append('S12 宣告會看到〈%s〉，批次檔沒有這一章' % nm)
    m = re.search(r'各只切出 \*\*(\d+)\*\* 段', spec)
    if m:
        for nm in re.findall(r'〈([^〉]+)〉[\d,]+ 字', spec.split('各只切出')[0][-120:]):
            if nm in chapter_len and chapter_len[nm][1] != int(m.group(1)):
                F.append('S12 宣告〈%s〉只切出 %s 段，實際 %d 段'
                         % (nm, m.group(1), chapter_len[nm][1]))

    # ---- S13 跨批盲測宣稱
    blind = s['blind']
    if blind:
        thr = blind['thr']
        hits = similar_pairs(paras, thr)
        pair = (blind['a'], blind['b'])
        for k in ('a', 'b'):
            ch, idx = blind[k]
            if (ch, idx) not in paras:
                F.append('S13 盲測錨點 %s[%d] 不存在' % (ch, idx))
            elif chapter_len[ch][0] != blind['ab' if k == 'a' else 'bb']:
                F.append('S13 盲測錨點 %s[%d] 批次寫 %s，實際 %s'
                         % (ch, idx, blind['ab' if k == 'a' else 'bb'], chapter_len[ch][0]))
        if blind['a'] in paras and blind['b'] in paras:
            r = difflib.SequenceMatcher(None, paras[blind['a']][1],
                                        paras[blind['b']][1]).ratio()
            if abs(r - blind['ratio']) > 0.005:
                F.append('S13 盲測對子宣告相似度 %.3f，實測 %.3f' % (blind['ratio'], r))
        others = [x for x in hits if (x[1], x[3]) != pair and (x[3], x[1]) != pair]
        if others:
            N.append('S13 SPEC 宣稱這一對是「全書唯一通過 ≥%.2f 門檻」的，實測另有 %d 對達標，'
                     '最高 %.3f（%s[%d]／%s[%d]）——「唯一」不成立'
                     % (thr, len(others), others[0][0], others[0][1][0], others[0][1][1],
                        others[0][3][0], others[0][3][1]))
            for r, ka, ba, kb, bb in others[:12]:
                N.append('      %.3f  %s[%d]（%s） / %s[%d]（%s）'
                         % (r, ka[0], ka[1], ba, kb[0], kb[1], bb))
        if blind.get('band'):
            # 「其餘十論上中下三篇 0.06–0.30」沒寫明是章級還是段級，兩種讀法都量給我看
            lo, hi = blind['band']
            g0 = gmap.get(blind['a'][0])
            trio = sorted([c for c in chapter_len
                           if gmap.get(c) == g0 and c[-1] in '上中下'])
            full = {}
            for c in trio:
                full[c] = ''.join(v[1] for (cc, _i), v in sorted(paras.items()) if cc == c)
            ch_pairs = []
            for i in range(len(trio)):
                for j in range(i + 1, len(trio)):
                    if trio[i][:-1] != trio[j][:-1]:
                        continue
                    ch_pairs.append((difflib.SequenceMatcher(
                        None, full[trio[i]], full[trio[j]]).ratio(), trio[i], trio[j]))
            ch_pairs.sort()
            out_ch = [x for x in ch_pairs if x[0] < lo or x[0] > hi]
            if ch_pairs:
                N.append('S13 章級讀法：同題上中下 %d 對，實測 %.3f–%.3f，%s'
                         % (len(ch_pairs), ch_pairs[0][0], ch_pairs[-1][0],
                            '全落在宣稱的 %.2f–%.2f 內' % (lo, hi) if not out_ch
                            else '有 %d 對落在宣稱的 %.2f–%.2f 之外（最低 %.3f %s／%s）'
                                 % (len(out_ch), lo, hi, out_ch[0][0],
                                    out_ch[0][1], out_ch[0][2])))
            same = []
            for i in range(len(trio)):
                for j in range(i + 1, len(trio)):
                    if trio[i][:-1] != trio[j][:-1]:
                        continue
                    for (c1, i1), (b1, t1) in sorted(paras.items()):
                        if c1 != trio[i]:
                            continue
                        for (c2, i2), (b2, t2) in sorted(paras.items()):
                            if c2 != trio[j] or b1 == b2 or (c1, i1) == blind['a']:
                                continue
                            r = difflib.SequenceMatcher(None, t1, t2).ratio()
                            if r > hi:
                                same.append((r, c1, i1, c2, i2))
            same.sort(reverse=True)
            if same:
                N.append('S13 段級讀法：同題上中下另有 %d 對段落超出宣稱上界 %.2f，'
                         '最高 %.3f（%s[%d]／%s[%d]）——盲測門檻 %.2f 以上的還有 %d 對'
                         % (len(same), hi, same[0][0], same[0][1], same[0][2],
                            same[0][3], same[0][4], thr,
                            len([x for x in same if x[0] >= thr])))
                for r, c1, i1, c2, i2 in same[:5]:
                    N.append('      %.3f  %s[%d] / %s[%d]' % (r, c1, i1, c2, i2))

    # ---- 報告
    print('=== 發包前自檢：SPEC.md vs b01–b%02d.md ===' % len(batch_chapters))
    print('批次 %d／章 %d／段 %d／字 %d' % (len(batch_chapters), len(chapter_len),
                                            len(paras), len(text_all)))
    print('錨點 整章判空 %d 章 %d 段／判空 %d／命中 %d／非空 %d／灰區 %d／不得填 XII %d 段'
          % (len(s['empty_ch']), sum(x[1] for x in s['empty_ch']), len(s['empty']),
             len(s['hit']), len(s['nonempty']), len(s['gray']), len(xii_keys)))
    for g, nc, np, bs in s['group_table']:
        mem = [c for c in chapter_len if gmap.get(c) == g]
        print('  %s %2d 章 %3d 段 %s' % (g, len(mem), sum(chapter_len[c][1] for c in mem),
                                         ' '.join(bs or [])))
    print('A 類條文 %d 條；B 類提示 %d 條' % (len(s['clauses']), len(s['b_clauses'])))
    if N:
        print('--- NOTE %d 條（不擋發包，SPEC 宣稱與實測不符，請自行裁定）---' % len(N))
        for x in N:
            print('  NOTE ' + x)
    if F:
        print('--- FAIL %d 條 ---' % len(F))
        for x in F:
            print('  FAIL ' + x)
        print('=== 自檢未過：%d FAIL / %d NOTE ===' % (len(F), len(N)))
        return 1
    print('=== 自檢 PASS：0 FAIL / %d NOTE ===' % len(N))
    return 0


# ---------------------------------------------------------------- 回收後：A 類

def load_rows(out_dir, want, batch_chapters):
    """讀 out/bNN.json；回傳 (rows, 有讀到的批次, 讀檔層錯誤)。"""
    rows, got, errs = {}, [], []
    if want:
        names = list(want)
    else:
        names = [os.path.basename(p)[:3]
                 for p in sorted(glob.glob(os.path.join(out_dir, 'b[0-9][0-9].json')))]
    for b in names:
        p = os.path.join(out_dir, '%s.json' % b)
        if not os.path.exists(p):
            errs.append('A1 找不到 %s' % os.path.relpath(p, BASE))
            continue
        try:
            obj = json.load(open(p, encoding='utf-8'))
        except Exception as e:
            errs.append('A1 %s.json 不是合法 JSON：%s' % (b, e))
            continue
        if obj.get('batch') not in (None, '%s.md' % b):
            errs.append('A1 %s.json 的 batch 欄寫 %s' % (b, obj.get('batch')))
        got.append(b)
        for r in obj.get('rows', []):
            if not isinstance(r, dict):
                errs.append('A1 %s.json 有一列不是物件' % b)
                continue
            key = (r.get('chapter'), r.get('para_index'))
            if key in rows:
                errs.append('A1 %s[%s] 重複出現' % key)
            rows[key] = dict(r, _batch=b)
    return rows, got, errs


def collect_fails(out_dir, want):
    """A 類 19 條，全部從 SPEC 現場解析的錨點來，回傳完整 FAIL 清單。"""
    paras, chapter_len, batch_chapters, _hb = read_batches()
    s = parse_spec()
    d = s['declared']
    gmap = group_map(s, chapter_len)
    rows, got, fails = load_rows(out_dir, want, batch_chapters)

    def dom(k):
        return list(rows[k].get('domains') or []) if k in rows else None

    def mod(k):
        return list(rows[k].get('modes') or []) if k in rows else None

    # ---- A1 形狀：列數、章名、段號連號、reason
    for b in got:
        mine = {k: v for k, v in rows.items() if v['_batch'] == b}
        chs = batch_chapters.get(b, [])
        want_n = sum(chapter_len[c][1] for c in chs)
        if len(mine) != want_n:
            fails.append('A1 %s rows %d 列，該批應有 %d 段' % (b, len(mine), want_n))
        for c in chs:
            idxs = sorted(i for (cc, i) in mine if cc == c)
            if idxs != list(range(1, chapter_len[c][1] + 1)):
                fails.append('A1 %s %s 的 para_index 不是 1–%d 連號：%s'
                             % (b, c, chapter_len[c][1], idxs))
        for k, r in sorted(mine.items()):
            if k not in paras:
                fails.append('A1 %s 有批次檔沒有的段 %s[%s]' % (b, k[0], k[1]))
            elif paras[k][0] != b:
                fails.append('A1 %s[%s] 應在 %s，卻出現在 %s' % (k[0], k[1], paras[k][0], b))
            if not str(r.get('reason') or '').strip():
                fails.append('A1 %s[%s] 的 reason 是空的' % k)

    # ---- A2／A3 整章判空
    mode_need = (d.get('empty_ch_modes') or d.get('empty_ch_modes_sec') or (0, None))[1]
    for ch, n, _b, _g in s['empty_ch']:
        for i in range(1, chapter_len.get(ch, ('', 0))[1] + 1):
            k = (ch, i)
            if dom(k):
                fails.append('A2 %s[%d] 屬整章判空的章，卻填了 %s' % (ch, i, dom(k)))
            if mode_need and k in rows and mode_need not in (mod(k) or []):
                fails.append('A3 %s[%d] 的 modes 未含 `%s`：%s'
                             % (ch, i, mode_need, mod(k)))

    # ---- A4 判空錨點
    for ch, idx, _b, _q, _cell in s['empty']:
        if dom((ch, idx)):
            fails.append('A4 %s[%d] 是判空錨點，卻填了 %s' % (ch, idx, dom((ch, idx))))

    # ---- A5 命中錨點
    for ch, idx, _b, _q, cell in s['hit']:
        have = dom((ch, idx))
        if have is None:
            continue
        mode, need, forbid = parse_req(cell)
        if mode == 'and':
            miss = [x for x in need if x not in have]
            if miss:
                fails.append('A5 %s[%d] 必含 %s，缺 %s（實得 %s）'
                             % (ch, idx, '＋'.join(need), '＋'.join(miss), have))
        elif need and not set(need) & set(have):
            fails.append('A5 %s[%d] 必含 %s 其一，實得 %s'
                         % (ch, idx, ' 或 '.join(need), have))
        for x in forbid:
            if x in have:
                fails.append('A5 %s[%d] 該格明寫不得含 %s，實得 %s' % (ch, idx, x, have))

    # ---- A6／A7 條文層的單段要求
    if s['a6']:
        ch, idx, need = s['a6']
        have = dom((ch, idx))
        if have is not None:
            miss = [x for x in need if x not in have]
            if miss:
                fails.append('A6 %s[%d] 必含 %s，缺 %s（實得 %s）'
                             % (ch, idx, '＋'.join(need), '＋'.join(miss), have))
    for ch, idx, need, forb in s['a7']:
        have = dom((ch, idx))
        if have is None:
            continue
        miss = [x for x in need if x not in have]
        if miss:
            fails.append('A7 %s[%d] 必含 %s，缺 %s（實得 %s）'
                         % (ch, idx, '＋'.join(need), '＋'.join(miss), have))
        bad = [x for x in forb if x in have]
        if bad:
            fails.append('A7 %s[%d] 不得含 %s，實得 %s' % (ch, idx, '＋'.join(bad), have))

    # ---- A8 非空錨點
    for ch, idx, _b, _r in s['nonempty']:
        have = dom((ch, idx))
        if have is not None and not have:
            fails.append('A8 %s[%d] 是非空錨點，domains 卻是空的' % (ch, idx))

    # ---- A9 不得填 XII
    for ch, idx in sorted(all_forbid_xii(s, gmap, chapter_len)):
        have = dom((ch, idx))
        if have and 'XII' in have:
            fails.append('A9 %s[%d] 在不得填 XII 的清單裡，實得 %s' % (ch, idx, have))

    # ---- A10–A14 同章判反方向
    for no, ch, idx, pol in s['polarity']:
        have = dom((ch, idx))
        if have is None:
            continue
        if pol == '判空' and have:
            fails.append('A%d %s[%d] 條文要求判空，實得 %s' % (no, ch, idx, have))
        if pol == '非空' and not have:
            fails.append('A%d %s[%d] 條文要求非空，實得空' % (no, ch, idx))

    # ---- A15–A17 條文層禁用領域（同一段只響一次，把犯的格一起列）
    bucket = {}
    for no, ch, idx, x in s['forbid_dom']:
        bucket.setdefault((no, ch, idx), []).append(x)
    for (no, ch, idx), doms in sorted(bucket.items()):
        have = dom((ch, idx))
        if have is None:
            continue
        bad = [x for x in doms if x in have]
        if bad:
            fails.append('A%d %s[%d] 不得含 %s，實得 %s'
                         % (no, ch, idx, '＋'.join(bad), have))

    # ---- A18 全書零段的 mode
    for m in s['zero_modes']:
        bad = sorted(k for k in rows if m in (mod(k) or []))
        if bad:
            fails.append('A18 `%s` 應全書 0 段，實得 %d 段：%s'
                         % (m, len(bad), ['%s[%s]' % x for x in bad[:5]]))

    # ---- A19 id 合法性與 domains 長度
    cap = s['max_dom']
    for k in sorted(rows):
        have, ms = dom(k) or [], mod(k) or []
        for x in have:
            if x not in DOMS:
                fails.append('A19 %s[%s] domains 出現非法 id `%s`' % (k[0], k[1], x))
        for x in ms:
            if x not in MODES:
                fails.append('A19 %s[%s] modes 出現非法 id `%s`' % (k[0], k[1], x))
        if cap is not None and len(have) > cap:
            fails.append('A19 %s[%s] domains %d 格，上限 %d：%s'
                         % (k[0], k[1], len(have), cap, have))
    return {'rows': rows, 'batches': got, 'fails': fails,
            'spec': s, 'paras': paras, 'chapter_len': chapter_len,
            'batch_chapters': batch_chapters, 'gmap': gmap}


# ---------------------------------------------------------------- 回收後：B 類

def _bound(txt):
    m = re.search(r'(\d+)\s*[–\-]\s*(\d+)\s*(%|段|格)', txt)
    if m:
        return int(m.group(1)), int(m.group(2)), m.group(3)
    m = re.search(r'≥\s*(\d+)\s*(%|段|格)', txt)
    if m:
        return int(m.group(1)), None, m.group(2)
    m = re.search(r'≤\s*(\d+)\s*(%|段|格)', txt)
    if m:
        return None, int(m.group(1)), m.group(2)
    return None


def b_report(res):
    """B 類逐條回報實測值與誤差；一律 WARN，不進 fails。"""
    s, rows, gmap = res['spec'], res['rows'], res['gmap']
    chapter_len = res['chapter_len']
    lines = []
    dom_of = {k: list(v.get('domains') or []) for k, v in rows.items()}
    mode_of = {k: list(v.get('modes') or []) for k, v in rows.items()}
    grp = {}
    for k in rows:
        grp.setdefault(gmap.get(k[0]), []).append(k)
    dom_cnt = {x: 0 for x in DOM_ORDER}
    for v in dom_of.values():
        for x in v:
            if x in dom_cnt:
                dom_cnt[x] += 1
    mode_cnt = {}
    for v in mode_of.values():
        for x in v:
            mode_cnt[x] = mode_cnt.get(x, 0) + 1

    def measure(txt, g):
        ks = grp.get(g, []) if g else list(rows)
        if not ks:
            return None, None
        if '命中預期' in txt:
            return _pct(len([k for k in ks if dom_of[k]]), len(ks)), '%'
        if '判空預期' in txt:
            return _pct(len([k for k in ks if not dom_of[k]]), len(ks)), '%'
        if '命中領域預期' in txt:
            return len([x for x in DOM_ORDER if dom_cnt[x]]), '格'
        if '零段' in txt:
            return len([x for x in DOM_ORDER if not dom_cnt[x]]), '格'
        m = re.match(r'^([IVX]+) ', txt)
        if m and m.group(1) in DOMS:
            return dom_cnt[m.group(1)], '段'
        m = re.match(r'^`(\w+)`', txt)
        if m:
            return mode_cnt.get(m.group(1), 0), '段'
        return None, None

    for txt, g in s['b_clauses']:
        val, unit = measure(txt, g)
        bnd = _bound(txt)
        if val is None or not bnd:
            lines.append('WARN 無法自動量化：%s' % txt)
            continue
        lo, hi, u = bnd
        ok = not ((lo is not None and val < lo) or (hi is not None and val > hi))
        # G4 那條的第二個預期被 `，` 切開後不帶群號，補回去才讀得懂實測值算的是誰
        label = txt if (not g or g in txt) else '%s%s' % (g, txt)
        lines.append('%-4s %s ｜ 實測 %d%s'
                     % ('ok' if ok else 'WARN', label, val, unit or u))
    top = sorted(dom_cnt.items(), key=lambda kv: (-kv[1], DOM_ORDER.index(kv[0])))
    lines.append('     領域分布 ' + '／'.join('%s %d' % x for x in top))
    lines.append('     mode 分布 ' + '／'.join(
        '%s %d' % x for x in sorted(mode_cnt.items(), key=lambda kv: -kv[1])))
    for g, nc, np, _bs in s['group_table']:
        ks = grp.get(g, [])
        if ks:
            lines.append('     %s %d/%d 命中 %d%%'
                         % (g, len([k for k in ks if dom_of[k]]), len(ks),
                            _pct(len([k for k in ks if dom_of[k]]), len(ks))))
    b = s['blind']
    if b:
        ka, kb = b['a'], b['b']
        if ka in dom_of and kb in dom_of:
            same = sorted(dom_of[ka]) == sorted(dom_of[kb])
            lines.append('     跨批盲測 %s[%d]=%s ｜ %s[%d]=%s ｜ %s（只記錄）'
                         % (ka[0], ka[1], dom_of[ka], kb[0], kb[1], dom_of[kb],
                            '一致' if same else '不一致'))
        else:
            lines.append('     跨批盲測：兩段不在本次回收範圍內，略過')
    return lines


# ---------------------------------------------------------------- 入口

def run(out_dir, want):
    res = collect_fails(out_dir, want)
    _p, chapter_len, batch_chapters, header_bad = read_batches()
    print('=== 回收驗收：%s ===' % os.path.relpath(out_dir, BASE))
    print('批次 %s（%d 批 %d 列）'
          % (' '.join(res['batches']) or '（無）', len(res['batches']), len(res['rows'])))
    for x in header_bad:
        print('  WARN 批次檔 ' + x)
    if not res['batches']:
        print('=== 沒有可檢查的輸出 ===')
        return 1
    print('--- B 類數量提示（不擋收）---')
    for x in b_report(res):
        print('  ' + x)
    if res['fails']:
        print('--- A 類 FAIL %d 條 ---' % len(res['fails']))
        for x in res['fails']:
            print('  FAIL ' + x)
        print('=== 驗收未過：%d FAIL ===' % len(res['fails']))
        return 1
    print('=== 驗收 PASS：A 類 0 FAIL ===')
    return 0


def main():
    ap = argparse.ArgumentParser(description='墨子標註驗收（A 類硬條件＋B 類數量提示）')
    ap.add_argument('batches', nargs='*', help='要檢查的批次，如 b01 b02；不給就檢查全部已存在的')
    ap.add_argument('--check-spec', action='store_true',
                    help='發包前跑：只拿 SPEC.md 對批次檔自檢，不看 out/')
    ap.add_argument('--out-dir', default=None, help='輸出目錄，預設 delegation/mozi/out')
    args = ap.parse_args()
    if args.check_spec:
        return check_spec()
    out_dir = args.out_dir or os.path.join(BASE, 'out')
    if not os.path.isabs(out_dir):
        # 相對路徑先當工作目錄下解，解不到才回退成 delegation/mozi 底下
        here = os.path.abspath(out_dir)
        out_dir = here if os.path.isdir(here) else os.path.join(BASE, out_dir)
    return run(out_dir, [b[:3] for b in args.batches])


if __name__ == '__main__':
    sys.exit(main())
