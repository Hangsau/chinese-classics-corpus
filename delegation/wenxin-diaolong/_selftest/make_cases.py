#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""驗收器本身的變異測試。

先由 SPEC 的錨點表合成一份「完美輸出」跑一次，應得 0 FAIL；
再逐一注入變異，每個變異宣告**完整**的 FAIL 碼集合（不是「至少含」），
harness 自己對答案，不需人工比對（水經注教訓：「該抓的抓到了」會放過連鎖）。

用法:
    PYTHONIOENCODING=utf-8 python _selftest/make_cases.py --verify
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
PAD = ("（合成測試用 reason，逐字承重句見前引，這一句只是把長度墊到門檻以上，"
       "不影響判讀，也不參與任何 A 類條件。）")


def build_perfect(spec: Spec, corpus: Corpus) -> dict[str, dict]:
    """由 SPEC 的錨點合成一份應得 0 FAIL 的輸出。

    未被錨點指名的段一律判空——章級上界（五篇 ≤5、書記 ≤5、誄碑 X ≤2、
    哀弔 X ≤3）是上界不是下界，全部填 V 會直接撞破。
    """
    anchors = {a.key(): a for a in spec.anchors}
    _nb, xie = spec.section_bullets("諧讔／諧隱")
    xie_keys = {(c, i) for c, i, _b in xie}

    out: dict[str, dict] = {b: {"batch": f"{b}.md", "rows": []}
                            for b in sorted(corpus.batch_size)}

    for (ch, pi), (batch, _text) in sorted(corpus.para.items()):
        a = anchors.get((ch, pi))
        domains: list[str] = []
        modes = ["observation"]
        quote = ""
        if a is not None:
            quote = a.quote or ""
            if not a.empty:
                picked: list[str] = []
                for g in a.require:
                    cand = sorted(g - a.forbid_d, key=DOMAIN_IDS.index)
                    if not cand:
                        raise SystemExit(f"{ch}[{pi}] 的 require 與 forbid 互相矛盾")
                    if not (set(picked) & g):
                        picked.append(cand[0])
                if not picked and a.nonempty:
                    picked = [d for d in ["V", "VII", "VIII"]
                              if d not in a.forbid_d][:1]
                domains = sorted(set(picked) - a.forbid_d, key=DOMAIN_IDS.index)
        elif (ch, pi) in xie_keys:
            domains = ["VII"]
        if ch == "序志" and pi == 9:
            modes = ["expression"]
        if a is not None:
            modes = [m for m in modes if m not in a.forbid_m] or ["proposition"]
        out[batch]["rows"].append({
            "chapter": ch, "para_index": pi,
            "domains": domains, "modes": modes,
            "reason": f"「{quote}」{PAD}",
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
        rep, _ = check_output(spec, corpus, sorted(tmp.glob("*.json")), True)
        for f in rep.fails[:25]:
            print("  " + f)
        print("合成的完美輸出沒有拿到 0 FAIL，先修驗收器或合成器")
        return 1

    a_empty = spec.section_anchors("必須判空的錨點")[0]
    free = next((ch, pi) for (ch, pi) in sorted(corpus.para)
                if (ch, pi) not in {a.key() for a in spec.anchors})

    cases: list[tuple[str, set[str], object]] = []

    def case(name, expect, fn):
        cases.append((name, set(expect), fn))

    # -- 判空側 -----------------------------------------------------------
    case("判空錨點被填上領域", {"A3"},
         lambda p: find_row(p, a_empty.chapter, a_empty.para_index)
         .__setitem__("domains", ["V"]))
    # 附會[1] 在判空表裡，同時被 A 類第 4 條點名不得含 IX；
    # 填 IX 會同時觸發「必須判空」(A3) 與「不得含」(A4)，兩碼一起宣告。
    case("判空錨點被填上被禁的 IX", {"A3", "A4"},
         lambda p: find_row(p, "附會", 1).__setitem__("domains", ["IX"]))
    case("練字[4] 誤填 formalization", {"A4"},
         lambda p: find_row(p, "練字", 4).__setitem__("modes", ["formalization"]))

    # -- XII 四側（A5）與試金石（A6） --------------------------------------
    case("認證側 正緯[3] 漏掉 XII（連帶把試金石判齊）", {"A5", "A6"},
         lambda p: find_row(p, "正緯", 3).__setitem__("domains", ["V"]))
    case("破除側 正緯[2] 誤填 XII（連帶把試金石判齊）", {"A5", "A6"},
         lambda p: find_row(p, "正緯", 2).__setitem__("domains", ["XI", "XII"]))
    case("認證側 原道第一[4] 漏掉 XII", {"A5"},
         lambda p: find_row(p, "原道第一", 4).__setitem__("domains", ["VII"]))
    case("正緯[3] 只給 XII、漏掉 V／VII 那一側", {"A5"},
         lambda p: find_row(p, "正緯", 3).__setitem__("domains", ["XII"]))
    # 明詩[6] 不得含 XII，而〈明詩〉也不在 A8 允許的四篇內
    case("明詩[6] 外溢成 XII", {"A5", "A8"},
         lambda p: find_row(p, "明詩", 6).__setitem__("domains", ["XII"]))
    case("自由段外溢成 XII（篇級限制）", {"A8"},
         lambda p: find_row(p, *free).__setitem__("domains", ["XII"]))

    # -- 各群命中錨點 ------------------------------------------------------
    case("G1 徵聖[1] 漏掉 VII", {"A9"},
         lambda p: find_row(p, "徵聖", 1).__setitem__("domains", ["V"]))
    case("G2 哀弔[11] 漏掉 X（連帶違反哀弔必含條件）", {"A10", "A15"},
         lambda p: find_row(p, "哀弔", 11).__setitem__("domains", ["VI"]))
    case("G2 詔策[5] 判空（只要求非空的那一列）", {"A10"},
         lambda p: find_row(p, "詔策", 5).__setitem__("domains", []))
    case("G3 神思[4] 判空", {"A12"},
         lambda p: find_row(p, "神思", 4).__setitem__("domains", []))
    case("G4 才略[6] 判空", {"A13"},
         lambda p: find_row(p, "才略", 6).__setitem__("domains", []))
    case("G5 序志[9] 掉了 expression", {"A14"},
         lambda p: find_row(p, "序志", 9).__setitem__("modes", ["proposition"]))
    case("諧讔[1] 判空", {"A11"},
         lambda p: find_row(p, "諧讔", 1).__setitem__("domains", []))

    # -- 章級上界（A15） ---------------------------------------------------
    # 聲律[3]、書記[8][12] 是判空錨點，避開它們才隔離得出 A15
    def blow_cap(p):
        for i in (1, 2, 4, 5, 6, 7):
            find_row(p, "聲律", i)["domains"] = ["V"]
    case("技術側五篇命中衝破上界", {"A15"}, blow_cap)

    def blow_shuji(p):
        for i in (7, 9, 10, 11, 13, 14):
            find_row(p, "書記", i)["domains"] = ["V"]
    case("書記[7]–[27] 命中衝破上界", {"A15"}, blow_shuji)

    def blow_leibei(p):
        for i in range(1, 4):
            find_row(p, "誄碑", i)["domains"] = ["X"]
    case("誄碑含 X 衝破上界", {"A15"}, blow_leibei)

    # -- 原文集注包含條件（A16） ------------------------------------------
    case("原文集注[2] 有領域但 [1] 沒有", {"A16"},
         lambda p: find_row(p, "原文集注", 2).__setitem__("domains", ["V"]))
    case("原文集注[6] 誤填 formalization", {"A16"},
         lambda p: find_row(p, "原文集注", 6).__setitem__("modes", ["formalization"]))

    # -- 詞彙／格式 --------------------------------------------------------
    case("domains 出現 Z-wisdom", {"A17"},
         lambda p: find_row(p, *free).__setitem__("domains", ["Z-wisdom"]))
    case("modes 出現未定義值", {"A17"},
         lambda p: find_row(p, *free).__setitem__("modes", ["storytelling"]))
    case("誤用 worked_instance", {"A18"},
         lambda p: find_row(p, *free).__setitem__("modes", ["worked_instance"]))
    case("命中段 reason 太短撐不起格數", {"A19"},
         lambda p: find_row(p, "徵聖", 1).__setitem__("reason", "湊的"))
    case("reason 空白", {"A1", "A19"},
         lambda p: find_row(p, "徵聖", 1).__setitem__("reason", "   "))

    # -- rows 結構（A1／A2） ----------------------------------------------
    # 少一列 / 改章名 / 改段號 都讓該段從 rows 消失：批內段數、全書段數、
    # 群段數三個不變式必然一起響，完整集合而不是「至少含 A1」。
    case("少回一列", {"A1", "A2"},
         lambda p: p[corpus.para[free][0]]["rows"].remove(find_row(p, *free)))
    case("章名被改寫", {"A1", "A2"},
         lambda p: find_row(p, *free).__setitem__("chapter", free[0] + "X"))
    case("para_index 被改寫", {"A1", "A2"},
         lambda p: find_row(p, *free).__setitem__("para_index", 999))
    case("多回一列", {"A1"},
         lambda p: p[corpus.para[free][0]]["rows"].append(
             copy.deepcopy(find_row(p, *free))))
    case("整批的 batch 欄寫錯", {"A1", "A2"},
         lambda p: p["b05"].__setitem__("batch", "b99.md"))

    bad = 0
    for name, expect, fn in cases:
        payload = copy.deepcopy(perfect)
        fn(payload)
        got = run(spec, corpus, payload, tmp)
        ok = got == expect
        bad += 0 if ok else 1
        print(f"{'OK  ' if ok else 'BAD '}{name:<34} 期望 {sorted(expect)}  "
              f"實得 {sorted(got)}")

    for f in tmp.glob("*.json"):
        f.unlink()
    tmp.rmdir()

    print(f"\n{len(cases)} 個變異，{bad} 個對不上答案")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
