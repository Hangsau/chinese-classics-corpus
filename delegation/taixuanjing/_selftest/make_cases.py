"""合成 accept.py 的反向驗證素材：一份完美輸出＋六份各注入一種錯誤的輸出。

驗收器沒被驗過就等於沒有驗收。完美輸出應得 0 FAIL；六份變異各自只改一處，
每處對準一條不同的 A 類條款，用來確認那條條款真的有牙齒。

  PYTHONIOENCODING=utf-8 python delegation/taixuanjing/_selftest/make_cases.py
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
sys.path.insert(0, BASE)
import accept  # noqa: E402


def build_perfect():
    """照 SPEC 所有錨點標對的一份輸出：預設判空＋observation，錨點逐條覆寫。"""
    paras, chapter_len, batch_chapters, _ = accept.read_batches()
    s = accept.parse_spec()

    rows = {}
    for (ch, idx), (batch, text) in paras.items():
        rows[(ch, idx)] = {'chapter': ch, 'para_index': idx, 'domains': [],
                           'modes': ['observation'],
                           'reason': '「%s」位次斷語／體例登錄，合成測試用' % text[:12]}
    # A8：玄數全章 formalization
    if s['a8']:
        a8ch, _n, a8mode = s['a8']
        for (ch, idx), r in rows.items():
            if ch == a8ch:
                r['modes'] = [a8mode]
                r['domains'] = []
    # 其餘 formalization 大宗（B 類帶寬用，不影響 A 類）
    for ch, _n, _b in s['empty_ch']:
        for (c, i), r in rows.items():
            if c == ch and 'formalization' not in r['modes']:
                r['modes'] = ['formalization']
    # 命中錨點：取「必須含」的第一格
    for ch, idx, _b, _q, cell in s['hit']:
        mode, need, _forbid = accept.parse_req(cell)
        r = rows[(ch, idx)]
        r['domains'] = list(need) if mode == 'and' else [need[0]]
        r['modes'] = ['proposition']
        r['reason'] = '「%s」本段自己說出對人的判斷，合成測試用' % paras[(ch, idx)][1][:12]
    # 判空錨點：明確清空（覆蓋掉上面可能的誤設）
    for ch, idx, _b, _q, _cell in s['empty']:
        rows[(ch, idx)]['domains'] = []
    return rows, chapter_len, batch_chapters, s


def write(dirname, rows, batch_chapters, only=None):
    d = os.path.join(HERE, dirname)
    os.makedirs(d, exist_ok=True)
    for batch, chs in batch_chapters.items():
        if only and batch not in only:
            continue
        chset = set(chs)
        out = [r for (c, _i), r in sorted(rows.items(), key=lambda kv: (chs.index(kv[0][0]) if kv[0][0] in chset else 99, kv[0][1]))
               if c in chset]
        with open(os.path.join(d, '%s.json' % batch), 'w', encoding='utf-8', newline='\n') as f:
            json.dump({'batch': '%s.md' % batch, 'rows': out}, f,
                      ensure_ascii=False, indent=1)
            f.write('\n')
    return d


def main():
    rows, chapter_len, batch_chapters, s = build_perfect()
    write('perfect', rows, batch_chapters)
    print('perfect  %d 段' % len(rows))

    def mutate(name, only, fn):
        m = copy.deepcopy(rows)
        fn(m)
        write(name, m, batch_chapters, only={only})
        print('%-22s (%s)' % (name, only))

    # m1 整章判空章被填領域（眾＝b02 的整章判空章）
    ch1, _n1, b1 = s['empty_ch'][0]

    def f1(m):
        m[(ch1, 5)]['domains'] = ['V']
    mutate('m1_empty_chapter_filled', b1, f1)

    # m2 必須判空錨點被填（常[1]，b02）
    def f2(m):
        m[('常', 1)]['domains'] = ['V']
    mutate('m2_empty_anchor_filled', 'b02', f2)

    # m3 必須命中錨點被清空（玄攡[3]，b03）
    def f3(m):
        m[('玄攡', 3)]['domains'] = []
    mutate('m3_hit_anchor_cleared', 'b03', f3)

    # m4 XII 禁用段被標 XII（玄告[2]，b04；只在禁用清單、不在兩張錨點表）
    def f4(m):
        m[('玄告', 2)]['domains'] = ['XII']
    mutate('m4_forbidden_xii', 'b04', f4)

    # m5 聚 三向被抹平成同一答案（b02）
    def f5(m):
        for i in (2, 4, 7, 8):
            m[('聚', i)]['domains'] = ['XII']
    mutate('m5_ju_flattened', 'b02', f5)

    # m6 積 兩向被抹平（[3] 跟 [5][9][10] 同答案，b02）
    def f6(m):
        m[('積', 3)]['domains'] = ['VII']
    mutate('m6_ji_flattened', 'b02', f6)


if __name__ == '__main__':
    main()
