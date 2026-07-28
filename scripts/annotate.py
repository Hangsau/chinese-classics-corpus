"""段落級標註的回填工具。

用法：在 scripts/ 下建一個一次性的 tmp_ann_<slug>.py，內容只有資料：

    from annotate import *

    c = "本議第一"
    put(c, 1, ["V"], [NA])
    put(c, 11, ["V"], [FO, P], note="均輸平準的運作機制")
    span(c, 2, 10, ["V"], [P])          # 連號同標時用

    apply("yantielun")

然後 `PYTHONIOENCODING=utf-8 python scripts/tmp_ann_<slug>.py`，跑完刪掉那支 tmp 檔。

不要手寫或手改 annotations.json——錨點就是這樣被弄壞的。
apply() 會雙向檢查：骨架裡每一段都必須有對照、對照表裡不得有骨架沒有的鍵。
任一邊不齊就 assert 失敗且不寫檔，這是本流程唯一的安全網，別拿掉。
"""

import json
import sys
from pathlib import Path

P = "proposition"
PR = "prescription"
OB = "observation"
FO = "formalization"
NA = "narrative"
EX = "expression"
RI = "ritual"

TAGGED_BY = "claude-opus-4-7"

_M = {}


def put(chapter, idx, domains, modes, conf="medium", note=None):
    _M[(chapter, idx)] = (domains, modes, conf, note)


def span(chapter, a, b, domains, modes, conf="medium", note=None):
    for i in range(a, b + 1):
        put(chapter, i, domains, modes, conf, note)


def apply(slug, tagged_at=None, root=None):
    root = Path(root) if root else Path(__file__).resolve().parent.parent
    path = root / "translations" / slug / "annotations.json"
    rows = json.loads(path.read_text(encoding="utf-8"))

    if tagged_at is None:
        from datetime import datetime, timedelta, timezone

        tagged_at = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")

    seen, missing = set(), []
    for r in rows:
        key = (r["anchor"]["chapter"], r["anchor"]["para_index"])
        if key not in _M:
            missing.append(key)
            continue
        seen.add(key)
        domains, modes, conf, note = _M[key]
        r["psych_domains"] = domains
        r["discourse_mode"] = modes
        r["confidence"] = conf
        r["note"] = note
        r["tagged_by"] = TAGGED_BY
        r["tagged_at"] = tagged_at

    unmatched = sorted(set(_M) - seen)
    assert not missing, f"骨架有 {len(missing)} 段沒對照：{missing[:20]}"
    assert not unmatched, f"對照表有 {len(unmatched)} 個多餘鍵：{unmatched[:20]}"

    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{slug}: {len(rows)} 段已回填")


def stats(slug, root=None):
    """回填後算 psych_survey 要填的數字。"""
    import collections

    root = Path(root) if root else Path(__file__).resolve().parent.parent
    rows = json.loads((root / "translations" / slug / "annotations.json").read_text(encoding="utf-8"))
    order = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII"]
    dom = collections.Counter()
    mode = collections.Counter()
    empty = 0
    for r in rows:
        if not r["psych_domains"]:
            empty += 1
        dom.update(r["psych_domains"] or [])
        mode.update(r["discourse_mode"] or [])
    print(f"paras_total       {len(rows)}")
    print(f"paras_no_domain   {empty}")
    print(f"domains_hit       {[k for k in order if dom[k]]}")
    print(f"domains_null      {[k for k in order if not dom[k]]}")
    print(f"domain_para_counts {({k: dom[k] for k in order if dom[k]})}")
    print(f"discourse_mode     {dict(mode)}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "stats":
        stats(sys.argv[2])
    else:
        print(__doc__)
