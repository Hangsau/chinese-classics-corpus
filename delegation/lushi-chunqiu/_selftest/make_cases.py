"""驗收器自身的反向驗證：一份完美輸出應得 0 FAIL，十六份變異各得一組指定的 FAIL 碼。

驗收器沒被驗過就等於沒有驗收。完美輸出由 SPEC 的四張錨點表現場合成（不手抄），
每份變異只動一處，預期寫成**完整的 FAIL 碼可重集合**而不是「至少含」——水經注那次
的教訓是「該抓的抓到了」會放過連鎖，寫成完整集合才逼得出「這一刀為什麼響兩下」。

  PYTHONIOENCODING=utf-8 python delegation/lushi-chunqiu/_selftest/make_cases.py --verify
"""
import argparse
import copy
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
sys.path.insert(0, BASE)
import accept  # noqa: E402

TMP = os.path.join(HERE, '_tmp')


# ---------------------------------------------------------------- 完美輸出

def build_perfect():
    """照 SPEC 每一條錨點標對：預設判空＋observation，四張表逐條覆寫。"""
    paras, chapter_len, batch_chapters, header_bad = accept.read_batches()
    if header_bad:
        raise SystemExit('批次檔標頭不一致，先修批次檔：%s' % header_bad[:3])
    s = accept.parse_spec()

    rows = {}
    for (ch, idx), (_b, text) in paras.items():
        rows[(ch, idx)] = {'chapter': ch, 'para_index': idx, 'domains': [],
                           'modes': ['observation'],
                           'reason': '「%s」合成測試用' % text[:12]}
    # A2／A3 整章判空章：清空並走 formalization
    for ch, _n, _b, _g in s['empty_ch']:
        for (c, _i), r in rows.items():
            if c == ch:
                r['domains'] = []
                r['modes'] = ['formalization']
    # A5 命中錨點：and 取全部、or 取第一格
    for ch, idx, _b, _q, cell in s['hit']:
        mode, need, _forbid = accept.parse_req(cell)
        rows[(ch, idx)]['domains'] = list(need) if mode == 'and' else [need[0]]
        rows[(ch, idx)]['modes'] = ['proposition']
    # A8 非空錨點：V 對每一條都合法（A10 只禁 士節[2] 的 VI）
    for ch, idx, _b, _q in s['nonempty']:
        rows[(ch, idx)]['domains'] = ['V']
        rows[(ch, idx)]['modes'] = ['proposition']
    # A4／A13 判空錨點：最後清，蓋掉上面任何誤設
    for ch, idx, _b, _q, _cell in s['empty']:
        rows[(ch, idx)]['domains'] = []
    # A11 必須判齊的段對
    for c1, i1, c2, i2 in s['equal_pairs']:
        rows[(c2, i2)]['domains'] = list(rows[(c1, i1)]['domains'])
        rows[(c2, i2)]['modes'] = list(rows[(c1, i1)]['modes'])
    return rows, batch_chapters, s


def write(dirname, rows, batch_chapters):
    d = os.path.join(TMP, dirname) if not os.path.isabs(dirname) else dirname
    os.makedirs(d, exist_ok=True)
    for batch, chs in batch_chapters.items():
        order = {c: n for n, c in enumerate(chs)}
        out = [r for (c, _i), r in sorted(rows.items(),
                                          key=lambda kv: (order.get(kv[0][0], 99), kv[0][1]))
               if c in order]
        with open(os.path.join(d, '%s.json' % batch), 'w',
                  encoding='utf-8', newline='\n') as f:
            json.dump({'batch': '%s.md' % batch, 'rows': out}, f,
                      ensure_ascii=False, indent=1)
            f.write('\n')
    return d


# ---------------------------------------------------------------- 變異

def _set(m, key, **kw):
    m[key].update(kw)


CASES = [
    # (名稱, 預期 FAIL 碼完整可重集合, 變異)
    ('m01_empty_chapter_filled', ['A2'],
     lambda m: _set(m, ('孟春紀', 1), domains=['V'])),
    ('m02_empty_chapter_mode_dropped', ['A3'],
     lambda m: _set(m, ('孟春紀', 2), modes=['observation'])),
    ('m03_empty_anchor_filled', ['A4'],
     lambda m: _set(m, ('上農', 3), domains=['V'])),
    # 判空側同時是三章分裂試金石 → 必然響兩下
    ('m04_split_empty_filled', ['A4', 'A13'],
     lambda m: _set(m, ('用民', 4), domains=['V'])),
    ('m05_hit_anchor_cleared', ['A5'],
     lambda m: _set(m, ('上農', 1), domains=[])),
    ('m06_nonempty_cleared', ['A8'],
     lambda m: _set(m, ('本生', 4), domains=[])),
    ('m07_split_nonempty_cleared', ['A8', 'A13'],
     lambda m: _set(m, ('用民', 7), domains=[])),
    ('m08_forbidden_xii', ['A9'],
     lambda m: _set(m, ('有始', 5), domains=['XII'])),
    # E1 的段同時在整章判空表與 XII 禁用清單 → 隔離不掉，兩碼一起宣告
    ('m09_forbidden_xii_in_empty_chapter', ['A2', 'A9'],
     lambda m: _set(m, ('仲冬紀', 1), domains=['XII'])),
    ('m10_forbidden_domain', ['A10'],
     lambda m: _set(m, ('士節', 2), domains=['VI'])),
    ('m11_equal_pair_split', ['A11'],
     lambda m: _set(m, ('應言', 2), domains=['V'])),
    # 兩段各自的必須含欄無交集，判齊時挑各自合法的一格才隔離得出 A12
    ('m12_differ_pair_flattened', ['A12'],
     lambda m: [_set(m, ('任數', 4), domains=['II', 'XIII']),
                _set(m, ('慎人', 4), domains=['II', 'XIII'])]),
    ('m13_worked_instance', ['A14'],
     lambda m: _set(m, ('士節', 1), modes=['worked_instance'])),
    ('m14_four_domains', ['A15'],
     lambda m: _set(m, ('士節', 1), domains=['I', 'II', 'III', 'IV'])),
    ('m15_illegal_domain', ['A15'],
     lambda m: _set(m, ('士節', 1), domains=['XIV'])),
    # 少一列：段數對不上、para_index 也斷號
    ('m16_row_dropped', ['A1', 'A1'],
     lambda m: m.pop(('士節', 1))),
    ('m17_reason_blank', ['A1'],
     lambda m: _set(m, ('士節', 1), reason='   ')),
]


def codes(fails):
    out = []
    for x in fails:
        m = re.match(r'^(A\d+)', x)
        out.append(m.group(1) if m else '??')
    return sorted(out)


def verify():
    rows, batch_chapters, _s = build_perfect()
    d = write(os.path.join(HERE, 'perfect'), rows, batch_chapters)
    got = accept.collect_fails(d, [])
    print('perfect  %d 段 %d 批 → FAIL %d' % (len(got['rows']), len(got['batches']),
                                              len(got['fails'])))
    bad = 0
    if got['fails']:
        bad += 1
        for x in got['fails'][:10]:
            print('    ' + x)

    for name, want, fn in CASES:
        m = copy.deepcopy(rows)
        fn(m)
        d = write(name, m, batch_chapters)
        fails = accept.collect_fails(d, [])['fails']
        ok = codes(fails) == sorted(want)
        print('%-38s 預期 %-12s 實得 %-12s %s'
              % (name, '+'.join(sorted(want)), '+'.join(codes(fails)) or '(無)',
                 'ok' if ok else '<<< 不符'))
        if ok:
            shutil.rmtree(d)
        else:
            bad += 1
            for x in fails:
                print('    ' + x)
            print('    保留輸出：%s' % os.path.relpath(d, BASE))
    if os.path.isdir(TMP) and not os.listdir(TMP):
        os.rmdir(TMP)
    print('--- 反向驗證：%d 例不符 ---' % bad)
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description='accept.py 的反向驗證素材與自動對答案')
    ap.add_argument('--verify', action='store_true', help='合成、跑驗收、自己對答案')
    args = ap.parse_args()
    if not args.verify:
        rows, batch_chapters, _s = build_perfect()
        write(os.path.join(HERE, 'perfect'), rows, batch_chapters)
        print('已寫 perfect（%d 段）；要對答案請加 --verify' % len(rows))
        return 0
    return verify()


if __name__ == '__main__':
    sys.exit(main())
