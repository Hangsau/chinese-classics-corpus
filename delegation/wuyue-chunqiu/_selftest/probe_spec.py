#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""擾動探針：證明 accept.py --check-spec 的每一族斷言真的會叫。

`0 FAIL` 本身不是通過條件——本庫已經三次被靜默失效騙過（墨子 regex 咬到後來
被改掉的散文、晏子 S11 只驗「至少解析到一條」、文心 A14 的 require_m 正向永不
觸發）。本檔對 SPEC.md 逐條下毒，跑一次 --check-spec，確認冒出預期的 FAIL 代碼；
沒冒出來就代表那族斷言是死的。

每個 case 跑完立刻還原 SPEC.md。**一律用 read_bytes/write_bytes**——Windows 上
read_text/write_text 會把 LF 轉成 CRLF，.gitattributes 強制 LF 是為了保護底本
SHA-256，探針不可以是弄髒 working tree 的那個人。

用法:
    python _selftest/probe_spec.py
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
PKG = HERE.parent
SPEC = PKG / "SPEC.md"
ACCEPT = PKG / "accept.py"

# (案例名, 原字串, 毒化字串, 預期 FAIL 代碼)
CASES: list[tuple[str, str, str, str]] = [
    ("S1 錨點表標題被改名",
     "### 認證側（4 段，必含 XII）",
     "### 認證組（4 段，必含 XII）", "S1"),

    ("S2 標題宣告段數與表列數不符",
     "### 技術側（4 段，非空但一格都不得填 XII）",
     "### 技術側（5 段，非空但一格都不得填 XII）", "S2"),

    ("S2 X 兩側粗體宣告段數不符",
     "**命中側（4 段，必含 X）：**",
     "**命中側（5 段，必含 X）：**", "S2"),

    ("S3 錨點段號指到不存在的段",
     "| `勾踐十年`[19] |",
     "| `勾踐十年`[99] |", "S3"),

    ("S3 錨點引句對不上原文",
     "「乃行第一術，立東郊以祭陽，名曰東皇公，立西郊以祭陰，名曰西王母」",
     "「乃行第一術，立東郊以祭陽，名曰東皇君，立西郊以祭陰，名曰西王母」", "S3"),

    ("S3 錨點批次寫錯",
     "| `越王勾踐五年`[26] | 「候天察地，紀歷陰陽，觀變參災，分別妖祥，"
     "日月含色，五精錯行，福見知吉，妖出知兇：臣之事也」 | b03 |",
     "| `越王勾踐五年`[26] | 「候天察地，紀歷陰陽，觀變參災，分別妖祥，"
     "日月含色，五精錯行，福見知吉，妖出知兇：臣之事也」 | b07 |", "S3"),

    ("S3 錨點體例群寫錯",
     "| `吳太伯傳`[1] | 「姜嫄怪而棄于阨狹之巷，牛馬過者折易而避之」 | b06 | G2 |",
     "| `吳太伯傳`[1] | 「姜嫄怪而棄于阨狹之巷，牛馬過者折易而避之」 | b06 | G1 |", "S3"),

    ("S4 同一段出現在兩張錨點表",
     "| `壽夢二十五年`[2] | 「我欲傳國季札，爾無忘寡人之言」 | b06 |",
     "| `勾踐十年`[19] | 「乃行第一術，立東郊以祭陽」 | b06 |", "S4"),

    ("S5 A 類條文的批次段數被改錯",
     "b01 12／b02 87／b03 45",
     "b01 12／b02 88／b03 45", "S5"),

    ("S5 批次表章名與 MANIFEST 不符",
     "| b05 | 42 | 2602 | 勾踐十三年 |",
     "| b05 | 42 | 2602 | 勾踐十四年 |", "S5"),

    ("S6 章被分派到錯的群",
     "| G4 譜系神話 | 第006卷 | b10 | 1／26 | §2.3 |",
     "| G4 譜系神話 | 第006卷 佚文 | b10 | 2／38 | §2.3 |", "S6"),

    ("S6 群的章／段宣告數字錯",
     "| G3 繫年條目 | 壽夢元年 壽夢二年 壽夢十六年 壽夢十七年 壽夢二十五年 "
     "諸樊元年 餘祭十二年 餘祭十三年 餘祭十七年 | b06 | 9／15 |",
     "| G3 繫年條目 | 壽夢元年 壽夢二年 壽夢十六年 壽夢十七年 壽夢二十五年 "
     "諸樊元年 餘祭十二年 餘祭十三年 餘祭十七年 | b06 | 9／16 |", "S6"),

    ("S7 異體字次數宣告錯",
     "`為`（全書 361 次",
     "`為`（全書 360 次", "S7"),

    ("S7 全書引號總數宣告錯",
     "`「` 440 `」` 440、`“` 329 `”` 326",
     "`「` 440 `」` 440、`“` 330 `”` 326", "S7"),

    ("S8 A 類條文段數與錨點表列數脫鉤",
     "**認證側 4 段全部含 XII。**",
     "**認證側 3 段全部含 XII。**", "S8"),

    ("S9 領域表少一列",
     "| XIII | 安頓·修復·平安 | 受苦之後如何自處（勾踐居臣期的自處） |\n",
     "", "S9"),

    ("S10 提到語料不存在的章名",
     "- **`勾踐十年`[18] 九術**",
     "- **`勾踐九年`[18] 九術**", "S10"),

    ("S11 引號體例把批次分到錯的家族",
     "`“ ”`：b02 b03 b04 b05 b10",
     "`“ ”`：b02 b03 b04 b05 b09", "S11"),

    ("S12 試金石正例不在認證側表",
     "**`勾踐十年`[19] 含 XII；`越王勾踐五年`[26] 非空且不含 XII。**",
     "**`勾踐十三年`[26] 含 XII；`越王勾踐五年`[26] 非空且不含 XII。**", "S12"),

    ("S13 裸年號章清單含不存在的章",
     "六章裸年號（十一年 十二年 十三年 十四年 二十年 二十三年）",
     "六章裸年號（十一年 十二年 十三年 十四年 二十年 二十四年）", "S13"),

    ("S14 錨點表沒有 A 類條文引用",
     "（表：**G4 登錄之外**。）", "。", "S14"),

    ("S15 硬斷行段全表列了不是 30 字的段",
     "`十三年`[53]", "`十三年`[52]", "S15"),

    ("S15 硬斷行段全表宣告總數錯",
     "**硬斷行段全表（35 段）**：",
     "**硬斷行段全表（36 段）**：", "S15"),

    # --- 停跑偵測：條文被整段刪掉時，斷言族必須自己喊停，不可靜默通過 ---

    ("停跑 硬斷行段全表標記被刪",
     "**硬斷行段全表（35 段）**：", "", "S15"),

    ("停跑 A 類批次段數條文被刪",
     "（b01 12／b02 87／b03 45／b04 65／b05 42／b06 25／b07 66／b08 65／"
     "b09 60／b10 26，合計 493）", "", "S5"),

    ("停跑 試金石條文被刪",
     "**`勾踐十年`[19] 含 XII；`越王勾踐五年`[26] 非空且不含 XII。**", "", "S12"),

    ("停跑 裸年號條文被刪",
     "16. **六章裸年號（十一年 十二年 十三年 十四年 二十年 二十三年）"
     "各自第 1 段的 `reason` 必須出現「夫差」。**", "", "S13"),
]


def run_check() -> str:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, str(ACCEPT), "--check-spec"],
                       cwd=str(PKG), capture_output=True, text=True,
                       encoding="utf-8", env=env)
    return (p.stdout or "") + (p.stderr or "")


def main() -> int:
    original = SPEC.read_bytes()

    baseline = run_check()
    if "0 FAIL" not in baseline:
        print("探針無法起跑：未毒化的 SPEC 本來就不是 0 FAIL")
        print(baseline)
        return 1
    print("baseline: 0 FAIL ✓\n")

    dead: list[str] = []
    try:
        for name, old, new, code in CASES:
            raw = original.decode("utf-8")
            if raw.count(old) == 0:
                dead.append(f"{name}：毒化目標字串在 SPEC 裡找不到（探針自己過期了）")
                print(f"  SKIP {name} —— 目標字串不存在")
                continue
            poisoned = raw.replace(old, new, 1)
            SPEC.write_bytes(poisoned.encode("utf-8"))
            out = run_check()
            if f"[{code}]" in out:
                print(f"  OK   {name} -> {code}")
            else:
                dead.append(f"{name}：預期 {code}，實際沒叫")
                print(f"  DEAD {name} —— 預期 {code} 沒出現")
    finally:
        SPEC.write_bytes(original)

    after = run_check()
    if "0 FAIL" not in after:
        print("\n還原後 SPEC 不是 0 FAIL——探針弄髒了檔案")
        print(after)
        return 1

    print(f"\n--- {len(CASES) - len(dead)}/{len(CASES)} 族斷言確認會叫 ---")
    for d in dead:
        print("DEAD " + d)
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main())
