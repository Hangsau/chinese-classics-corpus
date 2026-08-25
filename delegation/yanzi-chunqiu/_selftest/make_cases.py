#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""驗收器本身的變異測試。

先由 SPEC 的錨點表合成一份「完美輸出」跑一次，應得 0 FAIL；
再逐一注入變異，每個變異宣告**完整**的 FAIL 碼集合（不是「至少含」），
harness 自己對答案，不需人工比對。

用法:
    python _selftest/make_cases.py --verify
"""
from __future__ import annotations

import copy
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
BOOK = HERE.parent
sys.path.insert(0, str(BOOK))

from accept import (  # noqa: E402
    Corpus, Spec, DOMAIN_IDS, check_output,
)

SPEC_PATH = BOOK / "SPEC.md"
PAD = "（合成測試用 reason，逐字承重句見前引，這一句只是把長度墊到門檻以上，不影響判讀。）"


def build_perfect(spec: Spec, corpus: Corpus) -> dict[str, dict]:
    """由 SPEC 的錨點合成一份應得 0 FAIL 的輸出。"""
    anchors = {a.key(): a for a in spec.anchors}
    quote_of = {a.key(): (a.quote or "") for a in spec.anchors}
    out: dict[str, dict] = {}
    for batch in sorted(corpus.batch_size):
        out[batch] = {"batch": f"{batch}.md", "rows": []}

    for (ch, pi), (batch, _text) in sorted(corpus.para.items()):
        a = anchors.get((ch, pi))
        modes = ["narrative"] if corpus.juan[ch] not in ("問上", "問下") \
            else ["proposition"]
        if a is None:
            domains = ["V"]
        elif a.empty:
            domains = []
            modes = ["observation"]
        else:
            picked: list[str] = []
            for g in a.require:
                cand = sorted(g - a.forbid_d, key=DOMAIN_IDS.index)
                if not cand:
                    raise SystemExit(f"{ch}[{pi}] 的 require 與 forbid 互相矛盾")
                if not (set(picked) & g):
                    picked.append(cand[0])
            if not picked:
                picked = [d for d in ["V"] if d not in a.forbid_d] or ["VII"]
            domains = sorted(set(picked) - a.forbid_d, key=DOMAIN_IDS.index)
            modes = [m for m in modes if m not in a.forbid_m] or ["observation"]
        reason = f"「{quote_of.get((ch, pi), '')}」{PAD}"
        out[batch]["rows"].append({
            "chapter": ch, "para_index": pi,
            "domains": domains, "modes": modes, "reason": reason,
        })
    return out


def run(spec: Spec, corpus: Corpus, payload: dict[str, dict],
        tmp: pathlib.Path) -> set[str]:
    for f in tmp.glob("*.json"):
        f.unlink()
    paths = []
    for batch, obj in sorted(payload.items()):
        p = tmp / f"{batch}.json"
        p.write_bytes(json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8"))
        paths.append(p)
    rep, _rows = check_output(spec, corpus, paths, whole_book=True)
    return {re.match(r"\[(\w+)\]", f).group(1) for f in rep.fails}


def find_row(payload: dict, ch: str, pi: int = 1) -> dict:
    for obj in payload.values():
        for row in obj["rows"]:
            if row["chapter"] == ch and row["para_index"] == pi:
                return row
    raise SystemExit(f"合成輸出裡找不到 {ch}[{pi}]")


def main() -> int:
    corpus = Corpus(BOOK)
    spec = Spec(SPEC_PATH)
    tmp = HERE / "_tmp_out"
    tmp.mkdir(exist_ok=True)

    perfect = build_perfect(spec, corpus)
    base = run(spec, corpus, perfect, tmp)
    print(f"完美輸出：{len(base)} 類 FAIL {sorted(base)}")
    if base:
        rep, _ = check_output(spec, corpus, sorted(tmp.glob('*.json')), True)
        for f in rep.fails[:20]:
            print("  " + f)
        print("合成的完美輸出沒有拿到 0 FAIL，先修驗收器或合成器")
        return 1

    # 各段錨點，供變異取用
    a_empty = spec.section_anchors("必須判空的錨點")[0]
    a_break = spec.section_anchors("破除側")[0]
    a_cert = [a for a in spec.section_anchors("認證側")]
    a_tech = spec.section_anchors("技術側")[0]
    xs = spec.section_anchors("X 的兩側")
    x_hit = [a for a in xs if any("X" in g for g in a.require)][0]
    x_null = [a for a in xs if "X" in a.forbid_d][0]
    a_cliche = spec.section_anchors("敘事套語不是判空理由")[0]
    a_g2 = spec.section_anchors("G2 論說群")[0]
    a_g1 = spec.section_anchors("G1 敘事群")[0]
    touchstone = next(a for a in a_cert if "XII" in {d for g in a.require for d in g}
                      and not any("X" in g and "XII" not in g for g in a.require))
    free = next((ch, pi) for (ch, pi) in sorted(corpus.para)
                if (ch, pi) not in {a.key() for a in spec.anchors})

    cases = []

    def case(name, expect, fn):
        cases.append((name, set(expect), fn))

    case("判空錨點被填上領域", {"A2"},
         lambda p: find_row(p, a_empty.chapter, a_empty.para_index)
         .__setitem__("domains", ["V"]))
    case("破除側漏掉 XI", {"A3"},
         lambda p: find_row(p, a_break.chapter, a_break.para_index)
         .__setitem__("domains", ["V"]))
    case("破除側誤填 XII", {"A3"},
         lambda p: find_row(p, a_break.chapter, a_break.para_index)
         .__setitem__("domains", ["XI", "XII"]))
    case("認證側漏掉 XII（連帶把試金石判齊）", {"A5", "A6"},
         lambda p: find_row(p, touchstone.chapter, touchstone.para_index)
         .__setitem__("domains", ["XI"]))
    case("技術側誤填 XII", {"A7"},
         lambda p: find_row(p, a_tech.chapter, a_tech.para_index)
         .__setitem__("domains", ["V", "XII"]))
    case("技術側整段判空", {"A7"},
         lambda p: find_row(p, a_tech.chapter, a_tech.para_index)
         .__setitem__("domains", []))
    case("X 命中側漏掉 X", {"A8"},
         lambda p: find_row(p, x_hit.chapter, x_hit.para_index)
         .__setitem__("domains", ["V"]))
    case("X 判空側外溢成 X", {"A8"},
         lambda p: find_row(p, x_null.chapter, x_null.para_index)
         .__setitem__("domains", ["V", "X"]))
    case("敘事套語段誤填 formalization", {"A10"},
         lambda p: find_row(p, a_cliche.chapter, a_cliche.para_index)
         .__setitem__("modes", ["narrative", "formalization"]))
    case("G2 指定段漏掉指定領域", {"A11"},
         lambda p: find_row(p, a_g2.chapter, a_g2.para_index)
         .__setitem__("domains", ["IX"]))
    case("G1 指定段漏掉指定領域", {"A12"},
         lambda p: find_row(p, a_g1.chapter, a_g1.para_index)
         .__setitem__("domains", ["IX"]))
    case("domains 出現 Z-wisdom", {"A13"},
         lambda p: find_row(p, *free).__setitem__("domains", ["V", "Z-wisdom"]))
    case("modes 出現未定義值", {"A13"},
         lambda p: find_row(p, *free).__setitem__("modes", ["storytelling"]))
    case("誤用 worked_instance", {"A14"},
         lambda p: find_row(p, *free).__setitem__("modes", ["worked_instance"]))
    case("reason 太短撐不起格數", {"A15"},
         lambda p: find_row(p, *free).__setitem__("reason", "湊的"))
    case("reason 空白", {"A1", "A15"},
         lambda p: find_row(p, *free).__setitem__("reason", "   "))
    # 這三個變異都讓一段從 rows 消失，卷的章數與段數必然跟著對不上，
    # A16 是獨立不變式不是連鎖誤報，兩碼一起宣告。
    case("少回一列", {"A1", "A16"},
         lambda p: p[corpus.para[free][0]]["rows"].remove(find_row(p, *free)))
    case("章名被改寫", {"A1", "A16"},
         lambda p: find_row(p, *free).__setitem__("chapter", free[0] + "X"))
    case("para_index 被改寫", {"A1", "A16"},
         lambda p: find_row(p, *free).__setitem__("para_index", 99))
    case("多回一列", {"A1"},
         lambda p: p[corpus.para[free][0]]["rows"].append(
             copy.deepcopy(find_row(p, *free))))

    bad = 0
    for name, expect, fn in cases:
        payload = copy.deepcopy(perfect)
        fn(payload)
        got = run(spec, corpus, payload, tmp)
        mark = "OK  " if got == expect else "BAD "
        if got != expect:
            bad += 1
        print(f"{mark}{name:<32} 期望 {sorted(expect)}  實得 {sorted(got)}")

    for f in tmp.glob("*.json"):
        f.unlink()
    tmp.rmdir()

    print(f"\n{len(cases)} 個變異，{bad} 個對不上答案")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
