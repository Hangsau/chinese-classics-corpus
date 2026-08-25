"""驗收器自身的反向驗證：一份完美輸出應得 0 FAIL，二十三份變異各得一組指定的 FAIL 碼。

驗收器沒被驗過就等於沒有驗收。完美輸出由 SPEC 的四張錨點表＋A 類條文現場合成
（不手抄），每份變異只動一處，預期寫成**完整的 FAIL 碼可重集合**而不是「至少含」——
水經注那次的教訓是「該抓的抓到了」會放過連鎖，寫成完整集合才逼得出「這一刀為什麼
響兩下」。

  PYTHONIOENCODING=utf-8 python delegation/mozi/_selftest/make_cases.py --verify
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
    """照 SPEC 每一條錨點與 A 類條文標對：預設判空＋observation，逐層覆寫。"""
    paras, chapter_len, batch_chapters, header_bad = accept.read_batches()
    if header_bad:
        raise SystemExit('批次檔標頭不一致，先修批次檔：%s' % header_bad[:3])
    s = accept.parse_spec()
    d = s['declared']

    rows = {}
    for (ch, idx), (_b, text) in paras.items():
        rows[(ch, idx)] = {'chapter': ch, 'para_index': idx, 'domains': [],
                           'modes': ['observation'],
                           'reason': '「%s」合成測試用' % text[:12]}
    # A2／A3 整章判空章：清空並走條文指定的 mode
    need_mode = (d.get('empty_ch_modes') or d.get('empty_ch_modes_sec')
                 or (0, 'formalization'))[1]
    for ch, _n, _b, _g in s['empty_ch']:
        for i in range(1, chapter_len.get(ch, ('', 0))[1] + 1):
            rows[(ch, i)]['domains'] = []
            rows[(ch, i)]['modes'] = [need_mode]
    # A5 命中錨點：and 取全部、or 取第一格
    for ch, idx, _b, _q, cell in s['hit']:
        mode, need, _forbid = accept.parse_req(cell)
        rows[(ch, idx)]['domains'] = list(need) if mode == 'and' else [need[0]]
        rows[(ch, idx)]['modes'] = ['proposition']
    # A6／A7 條文層的單段要求（表沒寫到的部分補齊）
    if s['a6']:
        ch, idx, need = s['a6']
        have = rows[(ch, idx)]['domains']
        rows[(ch, idx)]['domains'] = have + [x for x in need if x not in have]
    for ch, idx, need, forb in s['a7']:
        have = [x for x in rows[(ch, idx)]['domains'] if x not in forb]
        rows[(ch, idx)]['domains'] = have + [x for x in need if x not in have]
    # A8 非空錨點：預設給 V（下面再依禁用清單讓路）
    for ch, idx, _b, _q in s['nonempty']:
        if not rows[(ch, idx)]['domains']:
            rows[(ch, idx)]['domains'] = ['V']
            rows[(ch, idx)]['modes'] = ['proposition']
    # A10–A14 條文要求非空的段
    for _no, ch, idx, pol in s['polarity']:
        if pol == '非空' and not rows[(ch, idx)]['domains']:
            rows[(ch, idx)]['domains'] = ['V']
            rows[(ch, idx)]['modes'] = ['proposition']
    # A9 不得填 XII：完美輸出一格都不填
    for ch, idx in accept.all_forbid_xii(s, accept.group_map(s, chapter_len),
                                         chapter_len):
        have = rows.get((ch, idx))
        if have and 'XII' in have['domains']:
            have['domains'] = [x for x in have['domains'] if x != 'XII'] or ['V']
    # A15–A17 條文層禁用領域：讓路，讓完的若空了就補一格合法的
    bucket = {}
    for _no, ch, idx, x in s['forbid_dom']:
        bucket.setdefault((ch, idx), []).append(x)
    for (ch, idx), bad in bucket.items():
        r = rows[(ch, idx)]
        r['domains'] = [x for x in r['domains'] if x not in bad]
        if not r['domains'] and any(p == '非空' for _n, c, i, p in s['polarity']
                                    if (c, i) == (ch, idx)):
            r['domains'] = [x for x in ('V', 'VII', 'XI') if x not in bad][:1]
    # A4／A10–A14 判空側：最後清，蓋掉上面任何誤設
    for ch, idx, _b, _q, _r in s['empty']:
        rows[(ch, idx)]['domains'] = []
    for _no, ch, idx, pol in s['polarity']:
        if pol == '判空':
            rows[(ch, idx)]['domains'] = []
    # A19 長度上限
    for r in rows.values():
        r['domains'] = r['domains'][:s['max_dom']]
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
     lambda m: _set(m, ('備高臨', 1), domains=['V'])),
    ('m02_empty_chapter_mode_dropped', ['A3'],
     lambda m: _set(m, ('備水', 1), modes=['observation'])),
    ('m03_empty_anchor_filled', ['A4'],
     lambda m: _set(m, ('七患', 2), domains=['V'])),
    # 判空錨點同時被條文 10 點名 → 必然響兩下
    ('m04_empty_anchor_in_polarity', ['A4', 'A10'],
     lambda m: _set(m, ('雜守', 8), domains=['V'])),
    ('m05_hit_anchor_cleared', ['A5'],
     lambda m: _set(m, ('法儀', 3), domains=[])),
    ('m06_nonempty_cleared', ['A8'],
     lambda m: _set(m, ('親士', 1), domains=[])),
    ('m07_nonempty_in_polarity', ['A8', 'A14'],
     lambda m: _set(m, ('尚賢中', 11), domains=[])),
    ('m08_forbidden_xii', ['A9'],
     lambda m: _set(m, ('號令', 1), domains=['XII'])),
    # G5 整章判空的段同時在 XII 禁用清單 → 隔離不掉，兩碼一起宣告
    ('m09_forbidden_xii_in_empty_chapter', ['A2', 'A9'],
     lambda m: _set(m, ('旗幟', 1), domains=['XII'])),
    # 條文 6 的段在命中表裡是 XII＋VII 的 and 格 → 拆掉一半兩邊都響
    ('m10_a6_split', ['A5', 'A6'],
     lambda m: _set(m, ('魯問', 14), domains=['XII'])),
    ('m11_a7_direction_flipped', ['A5', 'A7'],
     lambda m: _set(m, ('非命上', 4), domains=['V'])),
    ('m12_a11_nonempty_cleared', ['A5', 'A11'],
     lambda m: _set(m, ('備梯', 1), domains=[])),
    ('m13_a12_empty_filled', ['A4', 'A12'],
     lambda m: _set(m, ('迎敵祠', 1), domains=['V'])),
    ('m14_a13_empty_filled', ['A4', 'A13'],
     lambda m: _set(m, ('備城門', 8), domains=['V'])),
    # 禁用領域與判空錨點重疊：同一段兩格違規只算一次 A15
    ('m15_a15_forbidden_domain', ['A4', 'A15'],
     lambda m: _set(m, ('節用上', 3), domains=['III', 'IV'])),
    ('m16_a16_forbidden_domain', ['A4', 'A16'],
     lambda m: _set(m, ('節用中', 3), domains=['IX'])),
    ('m17_a17_forbidden_domain', ['A4', 'A17'],
     lambda m: _set(m, ('小取', 10), domains=['III', 'V'])),
    ('m18_worked_instance', ['A18'],
     lambda m: _set(m, ('親士', 2), modes=['worked_instance'])),
    ('m19_illegal_domain', ['A19'],
     lambda m: _set(m, ('親士', 2), domains=['Z-wisdom'])),
    ('m20_four_domains', ['A19'],
     lambda m: _set(m, ('親士', 2), domains=['I', 'II', 'III', 'IV'])),
    ('m21_illegal_mode', ['A19'],
     lambda m: _set(m, ('親士', 2), modes=['foo'])),
    # 少一列：段數對不上、para_index 也斷號
    ('m22_row_dropped', ['A1', 'A1'],
     lambda m: m.pop(('親士', 2))),
    ('m23_reason_blank', ['A1'],
     lambda m: _set(m, ('親士', 2), reason='   ')),
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
