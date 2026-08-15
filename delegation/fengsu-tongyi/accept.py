"""風俗通義 A 類驗收（體裁陷阱，硬條件）。

錨點清單一律從 SPEC.md 的兩張表現場解析，不在本檔手抄——孔叢子那次
18 個假 FAIL 的成因就是驗收器自己抄了一份沒被驗證過的清單。

用法：PYTHONIOENCODING=utf-8 python delegation/fengsu-tongyi/accept.py [b06 ...]
不給批次就檢查 out/ 底下所有已存在的批次。
"""
import glob
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DOMS = ['XIII', 'XII', 'XI', 'X', 'IX', 'VIII', 'VII', 'VI', 'V', 'IV', 'III', 'II', 'I']

SHANZE = ['山澤', '五嶽', '四瀆', '林', '麓', '京', '陵', '丘', '墟', '阜', '部', '藪',
          '沛', '陂', '渠', '溝', '洫']
QIWU = ['塤', '笙', '鼓', '磬', '柷', '空侯', '箏', '筑', '缶', '笛', '批把', '竽',
        '簧', '篪', '簫']
FOUR = ['3', '4', '5', '7']


def parse_spec():
    spec = open(os.path.join(BASE, 'SPEC.md'), encoding='utf-8').read()
    sections = re.split(r'^## ', spec, flags=re.M)
    empty, hit = [], []
    for sec in sections:
        target = None
        if sec.startswith('必須判空的錨點'):
            target = empty
        elif sec.startswith('必須命中的錨點'):
            target = hit
        if target is None:
            continue
        for line in sec.split('\n'):
            m = re.match(r'^\|\s*`([^`]+)`\[(\d+)\]\s*\|\s*(.*?)\s*\|\s*(b0\d)\s*\|\s*(.*?)\s*\|\s*$',
                         line)
            if m:
                target.append((m.group(1), int(m.group(2)), m.group(4), m.group(5)))
    return empty, hit


def parse_req(cell):
    """把「必須含」欄解析成 (mode, [domains], forbid_xii)。"""
    forbid = '不得含 XII' in cell
    body = re.sub(r'（[^）]*）', '', cell).replace('*', '').strip()
    toks = [t for t in re.split(r'[^IVX]+', body) if t in DOMS]
    mode = 'and' if ('＋' in body or '+' in body) else 'or'
    return mode, toks, forbid


def main():
    empty, hit = parse_spec()
    print('SPEC 解析：必須判空 %d 段、必須命中 %d 段' % (len(empty), len(hit)))
    if len(empty) != 27 or len(hit) != 52:
        print('!! 解析數與 SPEC 宣告的 27／52 不符，先修驗收器再跑')
        return 2

    want = sys.argv[1:]
    rows = {}
    got_batches = []
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

    fails = []
    skipped = 0

    for ch, idx, batch, why in empty:
        if batch not in got_batches:
            skipped += 1
            continue
        r = rows.get((ch, idx))
        if r is None:
            fails.append('A1 缺段 %s[%d]' % (ch, idx))
        elif r['domains']:
            fails.append('A2 應判空卻命中 %s[%d] → %s' % (ch, idx, r['domains']))

    for ch, idx, batch, cell in hit:
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
            miss = [x for x in need if x not in d]
            if miss:
                fails.append('A3 缺格 %s[%d] 需 %s 全含，實得 %s' % (ch, idx, need, d))
        else:
            if not any(x in d for x in need):
                fails.append('A3 缺格 %s[%d] 需 %s 至少一，實得 %s' % (ch, idx, need, d))
        if forbid and 'XII' in d:
            fails.append('A4 不得含 XII 卻含 %s[%d] → %s' % (ch, idx, d))

    # A5 三段肯定側必含 XII（已在 hit 表以 **XII** 標明，這裡重複把關）
    for key in [('世間多有蛇作怪者', 1), ('世間人家多有見赤白光為變怪者', 1), ('六國', 5)]:
        r = rows.get(key)
        if r is not None and 'XII' not in r['domains']:
            fails.append('A5 肯定側缺 XII %s[%d] → %s' % (key[0], key[1], r['domains']))

    # A6/A7 章群判空下限
    def group(names):
        got = [r for (c, i), r in rows.items() if c in names]
        return got, sum(1 for r in got if not r['domains'])

    sz, sz_empty = group(SHANZE)
    if len(sz) == 23:
        if sz_empty < 19:
            fails.append('A6 山澤章群判空 %d < 19' % sz_empty)
        mu = rows.get(('墟', 1))
        if mu is not None and not mu['domains']:
            fails.append('A6 墟[1] 應命中卻判空')
    qw, qw_empty = group(QIWU)
    if len(qw) == 19 and qw_empty < 14:
        fails.append('A7 器物章群判空 %d < 14' % qw_empty)

    # A8 四篇命中率須明顯高於兩章群
    fr, _ = group(FOUR)
    if len(fr) == 76:
        rate = lambda g: (sum(1 for r in g if r['domains']) / len(g)) if g else None
        r4, rs, rq = rate(fr), rate(sz), rate(qw)
        print('命中率：四篇 %.2f／山澤 %.2f／器物 %.2f' % (r4, rs or 0, rq or 0))
        if rs is not None and r4 <= rs + 0.2:
            fails.append('A8 四篇命中率未明顯高於山澤')
        if rq is not None and r4 <= rq + 0.2:
            fails.append('A8 四篇命中率未明顯高於器物')

    # A9 兩個 mode 全書掛零
    for m in ('worked_instance', 'expression'):
        bad = [(c, i) for (c, i), r in rows.items() if m in r.get('modes', [])]
        if bad:
            fails.append('A9 %s 應 0 段，實得 %d：%s' % (m, len(bad), bad[:5]))

    print('\n跳過（該批未回收）：%d 條錨點' % skipped)
    print('--- A 類 FAIL：%d ---' % len(fails))
    for f in fails:
        print(f)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
