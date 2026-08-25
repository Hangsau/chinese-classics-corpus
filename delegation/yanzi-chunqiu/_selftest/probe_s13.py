#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SPEC 擾動探針：證明 --check-spec 的每一族斷言真的活著。

驗收器凡是用字面 regex 去咬 SPEC 散文的地方，SPEC 一改就可能斷，
而斷掉的表現是**更綠**不是報錯（墨子事故）。做法：
逐條擾動 SPEC 的宣告值 → 確認對應斷言真的會叫 → 還原 → 確認 SPEC 位元組不變。

Windows 陷阱：一律走 read_bytes／write_bytes，read_text／write_text
會把 LF 換成 CRLF，本庫 .gitattributes 強制 LF。

用法:
    python _selftest/probe_s13.py
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
BOOK = HERE.parent
sys.path.insert(0, str(BOOK))

from accept import Corpus, Spec, check_spec  # noqa: E402

SPEC_PATH = BOOK / "SPEC.md"

# (名稱, 期望觸發的碼, 原字串, 換成)
CASES: list[tuple[str, str, str, str]] = [
    ("破除側區段標題被改名", "S1",
     "### 破除側（8 段，必含 XI 且不得含 XII）",
     "### 破除甲（8 段，必含 XI 且不得含 XII）"),
    ("破除側標題段數 8→9", "S2",
     "### 破除側（8 段，必含 XI 且不得含 XII）",
     "### 破除側（9 段，必含 XI 且不得含 XII）"),
    ("X 兩側標題命中 3→4", "S2",
     "### X 的兩側（命中 3 段必含 X；判空側 2 段必須非空但不得含 X）",
     "### X 的兩側（命中 4 段必含 X；判空側 2 段必須非空但不得含 X）"),
    # 引句在配套 (1) 的散文裡也出現一次，錨字串要用整列才唯一
    ("錨點引句改一字", "S3",
     "| `景公欲祠靈山河伯以禱雨晏子諫第十五`[1] | 「彼獨不欲雨乎？祠之何益？」 | b01 | 諫上 |",
     "| `景公欲祠靈山河伯以禱雨晏子諫第十五`[1] | 「彼獨不欲雨乎？祭之何益？」 | b01 | 諫上 |"),
    ("錨點卷別被改掉", "S3",
     "| `景公欲使楚巫致五帝以明德晏子諫第十四`[1] | 「古者不慢行而繁祭，不輕身而恃巫」 | b01 | 諫上 |",
     "| `景公欲使楚巫致五帝以明德晏子諫第十四`[1] | 「古者不慢行而繁祭，不輕身而恃巫」 | b01 | 雜上 |"),
    ("錨點批次被改掉", "S3",
     "| `景公欲祠靈山河伯以禱雨晏子諫第十五`[1] | 「彼獨不欲雨乎？祠之何益？」 | b01 | 諫上 |",
     "| `景公欲祠靈山河伯以禱雨晏子諫第十五`[1] | 「彼獨不欲雨乎？祠之何益？」 | b03 | 諫上 |"),
    ("批次表 b01 25→26", "S5",
     "| b01 | 25 | 25 | 諫上（全） |",
     "| b01 | 26 | 25 | 諫上（全） |"),
    ("A 類第 1 條 b01 25→26", "S5",
     "（b01 25／b02 33／b03 35／b04 29／b05 39／b06 41／b07 16，合計 218）",
     "（b01 26／b02 33／b03 35／b04 29／b05 39／b06 41／b07 16，合計 218）"),
    ("卷結構表 諫上 25→24 章", "S6",
     "| 1 | 諫上 | G1 | 25 | 25 | b01 第一–第二十五 |",
     "| 1 | 諫上 | G1 | 24 | 25 | b01 第一–第二十五 |"),
    ("兩章多段標題 213→212", "S7",
     "### 兩章多段，其餘 213 章各 1 段",
     "### 兩章多段，其餘 212 章各 1 段"),
    ("A 類第 3 條 8→7", "S8b",
     "3. **破除側 8 段全部含 XI 且全部不含 XII。**",
     "3. **破除側 7 段全部含 XI 且全部不含 XII。**"),
    ("A 類第 8 條 X 命中側 3→4", "S8f",
     "8. **X 命中側 3 段全部含 X。**",
     "8. **X 命中側 4 段全部含 X。**"),
    ("底本事實 為 466→467", "S9",
     "`為` 466 次", "`為` 467 次"),
    ("章名逗號 26→25", "S9",
     "**26 個含全形逗號**", "**25 個含全形逗號**"),
    ("章名總數 215→214", "S9",
     "215 個章名中", "214 個章名中"),
    ("領域表刪掉 XIII 一列", "S10",
     "| XIII | 安頓·修復·平安 |", "| XIII-x | 安頓·修復·平安 |"),
    ("mode id 被改名", "S10",
     "| `worked_instance` | ", "| `worked_example` | "),
    ("灰區 bullet 格式被改", "S11",
     "- `景公謂晏子，東海之中有水而赤，晏子詳對第十三`[1]（b05）",
     "- 景公謂晏子，東海之中有水而赤，晏子詳對第十三 [1] (b05) "),
    ("reason 長度係數格式被改", "S12",
     "`reason` 長度不得少於 N × 20 字元",
     "`reason` 長度不得少於 N 的二十倍字元"),
    ("試金石條文被改寫", "S13",
     "6. **`景公將伐宋瞢二丈夫立而怒晏子諫第二十二`[1] 含 XII；"
     "`景公使祝史禳彗星晏子諫第六`[1] 含 XI 不含 XII。**",
     "6. **前者含 XII、後者含 XI 不含 XII。**"),
]


def codes(raw_bytes: bytes, corpus: Corpus) -> set[str]:
    SPEC_PATH.write_bytes(raw_bytes)
    rep = check_spec(Spec(SPEC_PATH), corpus)
    return {re.match(r"\[(\w+)\]", f).group(1) for f in rep.fails}


def main() -> int:
    original = SPEC_PATH.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    corpus = Corpus(BOOK)

    try:
        base = codes(original, corpus)
        if base:
            print(f"未擾動的 SPEC 就有 FAIL {sorted(base)}，先修乾淨再跑探針")
            return 1
        print("未擾動：0 FAIL\n")

        bad = 0
        for name, want, old, new in CASES:
            if original.count(old.encode("utf-8")) != 1:
                n = original.count(old.encode("utf-8"))
                print(f"BAD  {name:<24} 錨字串在 SPEC 出現 {n} 次（需剛好 1 次）")
                bad += 1
                continue
            got = codes(original.replace(old.encode("utf-8"),
                                         new.encode("utf-8")), corpus)
            ok = want in got
            bad += 0 if ok else 1
            print(f"{'OK  ' if ok else 'BAD '}{name:<24} 期望 {want} 有叫  "
                  f"實得 {sorted(got) if got else '（全綠——斷言已停跑）'}")
    finally:
        SPEC_PATH.write_bytes(original)

    after = SPEC_PATH.read_bytes()
    same = hashlib.sha256(after).hexdigest() == digest
    print(f"\nSPEC 還原：{'位元組相同' if same else '位元組不同——已損毀，立刻 git checkout'}")
    print(f"{len(CASES)} 條擾動，{bad} 條沒叫")
    return 0 if bad == 0 and same else 1


if __name__ == "__main__":
    sys.exit(main())
