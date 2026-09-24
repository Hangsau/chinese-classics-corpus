#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""合成「完美輸出」＋注入變異，驗 accept.py 的 A 族斷言。

先由 SPEC 的判空／命中／禁格三表合成一份全書輸出，跑一次應得 0 FAIL；
再逐案注入變異，每案宣告**完整**的 FAIL 碼集合（不是「至少含」），
一次跑完自己對答案，不靠人工比對輸出。

用法：
    PYTHONIOENCODING=utf-8 python _selftest/make_cases.py --verify
    PYTHONIOENCODING=utf-8 python _selftest/make_cases.py --dump DIR
"""
from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import accept as A  # noqa: E402

PAD = "（合成案例，湊足 reason 長度門檻）"


def synth(spec: A.Spec, corpus: A.Corpus) -> dict[str, dict]:
    """由三張錨點表合成全書輸出；預設判空，命中錨點填其必含格。"""
    null_keys = {a.key for a in spec.null}
    forbid = {}
    for a in spec.forbid:
        if isinstance(a.domain, str):
            forbid.setdefault(a.key, set()).add(a.domain)

    want: dict[tuple[str, int], list[str]] = {}
    for a in spec.hit:
        if isinstance(a.domain, str):
            want.setdefault(a.key, [])
            if a.domain not in want[a.key]:
                want[a.key].append(a.domain)
        else:
            want.setdefault(a.key, [])

    out: dict[str, dict] = {}
    for key, (batch, text) in sorted(corpus.para.items()):
        doms: list[str] = []
        if key in want and key not in null_keys:
            doms = list(want[key])
            if not doms:
                # 命中錨點沒指定格：挑一個不被該段禁掉的合法格
                doms = [d for d in A.DOMAIN_IDS
                        if d not in forbid.get(key, set())][:1]
        reason = text[:40] + PAD * 3
        out.setdefault(batch, {"batch": batch, "rows": []})
        out[batch]["rows"].append({
            "chapter": key[0],
            "para_index": key[1],
            "domains": doms,
            "modes": ["narrative"],
            "reason": reason,
        })
    return out


def run(bundle: dict[str, dict], spec: A.Spec,
        corpus: A.Corpus) -> tuple[set[str], set[str]]:
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        for batch, obj in bundle.items():
            (d / f"{batch}.json").write_bytes(
                json.dumps(obj, ensure_ascii=False).encode("utf-8"))
        r = A.Report()
        rows: list[dict] = []
        for p in sorted(d.glob("b*.json")):
            rows += A.check_batch(p, spec, corpus, r)
        A.check_cross(rows, spec, corpus, r)
    return r.codes(), r.note_codes()


# --------------------------------------------------------------------------
# 變異：每個 mutate(bundle) 就地改一處，回傳案名
# --------------------------------------------------------------------------

def row_of(bundle: dict, chapter: str, idx: int) -> dict:
    for obj in bundle.values():
        for row in obj["rows"]:
            if row["chapter"].startswith(chapter) and row["para_index"] == idx:
                return row
    raise KeyError(f"{chapter}[{idx}]")


def build_cases(spec: A.Spec, corpus: A.Corpus) -> list[tuple]:
    null0 = spec.null[0]
    hit_named = next(a for a in spec.hit if isinstance(a.domain, str))
    fb = spec.forbid[0]
    chu = A.resolve_chapter("著書篇十", corpus)
    sides = spec.g5_sides()
    reg = [(A.resolve_chapter(c, corpus), i) for c, i in sides["registry"]]
    null_keys = {a.key for a in spec.null}
    free_reg = [k for k in reg if k not in null_keys]

    def m_a3(b):
        row_of(b, A.short(null0.chapter), null0.para_index)["domains"] = ["V"]

    def m_a4(b):
        row_of(b, A.short(hit_named.chapter),
               hit_named.para_index)["domains"] = []

    def m_a5(b):
        row = row_of(b, A.short(hit_named.chapter), hit_named.para_index)
        row["domains"] = ["I" if hit_named.domain != "I" else "II"]

    def m_a6(b):
        row = row_of(b, A.short(fb.chapter), fb.para_index)
        row["domains"] = sorted(set(row["domains"]) | {fb.domain})

    def m_a1_short(b):
        row = row_of(b, "著書篇十", 1)
        row["chapter"] = "著書篇十"

    def m_a1_missing(b):
        obj = b["b01"]
        obj["rows"] = obj["rows"][1:]

    def m_a1_alien(b):
        b["b01"]["rows"][0]["para_index"] = 999

    def m_a12_bad(b):
        b["b01"]["rows"][0]["domains"] = ["XIV"]

    def m_a12_dup(b):
        b["b01"]["rows"][0]["domains"] = ["V", "V"]

    def m_a11(b):
        b["b01"]["rows"][0]["modes"] = ["worked_instance"]

    def m_a14(b):
        b["b01"]["rows"][0]["reason"] = "這條理由完全是複述規格用語，沒有引到本段任何文字。"

    def m_a13(b):
        row = row_of(b, A.short(hit_named.chapter), hit_named.para_index)
        row["reason"] = "太短"

    def m_a8(b):
        row_of(b, "著書篇十", 43)["domains"] = []

    def m_a9(b):
        for k in free_reg:
            row_of(b, A.short(k[0]), k[1])["domains"] = ["V"]

    def m_a0(b):
        b["b01"]["batch"] = "b02"

    def m_a10(b):
        row_of(b, "聚書篇六", 1)["modes"] = ["formalization"]

    return [
        ("A3 判空錨點被標格", m_a3, {"A3"}, set()),
        ("A4 命中錨點被判空", m_a4, {"A4"}, set()),
        ("A5 必含格被換掉", m_a5, {"A5"}, set()),
        ("A6 禁格被填", m_a6, {"A6"}, set()),
        ("A1 章名被截短", m_a1_short, {"A1"}, set()),
        ("A1 少一列（該段沒被收到，連帶 B1）", m_a1_missing, {"A1"}, {"B1"}),
        ("A1 段號不存在（原段落失收，連帶 B1）", m_a1_alien, {"A1"}, {"B1"}),
        ("A12 非法 domain", m_a12_bad, {"A12"}, set()),
        ("A12 domains 重複值", m_a12_dup, {"A12"}, set()),
        ("A11 出現 worked_instance", m_a11, {"A11"}, set()),
        ("A14 reason 不引本段", m_a14, {"A14"}, set()),
        ("A13 reason 過短（必然連帶 A14，8 字窗放不進去）",
         m_a13, {"A13", "A14"}, set()),
        ("A8 著書篇十[38][43] 不同判（必然連帶 A4）", m_a8, {"A4", "A8"}, set()),
        ("A9 G5 兩側被合併判", m_a9, {"A9"}, set()),
        ("A0 batch 欄與檔名不符（列身分改對 b02 比，連帶 A1／B1）",
         m_a0, {"A0", "A1"}, {"B1"}),
        ("A10 書目著錄填 formalization", m_a10, {"A10"}, set()),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--dump", metavar="DIR")
    args = ap.parse_args()

    corpus = A.Corpus(ROOT)
    spec = A.Spec(A.SPEC_PATH, corpus.chapter_order)
    base = synth(spec, corpus)

    if args.dump:
        d = pathlib.Path(args.dump)
        d.mkdir(parents=True, exist_ok=True)
        for batch, obj in base.items():
            (d / f"{batch}.json").write_bytes(
                json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8"))
        print(f"已寫出 {len(base)} 批到 {d}")
        if not args.verify:
            return 0

    f, n = run(base, spec, corpus)
    if f:
        print(f"完美輸出不乾淨：FAIL={sorted(f)} NOTE={sorted(n)}")
        return 1
    print(f"完美輸出 0 FAIL（NOTE={sorted(n)}）")

    bad = 0
    for name, mutate, want_f, want_n in build_cases(spec, corpus):
        b = copy.deepcopy(base)
        mutate(b)
        got_f, got_n = run(b, spec, corpus)
        ok = got_f == want_f and got_n == want_n
        print(f"{'PASS' if ok else 'FAIL'} {name}"
              f"  FAIL={sorted(got_f)} NOTE={sorted(got_n)}")
        if not ok:
            print(f"     預期 FAIL={sorted(want_f)} NOTE={sorted(want_n)}")
            bad += 1
    print(f"{len(build_cases(spec, corpus))} 案，{bad} 不合預期")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
