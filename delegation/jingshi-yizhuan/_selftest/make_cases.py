"""合成 accept.py 的反向驗證素材：一份完美輸出、六份各注入一種錯誤的輸出，
以及四份 SPEC 變異副本（用來反證 --check-spec 真的有牙齒）。

驗收器沒被驗過就等於沒有驗收。完美輸出應得 0 FAIL；六份變異各自只改一處，
每處對準一條不同的 A 類條款；四份 SPEC 副本各自破壞一種規格書錯誤型態。

素材全部由 SPEC 現場推導，本檔不手抄章名／段號（同 accept.py 的規矩）。

  PYTHONIOENCODING=utf-8 python delegation/jingshi-yizhuan/_selftest/make_cases.py
"""
import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
sys.path.insert(0, BASE)
import accept  # noqa: E402


# ---------------------------------------------------------------- 完美輸出

def build_perfect():
    """照 SPEC 所有錨點標對：預設判空＋formalization，錨點與 A5／A8 條款逐條覆寫。"""
    paras, chapter_len, batch_chapters, _ = accept.read_batches()
    R = accept.Resolver(chapter_len)
    s = accept.normalize(accept.parse_spec(), R)

    rows = {}
    for (ch, idx), (_batch, text) in paras.items():
        rows[(ch, idx)] = {'chapter': ch, 'para_index': idx, 'domains': [],
                           'modes': ['formalization'],
                           'reason': '「%s」體例欄位登錄，合成測試用' % text[:12]}

    # 命中錨點：取候選格解出的領域（濾掉 A4 全書禁用的那一格）
    for row in s['hit']:
        key = (row['full'], row['idx'])
        need = [d for d in accept.parse_req(row['note']) if d != s['a4_dom']]
        rows[key]['domains'] = need
        rows[key]['modes'] = ['proposition']
        rows[key]['reason'] = '「%s」本段自己說出對人的判斷，合成測試用' % paras[key][1][:12]

    # A5：命中側必須含指定領域
    if s['a5'] and s['a5']['need']:
        for key in s['a5']['hit']:
            if s['a5']['need'] not in rows[key]['domains']:
                rows[key]['domains'].append(s['a5']['need'])

    # A8：目標段 modes 含指定 mode、domains 含指定領域
    if s['a8'] and s['a8']['ref']:
        r = rows[s['a8']['ref']]
        r['modes'] = [s['a8']['mode']]
        if s['a8']['dom'] not in r['domains']:
            r['domains'].insert(0, s['a8']['dom'])

    # 判空錨點與 A5／A6／A7／A8 判空側：明確清空（覆蓋掉上面任何誤設）
    empties = [(row['full'], row['idx']) for row in s['empty']]
    for k in ('a5', 'a6', 'a7'):
        if s[k]:
            empties += s[k]['empty']
    if s['a8']:
        empties += s['a8']['empty']
    for key in empties:
        rows[key]['domains'] = []
    return rows, chapter_len, batch_chapters, s


def write(dirname, rows, batch_chapters):
    d = os.path.join(HERE, dirname)
    os.makedirs(d, exist_ok=True)
    for batch, chs in batch_chapters.items():
        order = {c: n for n, c in enumerate(chs)}
        out = [r for (c, _i), r in
               sorted(rows.items(), key=lambda kv: (order.get(kv[0][0], 99), kv[0][1]))
               if c in order]
        with open(os.path.join(d, '%s.json' % batch), 'w', encoding='utf-8', newline='\n') as f:
            json.dump({'batch': '%s.md' % batch, 'rows': out}, f,
                      ensure_ascii=False, indent=1)
            f.write('\n')
    return d


# ---------------------------------------------------------------- SPEC 變異

def write_spec_variants(s, chapter_len):
    d = os.path.join(HERE, 'specs')
    os.makedirs(d, exist_ok=True)
    spec = open(s['spec_path'], encoding='utf-8').read()
    made = []

    def emit(name, text, what):
        if text == spec:
            print('!! %s 沒改到任何字（SPEC 格式變了？）' % name)
            return
        with open(os.path.join(d, name), 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        made.append((name, what))

    # sp1 錨點的批次歸屬改錯（該章其實在另一批）
    row = s['empty'][0]
    other = next(b for b in ('b01', 'b02', 'b03', 'b04') if b != row['batch'])
    old = '| %s | %s | %d |' % (row['batch'], row['ch'], row['idx'])
    emit('sp1_wrong_batch.md',
         spec.replace(old, '| %s | %s | %d |' % (other, row['ch'], row['idx']), 1),
         '把 %s[%d] 的批次從 %s 改成 %s' % (row['ch'], row['idx'], row['batch'], other))

    # sp2 逐字引句改一個字（只動錨點表那一列；同一句在配套散文裡也出現過，
    #     整檔 replace 會落在散文上，那只是提示層，測不到 S6）
    quote = re.findall(r'「([^「」]+)」', row['quote'])[0]
    typo = quote[:-2] + '囧' + quote[-1]
    lines = spec.split('\n')
    for i, line in enumerate(lines):
        if line.startswith(old) and quote in line:
            lines[i] = line.replace('「%s」' % quote, '「%s」' % typo, 1)
            break
    emit('sp2_quote_typo.md', '\n'.join(lines),
         '把錨點表裡 %s[%d] 的引句改掉一個字' % (row['ch'], row['idx']))

    # sp3 批次表段數寫錯
    bt = s['batch_table'][1]
    emit('sp3_batch_count.md',
         spec.replace('| %d | %d |' % (bt[2], bt[3]), '| %d | %d |' % (bt[2] + 1, bt[3]), 1),
         '把 %s 的段數從 %d 改成 %d' % (bt[0], bt[2], bt[2] + 1))

    # sp4 錨點段號超出該章段數
    hrow = s['hit'][-1]
    n = chapter_len[hrow['full']][1]
    emit('sp4_index_out_of_range.md',
         spec.replace('| %s | %s | %d |' % (hrow['batch'], hrow['ch'], hrow['idx']),
                      '| %s | %s | %d |' % (hrow['batch'], hrow['ch'], n + 77), 1),
         '把 %s[%d] 的段號改成 %d（該章只有 %d 段）'
         % (hrow['ch'], hrow['idx'], n + 77, n))
    return d, made


# ---------------------------------------------------------------- main

def main():
    rows, chapter_len, batch_chapters, s = build_perfect()
    write('perfect', rows, batch_chapters)
    print('perfect  %d 段（判空 %d／命中 %d）'
          % (len(rows), sum(1 for r in rows.values() if not r['domains']),
             sum(1 for r in rows.values() if r['domains'])))

    def mutate(name, fn, what):
        m = copy.deepcopy(rows)
        fn(m)
        write(name, m, batch_chapters)
        print('%-26s %s' % (name, what))

    # m1 → A2：判空錨點被填
    e0 = (s['empty'][0]['full'], s['empty'][0]['idx'])
    mutate('m1_empty_anchor_filled',
           lambda m: m[e0].update(domains=[s['empty'][0]['note'].split('＋')[0].strip()]),
           'A2：判空錨點 %s[%d] 被填' % e0)

    # m2 → A3：命中錨點被清空
    h0 = (s['hit'][0]['full'], s['hit'][0]['idx'])
    mutate('m2_hit_anchor_cleared', lambda m: m[h0].update(domains=[]),
           'A3：命中錨點 %s[%d] 被清空' % h0)

    # m3 → A4：任一段被標 XII（挑一段不在任何錨點表也不被 A 類點名的自由段）
    anchored = {(r['full'], r['idx']) for r in s['empty'] + s['hit']}
    for k in ('a5', 'a6', 'a7'):
        anchored |= set(s[k]['hit']) | set(s[k]['empty'])
    anchored |= set(s['a8']['empty']) | {s['a8']['ref']}
    free = next(k for k in sorted(rows) if k not in anchored)
    mutate('m3_forbidden_xii', lambda m: m[free].update(domains=[s['a4_dom']]),
           'A4：自由段 %s[%d] 被標 %s' % (free[0], free[1], s['a4_dom']))

    # m4 → A5：閘門命中側被判空
    a5h = s['a5']['hit'][0]
    mutate('m4_a5_gate_emptied', lambda m: m[a5h].update(domains=[]),
           'A5：閘門命中側 %s[%d] 判空' % a5h)

    # m5 → A6：「全身遠害」兩段判齊
    a6h, a6e = s['a6']['hit'][0], s['a6']['empty'][0]
    mutate('m5_a6_flattened',
           lambda m: m[a6e].update(domains=list(m[a6h]['domains'])),
           'A6：%s[%d] 與 %s[%d] 判齊' % (a6h + a6e))

    # m6 → A7：剝章相鄰兩段判齊
    a7h, a7e = s['a7']['hit'][0], s['a7']['empty'][0]
    mutate('m6_a7_flattened',
           lambda m: m[a7e].update(domains=list(m[a7h]['domains'])),
           'A7：%s[%d] 與 %s[%d] 判齊' % (a7h + a7e))

    d, made = write_spec_variants(s, chapter_len)
    print('\nSPEC 變異副本 → %s' % os.path.relpath(d, BASE))
    for name, what in made:
        print('%-28s %s' % (name, what))


if __name__ == '__main__':
    main()
