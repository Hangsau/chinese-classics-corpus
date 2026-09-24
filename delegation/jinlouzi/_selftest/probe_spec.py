#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""擾動探針：證明 accept.py 的 S 族斷言真的會叫。

每個案例擾動 SPEC.md 一處，宣告**完整**的 FAIL 碼集合，跑完還原。
收碼一律 in-process 讀 `check_spec()` 回傳的 Report，不 grep stdout
（自檢正常輸出就含 "FAIL" 字樣，`'FAIL' in out` 恆為真）。

Windows 陷阱：改寫 SPEC 一律走 read_bytes／write_bytes，
read_text／write_text 會把 LF 換成 CRLF，本庫 .gitattributes 強制 LF。

用法：PYTHONIOENCODING=utf-8 python _selftest/probe_spec.py
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import accept as A  # noqa: E402

SPEC = ROOT / "SPEC.md"

# (案名, 原文, 改成, 預期 FAIL 碼集合, 預期 NOTE 碼集合)
# 原文／改成可以是字串，也可以是等長的字串清單（一案要改多處時）。
# 每一處原文都必須在 SPEC 裡恰好出現一次，否則該案判 SKIP-BROKEN。
Text = str | list[str]
CASES: list[tuple[str, Text, Text, set[str], set[str]]] = [
    # -- S1 錨點段號不在語料 ------------------------------------------------
    ("S1 判空表段號越界",
     "| `興王篇一`[3] | `在位百二十年。` | b01 | G1 |",
     "| `興王篇一`[99] | `在位百二十年。` | b01 | G1 |",
     {"S1"}, set()),

    # -- S2 引句不在該段 ----------------------------------------------------
    ("S2 判空表引句改字",
     "| `興王篇一`[3] | `在位百二十年。` | b01 | G1 |",
     "| `興王篇一`[3] | `在位百三十年。` | b01 | G1 |",
     {"S2"}, set()),

    # -- S3 批號標錯 --------------------------------------------------------
    ("S3 判空表批號標錯",
     "| `興王篇一`[3] | `在位百二十年。` | b01 | G1 |",
     "| `興王篇一`[3] | `在位百二十年。` | b02 | G1 |",
     {"S3"}, set()),

    # -- S4 引句不唯一 ------------------------------------------------------
    ("S4 引句縮到不唯一",
     "| `興王篇一`[3] | `在位百二十年。` | b01 | G1 |",
     "| `興王篇一`[3] | `在位` | b01 | G1 |",
     {"S4"}, set()),

    # -- S5 判空表與命中表衝突 ----------------------------------------------
    ("S5 同一段同列判空與命中",
     "| `興王篇一`[3] | `在位百二十年。` | b01 | G1 |",
     "| `興王篇一`[9] | `在位百二十年。` | b01 | G1 |",
     {"S2", "S5"}, set()),

    # -- S6 必含與禁格互相抵銷 ----------------------------------------------
    ("S6 禁格改成該段的必含格",
     "| `志怪篇十二`[22] | `桓公與管仲闔門而謀伐莒，未發而已聞於國。"
     "桓公怒，管仲曰：「國必有聖人。」` | b16 | G6 | XII |",
     "| `志怪篇十二`[22] | `桓公與管仲闔門而謀伐莒，未發而已聞於國。"
     "桓公怒，管仲曰：「國必有聖人。」` | b16 | G6 | XI |",
     {"S6", "S12"}, set()),

    # -- S7 群標籤與分派表不符 ----------------------------------------------
    ("S7 錨點群標籤改錯",
     "| `興王篇一`[3] | `在位百二十年。` | b01 | G1 |",
     "| `興王篇一`[3] | `在位百二十年。` | b01 | G2 |",
     {"S7"}, set()),

    # -- S8 分派表段數寫錯 --------------------------------------------------
    ("S8 分派表 G1 段數改錯",
     "| G1 帝王譜系 | 興王篇一 | b01 b02 b03 | 1／21 |",
     "| G1 帝王譜系 | 興王篇一 | b01 b02 b03 | 1／22 |",
     {"S8"}, set()),

    # -- S9 批次表段數寫錯 --------------------------------------------------
    ("S9 批次表 b01 段數改錯",
     "| b01 | 11 |",
     "| b01 | 12 |",
     {"S9", "S10"}, set()),

    # -- S10 A 類散文逐批段數與批次表漂移 ------------------------------------
    ("S10 A類1 散文 b01 段數改錯",
     "b01 11／b02 9",
     "b01 12／b02 9",
     {"S10"}, set()),

    # -- S11 宣告段數與表列不符 ----------------------------------------------
    ("S11 判空宣告段數改錯",
     "「必須判空」表列的 128 段",
     "「必須判空」表列的 127 段",
     {"S11"}, set()),
    ("S11 必含格宣告條數改錯",
     "必含格 25 條全部滿足",
     "必含格 24 條全部滿足",
     {"S11"}, set()),

    # -- S12 散文清單與表格漂移 ----------------------------------------------
    ("S12 A類6 散文刪掉一條禁格",
     "`興王篇一`[9] 不得含 IX；",
     "",
     {"S12"}, set()),

    # -- S13 id 表被動過 ----------------------------------------------------
    ("S13 mode 表改 id",
     "| `worked_instance` |",
     "| `worked_example` |",
     {"S13"}, set()),

    # -- S14 G5 兩側段數宣告改錯 ---------------------------------------------
    ("S14 G5 登錄側段數改錯",
     "`著書篇十`[1]–[37]，共 41 段",
     "`著書篇十`[1]–[37]，共 42 段",
     {"S14"}, set()),

    # -- S15 批次沒有錨點覆蓋（NOTE 族，墨子型整族停擺的護欄）-----------------
    # b03 只有一段、掛兩條錨點，要整批失去覆蓋就得兩條一起挪；
    # 挪批號必然同時觸發 S3，照「完整碼集合」原則一起宣告。
    ("S15 b03 兩條錨點都挪走（整批失去覆蓋）",
     ["`伏尋我皇之爲孝也，四運推移，不以榮落遷貿；五德更用，不以貴賤革心。` | b03 |",
      "`望宅奉諱，氣絶良久。旣葬，嘔血數升，水漿不入口者四日，"
      "憂服之內，不復嘗米，所資麤麥，日中二溢。` | b03 |"],
     ["`伏尋我皇之爲孝也，四運推移，不以榮落遷貿；五德更用，不以貴賤革心。` | b02 |",
      "`望宅奉諱，氣絶良久。旣葬，嘔血數升，水漿不入口者四日，"
      "憂服之內，不復嘗米，所資麤麥，日中二溢。` | b02 |"],
     {"S3"}, {"S15"}),

    # -- S16 灰區三個數量（晏子型局部失明的護欄）-----------------------------
    ("S16 灰區 bullet 宣告數改錯",
     "本節共 89 條",
     "本節共 88 條",
     {"S16"}, set()),
    ("S16 灰區指名段落 bullet 數改錯",
     "其中 81 條指名段落",
     "其中 80 條指名段落",
     {"S16"}, set()),
    ("S16 灰區相異段數改錯",
     "合計 123 個相異段",
     "合計 122 個相異段",
     {"S16"}, set()),
    ("S16 灰區指名不存在的段",
     "- `箴戒篇一`[58] 何美人之死",
     "- `箴戒篇一`[99] 何美人之死",
     {"S16"}, set()),
]


def codes(text: str) -> tuple[set[str], set[str]]:
    SPEC.write_bytes(text.encode("utf-8"))
    corpus = A.Corpus(ROOT)
    spec = A.Spec(SPEC, corpus.chapter_order)
    r = A.check_spec(spec, corpus)
    return r.codes(), r.note_codes()


def main() -> int:
    orig = SPEC.read_bytes()
    digest = hashlib.sha256(orig).hexdigest()
    base = orig.decode("utf-8")

    bad = 0
    try:
        f, n = codes(base)
        if f or n:
            print(f"BASE 不乾淨：FAIL={sorted(f)} NOTE={sorted(n)}")
            return 1
        print("BASE 0 FAIL / 0 NOTE")

        for name, old, new, want_f, want_n in CASES:
            reps = list(zip(old, new)) if isinstance(old, list) else [(old, new)]
            miss = [o for o, _ in reps if base.count(o) != 1]
            if miss:
                print(f"SKIP-BROKEN {name}：錨定字串出現次數不是 1"
                      f"（{[base.count(o) for o in miss]}）")
                bad += 1
                continue
            mutated = base
            for o, n2 in reps:
                mutated = mutated.replace(o, n2, 1)
            got_f, got_n = codes(mutated)
            ok = got_f == want_f and got_n == want_n
            print(f"{'PASS' if ok else 'FAIL'} {name}"
                  f"  FAIL={sorted(got_f)} NOTE={sorted(got_n)}")
            if not ok:
                print(f"     預期 FAIL={sorted(want_f)} NOTE={sorted(want_n)}")
                bad += 1
    finally:
        SPEC.write_bytes(orig)

    if hashlib.sha256(SPEC.read_bytes()).hexdigest() != digest:
        print("SPEC 還原後位元組不符！")
        return 1
    print(f"SPEC 位元組已還原（{digest[:12]}）")
    print(f"{len(CASES)} 案，{bad} 不合預期")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
