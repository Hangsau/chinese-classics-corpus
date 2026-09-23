#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""輸出層變異測試：先由 SPEC 合成一份「完美回收」，再逐條下毒。

`probe_spec.py` 驗的是 `--check-spec`（SPEC 自己對不對），A 類那一半在沒有
`out/` 的時候一條都沒跑過。本檔補的就是這一半：

1. 依 SPEC 的錨點表合成 17 批共 307 段的完美輸出，**應得 0 FAIL**——這同時
   證明錨點之間沒有互相矛盾（水經注踩過：上限型條件與配對型條件說反，
   `--check-spec` 全綠，照發會把正確輸出判成 FAIL）。
2. 注入變異，每一刀宣告**完整**的 FAIL 碼集合。「至少含」會放過連鎖：改一次
   `reason` 常常同時觸發兩三族，寫成完整集合才逼得出「這一刀為什麼響三下」。

全程在記憶體裡跑，不寫 `out/`——`out/` 是真回收物的位置，探針不進去。

用法:
    PYTHONIOENCODING=utf-8 python _selftest/make_cases.py
"""
from __future__ import annotations

import copy
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
PKG = HERE.parent
sys.path.insert(0, str(PKG))

import accept  # noqa: E402

FILLER = "本段逐句讀過，承重句已在上面逐條指出，判讀理由到此為止。"


def pick_quote(text: str) -> str:
    """挑一段安全的逐字引句：不跨內層引號、不落在夾注裡、不含冒號。"""
    body = re.sub(r"〈.+?〉", "", text)
    for chunk in re.split(r"[「」：，。；？！]", body):
        if len(chunk) >= 6:
            return chunk[:20]
    return ""


def synth(corpus: accept.Corpus, spec: accept.Spec) -> dict[str, list[dict]]:
    by_key = {a.key(): a for a in spec.anchors}
    out: dict[str, list[dict]] = {b: [] for b in accept.BATCH_IDS}
    for (ch, pi), (b, text) in corpus.para.items():
        a = by_key.get((ch, pi))
        doms: list[str] = []
        if a is not None and not a.empty:
            for grp in a.require:
                cand = sorted(grp - a.forbid_d)
                if cand:
                    doms.append(cand[0])
            if a.nonempty and not doms:
                doms = [d for d in ("V", "VII") if d not in a.forbid_d][:1]
            doms = [d for d in dict.fromkeys(doms) if d not in a.forbid_d]
        q = pick_quote(text)
        head = f"「{q}」是本段的承重句。" if q else "本段登錄之外無對人的斷語。"
        out[b].append({"chapter": ch, "para_index": pi,
                       "domains": doms, "modes": ["observation"],
                       "reason": head + FILLER * (len(doms) or 1)})
    return out


def run(rows_by_batch: dict[str, list[dict]], corpus, spec) -> set[str]:
    r = accept.Report()
    gmap = accept.check_spec(spec, corpus, r)
    all_rows: dict[tuple[str, int], dict] = {}
    for b in accept.BATCH_IDS:
        got = accept.check_rows(b, rows_by_batch[b], spec, corpus, gmap, r)
        accept.check_anchors(spec, got, b, r)
        all_rows.update(got)
    accept.check_prose_rules(spec, all_rows, corpus, r)
    if len(all_rows) != len(corpus.para):
        r.fail("A1", f"共收 {len(all_rows)} 段，語料 {len(corpus.para)} 段")
    return r.codes()


def find(rows_by_batch, ch: str, pi: int) -> dict:
    for rows in rows_by_batch.values():
        for row in rows:
            if row["chapter"] == ch and row["para_index"] == pi:
                return row
    raise KeyError(f"{ch}[{pi}] 不在合成輸出裡")


# 每個 case 是 (案例名, 變異函式, 預期 FAIL 碼完整集合)
def build_cases() -> list[tuple[str, object, set[str]]]:
    def empty_anchor_filled(d):
        find(d, "越絕外傳記吳地傳第三", 2)["domains"] = ["V"]

    def auth_side_loses_xii(d):
        find(d, "越絕吳內傳第四", 19)["domains"] = ["V"]

    def breaking_side_gains_xii(d):
        find(d, "越絕計倪內經第五", 1)["domains"] = ["XI", "XII"]

    def tech_side_gains_xii(d):
        find(d, "越絕外傳記軍氣第十五", 2)["domains"] = ["XII"]

    def g4_hit_goes_empty(d):
        find(d, "越絕外傳記軍氣第十五", 1)["domains"] = []

    def rhetoric_side_goes_empty(d):
        find(d, "卷五", 1)["domains"] = []

    def x_side_loses_x(d):
        find(d, "越絕外傳記吳王占夢第十二", 3)["domains"] = ["V"]

    def x_tripwire_flattened(d):
        # [41] 判空、[25] 非空——配套 (2) 的三段判齊，必須被試金石咬住
        find(d, "越絕外傳記地傳第十", 41)["domains"] = []
        find(d, "越絕外傳記吳地傳第三", 25)["domains"] = ["X"]

    def illegal_domain(d):
        find(d, "越絕外傳記地傳第十", 2)["domains"] = ["Z-wisdom"]

    def worked_instance(d):
        find(d, "越絕計倪內經第五", 2)["modes"] = ["worked_instance"]

    def reason_too_short(d):
        row = find(d, "越絕外傳記地傳第十", 2)
        row["domains"] = ["V", "VII"]
        row["reason"] = "承重"

    def curly_quote(d):
        row = find(d, "越絕外傳記地傳第十", 2)
        row["reason"] = "“銳兵任死，越之常性也。”" + FILLER

    def foreign_literal(d):
        row = find(d, "越絕外傳記地傳第十", 2)
        row["reason"] = "「銳兵任死」是勾踐治下越人的常性。" + FILLER

    def spliced_quote(d):
        row = find(d, "越絕外傳記地傳第十", 41)
        row["reason"] = "「種將死，自策：後有賢者，百年而至」承重。" + FILLER

    def quote_from_jiazhu(d):
        # 本事第一[8] 自己是判空錨點，拿它下這一刀會先響 A2、A21 反而測不到；
        # 荊平王內傳第二[3] 沒有錨點，是這六處夾注裡乾淨的落點。
        row = find(d, "越絕荊平王內傳第二", 3)
        row["domains"] = ["II"]
        row["reason"] = "承重句是夾注的「一作「也」」。" + FILLER * 2

    def box_filled_in(d):
        # SPEC 底本事實 3：`□` 原樣帶著，不補字
        key = ("越絕德序外傳記第十八", 5)
        row = find(d, *key)
        src = accept.Corpus().para[key][1]
        i = src.index("□")
        row["reason"] = f"「{src[i - 3:i]}某{src[i + 1:i + 4]}」承重。" + FILLER

    def row_missing(d):
        d["b16"] = [x for x in d["b16"] if x["para_index"] != 3]

    def row_extra(d):
        d["b16"].append({"chapter": "越絕德序外傳記第十八", "para_index": 99,
                         "domains": [], "modes": ["observation"],
                         "reason": "多出來的一段。" + FILLER})

    def row_duplicated(d):
        d["b16"].append(copy.deepcopy(d["b16"][0]))

    return [
        ("判空錨點被填了領域", empty_anchor_filled, {"A2"}),
        ("認證側丟了 XII", auth_side_loses_xii, {"A3"}),
        ("破除側多了 XII", breaking_side_gains_xii, {"A4"}),
        ("技術側多了 XII", tech_side_gains_xii, {"A4"}),
        ("G4 登錄之外那段判空", g4_hit_goes_empty, {"A3", "A4"}),
        ("說辭側那段判空", rhetoric_side_goes_empty, {"A3", "A4"}),
        ("X 命中側丟了 X", x_side_loses_x, {"A3"}),
        ("配套 (2) 三段判齊", x_tripwire_flattened, {"A2", "A3", "A15"}),
        ("非法 domain id", illegal_domain, {"A3", "A11"}),
        ("出現 worked_instance", worked_instance, {"A12"}),
        ("標兩格但 reason 過短", reason_too_short, {"A13"}),
        ("reason 用了彎引號", curly_quote, {"A6"}),
        ("reason 出現《吳越春秋》字面", foreign_literal, {"A7"}),
        ("引句吞掉內層引號", spliced_quote, {"A20"}),
        ("承重引句落在夾注裡", quote_from_jiazhu, {"A21"}),
        ("reason 把闕字補掉", box_filled_in, {"A22"}),
        ("缺一段", row_missing, {"A1"}),
        ("多一段", row_extra, {"A1"}),
        ("同一段重複兩列", row_duplicated, {"A1"}),
    ]


def main() -> int:
    corpus = accept.Corpus()
    spec = accept.Spec(accept.SPEC_PATH)
    perfect = synth(corpus, spec)

    n = sum(len(v) for v in perfect.values())
    base = run(copy.deepcopy(perfect), corpus, spec)
    if base:
        print(f"合成的完美輸出沒有 0 FAIL（{n} 段）：{sorted(base)}")
        print("這代表 SPEC 的錨點彼此矛盾，或驗收器條件與配套說反了——照發包"
              "會把正確輸出判成 FAIL。")
        return 1
    print(f"完美輸出 {n} 段：0 FAIL\n")

    bad: list[str] = []
    for name, mutate, want in build_cases():
        d = copy.deepcopy(perfect)
        mutate(d)
        got = run(d, corpus, spec)
        if got == want:
            print(f"  OK   {name} -> {sorted(got)}")
        else:
            bad.append(f"{name}：預期 {sorted(want)}，實得 {sorted(got)}")
            print(f"  BAD  {name} —— 預期 {sorted(want)}，實得 {sorted(got)}")

    cases = build_cases()
    print(f"\n--- {len(cases) - len(bad)}/{len(cases)} 條變異拿到預期的完整 FAIL 集合 ---")
    for b in bad:
        print("BAD " + b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
