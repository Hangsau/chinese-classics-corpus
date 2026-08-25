#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文心雕龍 標註驗收器。

錨點一律由本檔現場解析 SPEC.md 的表格與條文，不在程式裡手抄任何章名、段號或引句。

用法:
    python accept.py --check-spec              # 只驗規格本身（發包前必跑到 0 FAIL / 0 NOTE）
    python accept.py out/b01.json [...]        # 驗回收的批次輸出
    python accept.py --all                     # 驗 out/ 底下全部批次（含全書級條件）
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).resolve().parent
SPEC_PATH = HERE / "SPEC.md"
OUT_DIR = HERE / "out"

DOMAIN_IDS = ["I", "II", "III", "IV", "V", "VI", "VII",
              "VIII", "IX", "X", "XI", "XII", "XIII"]
MODE_IDS = ["observation", "proposition", "prescription", "formalization",
            "narrative", "ritual", "expression", "worked_instance"]

GROUP_IDS = ["G1", "G2", "G2′", "G3", "G4", "G5", "G6"]
SUBGROUPS = ["G3技", "G3人"]

# 贊語的機械定義：每章末兩段中長度 ≤ 48 字者。實測 101 段（50 章各 2 段 ＋ 諧隱 1 段）。
ZAN_MAXLEN = 48

_ROMAN_RE = re.compile(
    r"(?<![A-Za-z])(XIII|XII|XI|IX|VIII|VII|VI|IV|III|II|X|V|I)(?![A-Za-z])")

# 每張錨點表的語意。key 是標題子字串 + 該標題下的第幾張表。
# 只描述「這張表是什麼意思」，段數與成員一律由 SPEC 現場解析。
SECTION_SEMANTICS = {
    ("必須判空的錨點", 0): {"empty": True, "quote": False},
    ("XII 四側", 0): {"quote": True},
    ("G1 文之樞紐", 0): {"quote": True},
    ("G2 文體論", 0): {"quote": True},
    ("G3 創作論", 0): {"quote": True},
    ("G4 批評論", 0): {"quote": True},
    ("G5 自序", 0): {"quote": True},
}

SECTION_CODE = {
    "必須判空的錨點": "A3",
    "XII 四側": "A5",
    "G1 文之樞紐": "A9",
    "G2 文體論": "A10",
    "G3 創作論": "A12",
    "G4 批評論": "A13",
    "G5 自序": "A14",
}


class Report:
    def __init__(self) -> None:
        self.fails: list[str] = []
        self.notes: list[str] = []

    def fail(self, code: str, msg: str) -> None:
        self.fails.append(f"[{code}] {msg}")

    def note(self, code: str, msg: str) -> None:
        self.notes.append(f"[{code}] {msg}")

    def codes(self) -> set[str]:
        return {f.split("]")[0].lstrip("[") for f in self.fails}

    def ok(self) -> bool:
        return not self.fails

    def dump(self, title: str) -> None:
        print(f"=== {title} ===")
        for f in self.fails:
            print("FAIL " + f)
        for n in self.notes:
            print("NOTE " + n)
        print(f"{len(self.fails)} FAIL / {len(self.notes)} NOTE")


# --------------------------------------------------------------------------
# 語料
# --------------------------------------------------------------------------

class Corpus:
    """delegation/wenxin-diaolong/bNN.md 是段落文字與批次歸屬的唯一真相。"""

    def __init__(self, root: pathlib.Path) -> None:
        self.para: dict[tuple[str, int], tuple[str, str]] = {}
        self.chapters: list[tuple[str, str, int]] = []   # (batch, chapter, n_para)
        for f in sorted(root.glob("b0*.md")):
            text = f.read_bytes().decode("utf-8")
            cur = None
            for line in text.split("\n"):
                m = re.match(r"^## (.+?)（(\d+) 段）$", line)
                if m:
                    cur = m.group(1)
                    self.chapters.append((f.stem, cur, int(m.group(2))))
                    continue
                m2 = re.match(r"^\[(\d+)\] (.*)$", line)
                if m2 and cur:
                    self.para[(cur, int(m2.group(1)))] = (f.stem, m2.group(2))
        if not self.para:
            raise SystemExit("讀不到 bNN.md，語料為空")

        self.chapter_size = {ch: n for _b, ch, n in self.chapters}
        self.chapter_batch = {ch: b for b, ch, _n in self.chapters}
        self.batch_size = Counter(v[0] for v in self.para.values())
        self.batch_chapters = defaultdict(list)
        for b, ch, _n in self.chapters:
            self.batch_chapters[b].append(ch)
        self.all_text = "".join(v[1] for v in self.para.values())

        self.zan: set[tuple[str, int]] = set()
        for _b, ch, n in self.chapters:
            for i in (n - 1, n):
                if i >= 1 and len(self.para[(ch, i)][1]) <= ZAN_MAXLEN:
                    self.zan.add((ch, i))

    def quote_hits(self, quote: str) -> list[tuple[str, int]]:
        return [k for k, v in self.para.items() if quote in v[1]]

    def quote_ok(self, quote: str, key: tuple[str, int]) -> tuple[bool, bool]:
        """回傳 (在本段, 全書唯一)。`……` 與 `」「` 節引逐段比。"""
        frags = [f for f in re.split(r"……|」「", quote) if f]
        text = self.para[key][1]
        inside = all(f in text for f in frags)
        unique = all(len(self.quote_hits(f)) == 1 for f in frags)
        return inside, unique


# --------------------------------------------------------------------------
# SPEC 解析
# --------------------------------------------------------------------------

def _strip_parens(cell: str) -> str:
    prev, out = None, cell
    while prev != out:
        prev = out
        out = re.sub(r"（[^（）]*）", "", out)
    return out


def parse_requirement(cell: str):
    """把條件欄解析成 (require_groups, forbid_domains, forbid_modes)。

    require_groups 是 set 的 list，每個 set 代表「至少含其中一個」。
    """
    body = _strip_parens(cell)
    body = body.replace("*", "").replace("`", "").replace("「", "").replace("」", "")
    require: list[set[str]] = []
    require_m: set[str] = set()
    forbid_d: set[str] = set()
    forbid_m: set[str] = set()
    for clause in re.split(r"[，；]|且", body):
        clause = clause.strip()
        if not clause:
            continue
        doms = _ROMAN_RE.findall(clause)
        modes = [m for m in MODE_IDS if m in clause]
        negative = ("不得含" in clause) or ("不得填" in clause) or ("不含" in clause)
        if negative:
            forbid_d.update(doms)
            forbid_m.update(modes)
        else:
            if doms:
                require.append(set(doms))
            if modes and "必含" in clause:
                require_m.update(modes)
    return require, require_m, forbid_d, forbid_m


class Anchor:
    __slots__ = ("chapter", "para_index", "quote", "batch",
                 "require", "require_m", "forbid_d", "forbid_m",
                 "empty", "nonempty", "section", "line_no")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    def key(self):
        return (self.chapter, self.para_index)

    def label(self):
        return f"{self.chapter}[{self.para_index}]"


class Spec:
    def __init__(self, path: pathlib.Path) -> None:
        self.raw = path.read_bytes().decode("utf-8")
        self.lines = self.raw.split("\n")
        self.tables: dict[tuple[str, int], list[tuple[int, list[str]]]] = {}
        self.table_header: dict[tuple[str, int], list[str]] = {}
        self.heading_text: dict[str, str] = {}
        self._parse_tables()
        self.anchors: list[Anchor] = []
        self._build_anchors()
        self.groups, self.subgroups = self._parse_dispatch()

    # -- 表格 ---------------------------------------------------------------
    def _parse_tables(self) -> None:
        cur_heading = ""
        table_idx = 0
        i = 0
        while i < len(self.lines):
            line = self.lines[i]
            if line.startswith("#"):
                cur_heading = line.lstrip("#").strip()
                table_idx = 0
                i += 1
                continue
            if line.startswith("| 章[段]"):
                header = [c.strip() for c in line.strip("|").split("|")]
                key = (cur_heading, table_idx)
                self.table_header[key] = header
                rows = []
                i += 2  # 跳過分隔列
                while i < len(self.lines) and self.lines[i].startswith("|"):
                    cells = [c.strip() for c in self.lines[i].strip("|").split("|")]
                    rows.append((i, cells))
                    i += 1
                self.tables[key] = rows
                table_idx += 1
                continue
            i += 1

    def _build_anchors(self) -> None:
        for (heading, idx), rows in self.tables.items():
            frag = next((f for (f, j) in SECTION_SEMANTICS
                         if f in heading and j == idx), None)
            if frag is None:
                continue
            sem = SECTION_SEMANTICS[(frag, idx)]
            header = self.table_header[(heading, idx)]
            self.heading_text[frag] = heading
            q_col = header.index("逐字引句") if "逐字引句" in header else None
            b_col = header.index("批") if "批" in header else None
            r_col = (header.index("必須含") if "必須含" in header
                     else (header.index("為什麼判空") if "為什麼判空" in header else None))
            for line_no, cells in rows:
                m = re.match(r"^`(.+?)`\[(\d+)\]$", cells[0])
                if not m:
                    continue
                quote = None
                if q_col is not None and q_col < len(cells):
                    q = re.match(r"^「(.+)」$", cells[q_col])
                    quote = q.group(1) if q else None
                batch = cells[b_col] if b_col is not None and b_col < len(cells) else None
                require, require_m, forbid_d, forbid_m = ([], set(), set(), set())
                if r_col is not None and r_col < len(cells):
                    (require, require_m,
                     forbid_d, forbid_m) = parse_requirement(cells[r_col])
                empty = bool(sem.get("empty"))
                if empty:
                    require = []
                # 「非空（不指定格）」那一列沒有羅馬數字，不補這一句它會靜靜不被檢查
                said_nonempty = (r_col is not None and r_col < len(cells)
                                 and "非空" in cells[r_col])
                self.anchors.append(Anchor(
                    chapter=m.group(1), para_index=int(m.group(2)),
                    quote=quote, batch=batch,
                    require=require, require_m=require_m,
                    forbid_d=forbid_d, forbid_m=forbid_m,
                    empty=empty,
                    nonempty=(not empty) and (bool(require) or said_nonempty),
                    section=frag, line_no=line_no))

    def section_anchors(self, frag: str) -> list[Anchor]:
        return [a for a in self.anchors if a.section == frag]

    def needs_quote(self, frag: str) -> bool:
        return bool(SECTION_SEMANTICS.get((frag, 0), {}).get("quote"))

    # -- 分派表 -------------------------------------------------------------
    def _parse_dispatch(self):
        groups: dict[str, dict] = {}
        subgroups: dict[str, dict] = {}
        for line in self.lines:
            m = re.match(r"^\| \*\*(G\d′?)[^|*]*\*\* \| (\d+) \| (\d+) \| (.*?) \| .*\|$",
                         line)
            if not m:
                continue
            gid, n_ch, n_pa, cell = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
            chapters = re.findall(r"([㐀-鿿]+)(\d+)/(b0\d)", cell)
            groups[gid] = {"n_ch": n_ch, "n_pa": n_pa,
                           "chapters": [(c, int(n), b) for c, n, b in chapters]}
            if gid == "G3":
                for part in cell.split("<br>"):
                    ms = re.match(r"^\*\*(技術側|人側) (\d+) 篇 (\d+) 段\*\*：(.*)$",
                                  part.strip())
                    if not ms:
                        continue
                    name = "G3技" if ms.group(1) == "技術側" else "G3人"
                    chs = re.findall(r"([㐀-鿿]+)(\d+)/(b0\d)", ms.group(4))
                    subgroups[name] = {"n_ch": int(ms.group(2)), "n_pa": int(ms.group(3)),
                                       "chapters": [(c, int(n), b) for c, n, b in chs]}
        return groups, subgroups

    def chapter_group(self) -> dict[str, str]:
        out = {}
        for gid, g in self.groups.items():
            for ch, _n, _b in g["chapters"]:
                out[ch] = gid
        return out

    def chapter_subgroup(self) -> dict[str, str]:
        out = {}
        for sid, g in self.subgroups.items():
            for ch, _n, _b in g["chapters"]:
                out[ch] = sid
        return out

    # -- 條文數字 -----------------------------------------------------------
    def number(self, pattern: str):
        m = re.search(pattern, self.raw)
        return int(m.group(1)) if m else None

    def heading_count(self, frag: str):
        head = self.heading_text.get(frag)
        if head is None:
            return None
        m = re.search(r"(\d+) 段[）， ]", head)
        return int(m.group(1)) if m else None

    def section_bullets(self, heading_frag: str):
        """回傳 (bullet 總數, 解析出的 (章, 段, 批) 清單)。數量必須相等。"""
        m = re.search(r"^#+ .*" + re.escape(heading_frag) + r".*?$(.*?)(?=^#+ )",
                      self.raw, re.M | re.S)
        if m is None:
            return None, []
        body = m.group(1)
        bullets = re.findall(r"^- .*$", body, re.M)
        parsed = re.findall(r"^- `(.+?)`\[(\d+)\]（(b0\d)）", body, re.M)
        return len(bullets), [(c, int(i), b) for c, i, b in parsed]

    def gray_bullets(self):
        """灰區：一個 bullet 可能列多章多段（`祝盟`[5][6]；`封禪`[6][7]）。

        回傳 (bullet 總數, 有解析出段落的 bullet 數, [(章, 段), ...])。
        兩個數字必須相等——只驗非空會讓格式漂掉的那幾條靜靜消失（晏子教訓）。
        """
        m = re.search(r"^#+ .*我不設錨的灰區.*?$(.*?)(?=^#+ )",
                      self.raw, re.M | re.S)
        if m is None:
            return None, 0, []
        bullets = re.findall(r"^- .*$", m.group(1), re.M)
        keys: list[tuple[str, int]] = []
        hit = 0
        for b in bullets:
            got = re.findall(r"`([^`]+?)`((?:\[\d+\])+)", b)
            if got:
                hit += 1
            for ch, idxs in got:
                for i in re.findall(r"\[(\d+)\]", idxs):
                    keys.append((ch, int(i)))
        return len(bullets), hit, keys


# --------------------------------------------------------------------------
# --check-spec
# --------------------------------------------------------------------------

# A 類條文數字 → 該數字必須等於哪一組錨點的列數。
CLAUSE_COUNTS = [
    ("S8a", r"「必須判空」的 (\d+) 段", "必須判空的錨點"),
    ("S8b", r"XII 四側指定的 (\d+) 段", "XII 四側"),
    ("S8c", r"G1 指定的 (\d+) 段", "G1 文之樞紐"),
    ("S8d", r"G2 指定的 (\d+) 段", "G2 文體論"),
    ("S8e", r"G3 指定的 (\d+) 段", "G3 創作論"),
    ("S8f", r"G4 指定的 (\d+) 段", "G4 批評論"),
    ("S8g", r"G5 指定的 (\d+) 段", "G5 自序"),
]

BASE_FACTS = [
    ("為", r"`為` (\d+) 次"),
    ("爲", r"`爲` (\d+)；"),
    ("於", r"`於` (\d+)／"),
    ("于", r"`于` (\d+)（其中"),
]

TOUCHSTONE_RE = re.compile(
    r"\*\*`(.+?)`\[(\d+)\] 與 `(.+?)`\[(\d+)\] 的 XII 必須判反。\*\*")

CONTAIN_RE = re.compile(
    r"`domains\(\[(\d+)\]\) ⊇ domains\(\[(\d+)\]\) ∪ domains\(\[(\d+)\]\)`")

CAP_CHAPTERS_RE = re.compile(
    r"\*\*((?:〈[^〉]+〉)+)([一二三四五六七八九十]+)篇 (\d+) 段，命中至多 (\d+) 段。\*\*")
CAP_RANGE_RE = re.compile(
    r"\*\*〈(.+?)〉\[(\d+)\]–\[(\d+)\] 這 (\d+) 段.*?，命中至多 (\d+) 段。\*\*")
CAP_X_RE = re.compile(
    r"\*\*〈(.+?)〉(\d+) 段含 X 至多 (\d+) 段")


def check_spec(spec: Spec, corpus: Corpus) -> Report:
    r = Report()

    # S1 每個宣告的區段都要找得到；找不到代表 parser 咬空了（斷掉會更綠，不是報錯）
    for (frag, idx) in SECTION_SEMANTICS:
        if not [h for (h, i) in spec.tables if frag in h and i == idx]:
            r.fail("S1", f"找不到區段表格「{frag}」第 {idx} 張——SPEC 標題或表頭被改過，"
                         f"這一族斷言已經停跑")
    if not spec.anchors:
        r.fail("S1", "一條錨點都沒解析到")

    # S2 標題宣告的段數 == 實際列數
    for frag in SECTION_SEMANTICS:
        frag = frag[0]
        declared = spec.heading_count(frag)
        head = spec.heading_text.get(frag)
        rows = spec.tables.get((head, 0), []) if head else []
        if declared is None:
            r.fail("S2", f"「{frag}」標題裡讀不到宣告段數")
        elif declared != len(rows):
            r.fail("S2", f"「{frag}」標題宣告 {declared} 段，表格實際 {len(rows)} 列")

    # S3 每條錨點回語料對拍
    for a in spec.anchors:
        key = a.key()
        if key not in corpus.para:
            r.fail("S3", f"{a.label()} 在語料裡不存在")
            continue
        batch, _text = corpus.para[key]
        if a.batch != batch:
            r.fail("S3", f"{a.label()} SPEC 寫 {a.batch}，實際在 {batch}")
        if not spec.needs_quote(a.section):
            continue
        if not a.quote:
            r.fail("S3", f"{a.label()} 讀不到逐字引句")
            continue
        inside, unique = corpus.quote_ok(a.quote, key)
        if not inside:
            r.fail("S3", f"{a.label()} 引句對不上原文：{a.quote[:20]}")
        elif not unique:
            r.fail("S3", f"{a.label()} 引句在全書不唯一：{a.quote[:20]}")

    # S4 錨點段落不得重複登場
    for k, c in Counter(a.key() for a in spec.anchors).items():
        if c > 1:
            r.fail("S4", f"{k[0]}[{k[1]}] 出現在多張錨點表（{c} 次）")

    # S5 批次表與 A1 條文
    m = re.search(r"b01 (\d+)／b02 (\d+)／b03 (\d+)／b04 (\d+)／"
                  r"b05 (\d+)／b06 (\d+)／b07 (\d+)，合計 (\d+)", spec.raw)
    if not m:
        r.fail("S5", "A 類第 1 條讀不到批次段數宣告——條文被改寫，這一族斷言已停跑")
    else:
        for i in range(7):
            b = f"b0{i + 1}"
            if corpus.batch_size[b] != int(m.group(i + 1)):
                r.fail("S5", f"A1 條文 {b} 宣告 {m.group(i + 1)} 段，"
                             f"實際 {corpus.batch_size[b]} 段")
        if int(m.group(8)) != len(corpus.para):
            r.fail("S5", f"A1 條文合計宣告 {m.group(8)}，實際 {len(corpus.para)}")

    seen_batch_rows = 0
    for line in spec.lines:
        m = re.match(r"^\| (b0\d) \| (\d+) \| (\d+) \|$", line)
        if m:
            seen_batch_rows += 1
            b, np_, nc = m.group(1), int(m.group(2)), int(m.group(3))
            if corpus.batch_size[b] != np_:
                r.fail("S5", f"批次表 {b} 段數 {np_}，實際 {corpus.batch_size[b]}")
            if len(corpus.batch_chapters[b]) != nc:
                r.fail("S5", f"批次表 {b} 章數 {nc}，實際 {len(corpus.batch_chapters[b])}")
    if seen_batch_rows != len(corpus.batch_size):
        r.fail("S5", f"批次表只解析到 {seen_batch_rows} 列，實際 {len(corpus.batch_size)} 批"
                     f"——表格格式漂掉，缺的那幾列已停跑")

    # S6 分派表：群的篇數、段數、章名歸屬、批次都要對
    if set(spec.groups) != set(GROUP_IDS):
        r.fail("S6", f"分派表解析到 {sorted(spec.groups)}，應為 {GROUP_IDS}"
                     f"——缺的那幾群已停跑")
    assigned = []
    for gid, g in spec.groups.items():
        chs = g["chapters"]
        if len(chs) != g["n_ch"]:
            r.fail("S6", f"{gid} 宣告 {g['n_ch']} 篇，章名欄解析出 {len(chs)} 篇")
        if sum(n for _c, n, _b in chs) != g["n_pa"]:
            r.fail("S6", f"{gid} 宣告 {g['n_pa']} 段，章名欄加總 "
                         f"{sum(n for _c, n, _b in chs)} 段")
        for ch, n, b in chs:
            assigned.append(ch)
            if ch not in corpus.chapter_size:
                r.fail("S6", f"{gid} 的章名「{ch}」在語料裡不存在")
            else:
                if corpus.chapter_size[ch] != n:
                    r.fail("S6", f"{gid} 的「{ch}」宣告 {n} 段，"
                                 f"實際 {corpus.chapter_size[ch]} 段")
                if corpus.chapter_batch[ch] != b:
                    r.fail("S6", f"{gid} 的「{ch}」宣告在 {b}，"
                                 f"實際 {corpus.chapter_batch[ch]}")
    dup = [c for c, k in Counter(assigned).items() if k > 1]
    if dup:
        r.fail("S6", f"分派表章名重複：{dup}")
    missing = set(corpus.chapter_size) - set(assigned)
    if missing:
        r.fail("S6", f"分派表漏了 {len(missing)} 章：{sorted(missing)}")
    total = sum(g["n_pa"] for g in spec.groups.values())
    if total != len(corpus.para):
        r.fail("S6", f"分派表各群段數加總 {total}，語料 {len(corpus.para)} 段")

    # S7 G3 群內兩側
    if set(spec.subgroups) != set(SUBGROUPS):
        r.fail("S7", f"G3 只解析到 {sorted(spec.subgroups)}，應為 {SUBGROUPS}"
                     f"——群內拆側已停跑")
    sub_total = 0
    for sid, g in spec.subgroups.items():
        if len(g["chapters"]) != g["n_ch"]:
            r.fail("S7", f"{sid} 宣告 {g['n_ch']} 篇，解析出 {len(g['chapters'])} 篇")
        s = sum(n for _c, n, _b in g["chapters"])
        if s != g["n_pa"]:
            r.fail("S7", f"{sid} 宣告 {g['n_pa']} 段，加總 {s} 段")
        sub_total += g["n_pa"]
    if "G3" in spec.groups and sub_total != spec.groups["G3"]["n_pa"]:
        r.fail("S7", f"G3 兩側加總 {sub_total} 段，群宣告 {spec.groups['G3']['n_pa']} 段")

    # S8 A 類條文數字 == 錨點表列數
    for code, pat, frag in CLAUSE_COUNTS:
        n = spec.number(pat)
        head = spec.heading_text.get(frag)
        rows = len(spec.tables.get((head, 0), [])) if head else 0
        if n is None:
            r.fail(code, f"A 類條文讀不到數字（pattern={pat}）——條文被改寫，斷言已停跑")
        elif n != rows:
            r.fail(code, f"條文寫 {frag} {n} 段，錨點表 {rows} 列")

    # S9 底本事實
    for ch, pat in BASE_FACTS:
        n = spec.number(pat)
        actual = corpus.all_text.count(ch)
        if n is None:
            r.fail("S9", f"讀不到底本事實宣告（{ch}，pattern={pat}）")
        elif n != actual:
            r.fail("S9", f"底本事實 {ch} 宣告 {n} 次，實際 {actual} 次")

    n = spec.number(r"校異「一作「X」」(\d+) 處")
    actual = corpus.all_text.count("一作「")
    if n is None:
        r.fail("S9", "讀不到校異處數宣告")
    elif n != actual:
        r.fail("S9", f"校異宣告 {n} 處，實際 {actual} 處")

    n = spec.number(r"\*\*贊語 (\d+) 段")
    if n is None:
        r.fail("S9", "讀不到贊語段數宣告")
    elif n != len(corpus.zan):
        r.fail("S9", f"贊語宣告 {n} 段，實際 {len(corpus.zan)} 段")

    brackets = sum(corpus.all_text.count(c) for c in "〈〉〔〕【】")
    if brackets:
        r.fail("S9", f"SPEC 宣告本書無夾注，實際出現 {brackets} 個夾注符號")

    # 校異分布逐篇對拍
    declared_dist = re.search(r"分布 12 篇：(.+?)。", spec.raw)
    if declared_dist is None:
        r.fail("S9", "讀不到校異分布宣告——這一族斷言已停跑")
    else:
        pairs = re.findall(r"([㐀-鿿]+) (\d+)", declared_dist.group(1))
        if len(pairs) != 12:
            r.fail("S9", f"校異分布宣告 12 篇，只解析出 {len(pairs)} 篇")
        actual_dist = Counter()
        for (ch, _pi), (_b, t) in corpus.para.items():
            if "一作「" in t:
                actual_dist[ch] += t.count("一作「")
        for ch, cnt in pairs:
            if actual_dist.get(ch, 0) != int(cnt):
                r.fail("S9", f"校異分布〈{ch}〉宣告 {cnt} 處，實際 {actual_dist.get(ch, 0)} 處")
        if set(actual_dist) != {c for c, _n in pairs}:
            r.fail("S9", f"校異分布篇名不符，實際：{sorted(actual_dist)}")

    # S10 領域表與 mode 表
    spec_domains = re.findall(r"^\| (XIII|XII|XI|IX|VIII|VII|VI|IV|III|II|X|V|I) \| ",
                              spec.raw, re.M)
    if spec_domains != DOMAIN_IDS:
        r.fail("S10", f"領域表列出 {len(spec_domains)} 個 id，與 13 個標準 id 不符：{spec_domains}")
    spec_modes = re.findall(r"^\| `([a-z_]+)` \| ", spec.raw, re.M)
    if sorted(spec_modes) != sorted(MODE_IDS):
        r.fail("S10", f"mode 表列出 {spec_modes}，與 8 個標準 id 不符")

    # S11 灰區：每個 bullet 都要解析得出來（只驗非空會讓格式漂掉的那幾條靜靜消失）
    nb, nhit, gray = spec.gray_bullets()
    if nb is None:
        r.fail("S11", "找不到灰區區段——斷言已停跑")
    else:
        if nhit != nb:
            r.fail("S11", f"灰區有 {nb} 個 bullet，只有 {nhit} 條解析出段落——"
                          f"格式漂掉的那幾條已停跑")
        for ch, pi in gray:
            if (ch, pi) not in corpus.para:
                r.fail("S11", f"灰區 {ch}[{pi}] 在語料裡不存在")
    gray_keys = set(gray)
    clash = gray_keys & {a.key() for a in spec.anchors}
    if clash:
        r.fail("S11", f"灰區段落同時被列為硬錨點：{sorted(clash)}")

    # S12 reason 長度係數
    if spec.number(r"不得少於 N × (\d+) 字元") is None:
        r.fail("S12", "A 類讀不到 reason 長度係數")

    # S13 諧讔／諧隱 非空清單
    nb, xie = spec.section_bullets("諧讔／諧隱")
    n_clause = spec.number(r"那一節列出的 (\d+) 段 `domains` 全部非空")
    if nb is None:
        r.fail("S13", "找不到諧讔／諧隱區段——A11 已停跑")
    else:
        if len(xie) != nb:
            r.fail("S13", f"諧讔／諧隱有 {nb} 個 bullet，只解析出 {len(xie)} 條")
        if n_clause is None:
            r.fail("S13", "A11 條文讀不到段數")
        elif n_clause != len(xie):
            r.fail("S13", f"A11 條文寫 {n_clause} 段，清單 {len(xie)} 條")
        for ch, pi, b in xie:
            if (ch, pi) not in corpus.para:
                r.fail("S13", f"諧讔／諧隱 {ch}[{pi}] 在語料裡不存在")
            elif corpus.para[(ch, pi)][0] != b:
                r.fail("S13", f"{ch}[{pi}] 宣告 {b}，實際 {corpus.para[(ch, pi)][0]}")

    # S14 試金石（A6）
    m = TOUCHSTONE_RE.search(spec.raw)
    if m is None:
        r.fail("S14", "A 類第 6 條試金石讀不出兩段——A6 已停跑")
    else:
        for ch, pi in [(m.group(1), int(m.group(2))), (m.group(3), int(m.group(4)))]:
            if (ch, pi) not in corpus.para:
                r.fail("S14", f"試金石 {ch}[{pi}] 在語料裡不存在")

    # S15 原文集注包含條件（A16）
    # 配套 (6) 與 A 類第 16 條各寫一次，兩處必須逐字一致；去重後應剩 2 條。
    raw_contains = CONTAIN_RE.findall(spec.raw)
    contains = sorted(set(raw_contains))
    if len(raw_contains) != 4 or len(contains) != 2:
        r.fail("S15", f"包含條件在 SPEC 出現 {len(raw_contains)} 次、去重 "
                      f"{len(contains)} 條（應為 4 次／2 條）——配套 (6) 與 A16 已漂開")
    m = re.search(r"〈原文集注〉的包含條件", spec.raw)
    if m is None:
        r.fail("S15", "找不到〈原文集注〉包含條件標題")
    for a, b, c in contains:
        big = corpus.para.get(("原文集注", int(a)))
        for sub in (b, c):
            small = corpus.para.get(("原文集注", int(sub)))
            if big is None or small is None:
                r.fail("S15", f"原文集注[{a}]／[{sub}] 在語料裡不存在")
            elif small[1] not in big[1]:
                r.fail("S15", f"原文集注[{sub}] 的文字並不包含在 [{a}] 裡，"
                              f"包含條件的前提不成立")

    # S16 章級上界：宣告的段數要對得上語料
    caps = parse_caps(spec)
    if len(caps) != 4:
        r.fail("S16", f"章級上界解析到 {len(caps)} 條，應為 4 條——這一族斷言已停跑")
    for cap in caps:
        n = sum(corpus.chapter_size.get(c, 0) for c in cap["chapters"]) \
            if cap["kind"] != "range" else (cap["hi"] - cap["lo"] + 1)
        for c in cap["chapters"]:
            if c not in corpus.chapter_size:
                r.fail("S16", f"上界條文的章名「{c}」在語料裡不存在")
        if n != cap["n_para"]:
            r.fail("S16", f"上界條文「{'／'.join(cap['chapters'])}」宣告 {cap['n_para']} 段，"
                          f"實際 {n} 段")
        if cap["kind"] == "range":
            ch = cap["chapters"][0]
            if corpus.chapter_size.get(ch, 0) < cap["hi"]:
                r.fail("S16", f"{ch} 只有 {corpus.chapter_size.get(ch)} 段，"
                              f"上界條文指到 [{cap['hi']}]")

    # S17 「modes 必含 X」型條件：條文寫了、表格也要解析得出來
    for m in re.finditer(r"`(.+?)`\[(\d+)\] 的 `modes` 含 `([a-z_]+)`", spec.raw):
        ch, pi, mode = m.group(1), int(m.group(2)), m.group(3)
        a = next((x for x in spec.anchors if x.key() == (ch, pi)), None)
        if a is None:
            r.fail("S17", f"條文要求 {ch}[{pi}] 的 modes 含 {mode}，但錨點表裡沒有這一段")
        elif mode not in a.require_m:
            r.fail("S17", f"條文要求 {ch}[{pi}] 的 modes 含 {mode}，"
                          f"但錨點表的條件欄解析不出來（實得 {sorted(a.require_m)}）"
                          f"——A14 的這一半已停跑")

    return r


def parse_caps(spec: Spec) -> list[dict]:
    caps = []
    for m in CAP_CHAPTERS_RE.finditer(spec.raw):
        chs = re.findall(r"〈([^〉]+)〉", m.group(1))
        caps.append({"kind": "chapters", "chapters": chs,
                     "n_para": int(m.group(3)), "cap": int(m.group(4)), "domain": None})
    for m in CAP_RANGE_RE.finditer(spec.raw):
        caps.append({"kind": "range", "chapters": [m.group(1)],
                     "lo": int(m.group(2)), "hi": int(m.group(3)),
                     "n_para": int(m.group(4)), "cap": int(m.group(5)), "domain": None})
    for m in CAP_X_RE.finditer(spec.raw):
        caps.append({"kind": "domain", "chapters": [m.group(1)],
                     "n_para": int(m.group(2)), "cap": int(m.group(3)), "domain": "X"})
    return caps


# --------------------------------------------------------------------------
# 批次輸出驗收（A 類）
# --------------------------------------------------------------------------

def check_output(spec: Spec, corpus: Corpus, paths: list[pathlib.Path],
                 whole_book: bool):
    r = Report()
    rows: dict[tuple[str, int], dict] = {}

    for p in paths:
        try:
            obj = json.loads(p.read_bytes().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            r.fail("A1", f"{p.name} 不是合法 JSON：{e}")
            continue
        batch = re.sub(r"\.md$", "", str(obj.get("batch", p.stem)))
        expect = corpus.batch_size.get(batch)
        if expect is None:
            r.fail("A1", f"{p.name} 的 batch 欄「{obj.get('batch')}」不是已知批次")
            continue
        rs = obj.get("rows")
        if not isinstance(rs, list):
            r.fail("A1", f"{p.name} 沒有 rows 陣列")
            continue
        if len(rs) != expect:
            r.fail("A1", f"{batch} 有 {len(rs)} 列，應為 {expect} 列")
        batch_chs = set(corpus.batch_chapters[batch])
        for i, row in enumerate(rs):
            ch, pi = row.get("chapter"), row.get("para_index")
            if ch not in batch_chs:
                r.fail("A1", f"{batch} 第 {i + 1} 列章名不屬於本批：{ch!r}")
                continue
            if not isinstance(pi, int) or (ch, pi) not in corpus.para:
                r.fail("A1", f"{batch} {ch} 的 para_index {pi!r} 不存在")
                continue
            if (ch, pi) in rows:
                r.fail("A1", f"{ch}[{pi}] 重複出現")
                continue
            rows[(ch, pi)] = row
            if not str(row.get("reason") or "").strip():
                r.fail("A1", f"{ch}[{pi}] 沒有 reason")

        by_ch = defaultdict(set)
        for row in rs:
            if isinstance(row.get("para_index"), int):
                by_ch[row.get("chapter")].add(row["para_index"])
        for _b, ch, n in corpus.chapters:
            if _b != batch:
                continue
            if by_ch.get(ch) != set(range(1, n + 1)):
                r.fail("A1", f"{ch} 的 para_index 應為 1..{n}，"
                             f"實得 {sorted(by_ch.get(ch, []))}")

    def dom(key):
        v = rows.get(key, {}).get("domains")
        return v if isinstance(v, list) else None

    # A17 詞彙合法
    for key, row in rows.items():
        for d in row.get("domains") or []:
            if d not in DOMAIN_IDS:
                r.fail("A17", f"{key[0]}[{key[1]}] domains 出現非法值 {d!r}")
        for m in row.get("modes") or []:
            if m not in MODE_IDS:
                r.fail("A17", f"{key[0]}[{key[1]}] modes 出現非法值 {m!r}")

    # A2 章名歸群
    ch_group = spec.chapter_group()
    for key in rows:
        if key[0] not in ch_group:
            r.fail("A2", f"{key[0]} 不屬於分派表任一群")

    # A3/A5/A9/A10/A12/A13/A14 錨點
    for a in spec.anchors:
        key = a.key()
        if key not in rows:
            continue
        ds = dom(key)
        ms = rows[key].get("modes")
        code = SECTION_CODE.get(a.section, "A4")
        if ds is None:
            r.fail("A1", f"{a.label()} 沒有 domains 陣列")
            continue
        if a.empty and ds:
            r.fail(code, f"{a.label()} 必須判空，實得 {ds}")
        if a.nonempty and not ds:
            r.fail(code, f"{a.label()} 必須非空，實得 []")
        for g in a.require:
            if not (set(ds) & g):
                r.fail(code, f"{a.label()} 必須含 {'或'.join(sorted(g, key=DOMAIN_IDS.index))}，"
                             f"實得 {ds}")
        bad = set(ds) & a.forbid_d
        if bad:
            r.fail("A4" if a.section == "必須判空的錨點" else code,
                   f"{a.label()} 不得含 {sorted(bad)}，實得 {ds}")
        if isinstance(ms, list):
            badm = set(ms) & a.forbid_m
            if badm:
                r.fail("A4" if a.section == "必須判空的錨點" else code,
                       f"{a.label()} modes 不得含 {sorted(badm)}，實得 {ms}")
            missm = a.require_m - set(ms)
            if missm:
                r.fail(code, f"{a.label()} modes 必含 {sorted(missm)}，實得 {ms}")

    # A6 試金石：正緯兩段的 XII 必須判反
    m = TOUCHSTONE_RE.search(spec.raw)
    if m is None:
        r.fail("A6", "讀不到試金石條文——A 類第 6 條已停跑")
    else:
        k1, k2 = (m.group(1), int(m.group(2))), (m.group(3), int(m.group(4)))
        if k1 in rows and k2 in rows:
            if ("XII" in set(dom(k1) or [])) == ("XII" in set(dom(k2) or [])):
                r.fail("A6", f"試金石判齊：{k1[0]}[{k1[1]}] 與 {k2[0]}[{k2[1]}] "
                             f"的 XII 同向")

    # A8 XII 篇級限制
    m = re.search(r"XII 不得出現在((?:〈[^〉]+〉)+)以外的任何篇", spec.raw)
    if m is None:
        r.fail("A8", "讀不到 XII 篇級限制條文——A8 已停跑")
    else:
        allowed = set(re.findall(r"〈([^〉]+)〉", m.group(1)))
        unknown = allowed - set(corpus.chapter_size)
        if unknown:
            r.fail("A8", f"XII 允許篇名在語料裡不存在：{sorted(unknown)}")
        for key, row in rows.items():
            if "XII" in (row.get("domains") or []) and key[0] not in allowed:
                r.fail("A8", f"{key[0]}[{key[1]}] 含 XII，但〈{key[0]}〉不在允許的四篇內")

    # A11 諧讔／諧隱非空
    _nb, xie = spec.section_bullets("諧讔／諧隱")
    for ch, pi, _b in xie:
        if (ch, pi) in rows and not dom((ch, pi)):
            r.fail("A11", f"{ch}[{pi}] 必須非空，實得 []")

    # A15 章級上界
    for cap in parse_caps(spec):
        if cap["kind"] == "range":
            ch = cap["chapters"][0]
            keys = [(ch, i) for i in range(cap["lo"], cap["hi"] + 1) if (ch, i) in rows]
        else:
            keys = [k for k in rows if k[0] in cap["chapters"]]
        if not keys:
            continue
        if cap["domain"]:
            hits = [k for k in keys if cap["domain"] in (dom(k) or [])]
            label = f"含 {cap['domain']}"
        else:
            hits = [k for k in keys if dom(k)]
            label = "命中"
        if len(hits) > cap["cap"]:
            r.fail("A15", f"〈{'〉〈'.join(cap['chapters'])}〉{label} {len(hits)} 段，"
                          f"上界 {cap['cap']} 段：{[f'{c}[{i}]' for c, i in hits]}")
    # 〈哀弔〉X 必含指定段（條文裡的附加條件）
    m = re.search(r"〈哀弔〉\d+ 段含 X 至多 \d+ 段，且必含 `(.+?)`\[(\d+)\]", spec.raw)
    if m is None:
        r.fail("A15", "讀不到〈哀弔〉X 必含條件——這一條已停跑")
    else:
        k = (m.group(1), int(m.group(2)))
        if k in rows and "X" not in (dom(k) or []):
            r.fail("A15", f"{k[0]}[{k[1]}] 必須含 X，實得 {dom(k)}")

    # A16 原文集注包含條件
    for a, b, c in CONTAIN_RE.findall(spec.raw):
        big = dom(("原文集注", int(a)))
        if big is None:
            continue
        for sub in (b, c):
            small = dom(("原文集注", int(sub)))
            if small is None:
                continue
            extra = set(small) - set(big)
            if extra:
                r.fail("A16", f"原文集注[{sub}] 有 {sorted(extra)} 但 [{a}] 沒有——"
                              f"[{sub}] 的文字整段包含在 [{a}] 裡，不可能多出領域")
    for i in range(1, corpus.chapter_size.get("原文集注", 0) + 1):
        ms = rows.get(("原文集注", i), {}).get("modes")
        if isinstance(ms, list) and "formalization" in ms:
            r.fail("A16", f"原文集注[{i}] 的 modes 不得含 formalization")

    # A18 worked_instance 全書 0 段
    wi = [f"{k[0]}[{k[1]}]" for k, row in rows.items()
          if "worked_instance" in (row.get("modes") or [])]
    if wi:
        r.fail("A18", f"worked_instance 應為 0 段，實得 {len(wi)}：{wi[:5]}")

    # A19 reason 長度
    coef = spec.number(r"不得少於 N × (\d+) 字元")
    if coef is None:
        r.fail("A19", "讀不到 reason 長度係數——A 類第 19 條已停跑")
    else:
        for key, row in rows.items():
            n = len(row.get("domains") or [])
            ln = len(str(row.get("reason") or ""))
            if n and ln < n * coef:
                r.fail("A19", f"{key[0]}[{key[1]}] 標了 {n} 格，reason 只有 {ln} 字元"
                              f"（需 ≥ {n * coef}）")

    if whole_book:
        got = Counter(ch_group.get(k[0]) for k in rows)
        for gid, g in spec.groups.items():
            if got[gid] != g["n_pa"]:
                r.fail("A2", f"群 {gid} 回收 {got[gid]} 段，應為 {g['n_pa']} 段")
        miss = set(corpus.para) - set(rows)
        if miss:
            r.fail("A1", f"全書漏了 {len(miss)} 段，例：{sorted(miss)[:3]}")

    return r, rows


def report_b_class(spec: Spec, corpus: Corpus, rows: dict) -> None:
    if not rows:
        return
    print("\n=== B 類實測（不擋收） ===")
    ch_group = spec.chapter_group()
    ch_sub = spec.chapter_subgroup()
    dc = Counter(d for row in rows.values() for d in (row.get("domains") or []))
    mc = Counter(m for row in rows.values() for m in (row.get("modes") or []))

    def rate(ks):
        if not ks:
            return "n/a"
        hit = len([k for k in ks if rows[k].get("domains")])
        return f"{hit}/{len(ks)} = {hit / len(ks):.0%}"

    allk = list(rows)
    print(f"全書命中 {rate(allk)}")
    for gid in GROUP_IDS:
        ks = [k for k in allk if ch_group.get(k[0]) == gid]
        if gid == "G3":
            for sid in SUBGROUPS:
                sks = [k for k in ks if ch_sub.get(k[0]) == sid]
                print(f"  {sid:<6} {rate(sks)}")
        else:
            print(f"  {gid:<6} {rate(ks)}")
    zan = [k for k in allk if k in corpus.zan]
    print(f"贊語 {len(zan)} 段命中 {rate(zan)}")
    print("領域：" + "  ".join(f"{d}={dc[d]}" for d in DOMAIN_IDS))
    print("mode：" + "  ".join(f"{m}={mc[m]}" for m in MODE_IDS))
    print(f"零段領域：{[d for d in DOMAIN_IDS if not dc[d]]}")

    k1, k2 = ("諧讔", 1), ("諧隱", 1)
    if k1 in rows and k2 in rows:
        d1 = sorted(set(rows[k1].get("domains") or []), key=DOMAIN_IDS.index)
        d2 = sorted(set(rows[k2].get("domains") or []), key=DOMAIN_IDS.index)
        verdict = "一致" if d1 == d2 else "不一致"
        print(f"跨批盲測 諧讔[1]（b05）↔ 諧隱[1]（b06）相似度 0.939：{d1} vs {d2} → {verdict}")
    else:
        print("跨批盲測：兩批尚未齊回收")

    print("\n--- 逐章命中（群內也要拆開看）---")
    for _b, ch, n in corpus.chapters:
        ks = [k for k in allk if k[0] == ch]
        if ks:
            g = ch_sub.get(ch) or ch_group.get(ch)
            print(f"  {ch:<6} {g:<5} {rate(ks)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--check-spec", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    corpus = Corpus(HERE)
    spec = Spec(SPEC_PATH)

    if args.check_spec:
        rep = check_spec(spec, corpus)
        rep.dump("check-spec")
        # 斷言族斷掉的表現是「更綠」而不是報錯，這幾行是唯一看得出 parser 咬空的地方。
        print("\n--- 解析涵蓋 ---")
        print(f"語料 {len(corpus.chapters)} 章 / {len(corpus.para)} 段 / "
              f"{len(corpus.batch_size)} 批 / 贊語 {len(corpus.zan)} 段")
        print(f"分派表 {len(spec.groups)} 群 + {len(spec.subgroups)} 側，"
              f"涵蓋 {sum(len(g['chapters']) for g in spec.groups.values())} 章")
        print(f"錨點共 {len(spec.anchors)} 條，分佈：")
        for frag, _i in SECTION_SEMANTICS:
            ax = spec.section_anchors(frag)
            req = sum(len(a.require) for a in ax)
            fb = sum(len(a.forbid_d) + len(a.forbid_m) for a in ax)
            print(f"  {frag:<14} {len(ax):>2} 條  require群 {req:>2}  forbid {fb:>2}")
        nb_g, nhit_g, gray = spec.gray_bullets()
        nb_x, xie = spec.section_bullets("諧讔／諧隱")
        print(f"灰區 {nhit_g}/{nb_g} bullet（{len(gray)} 段）；"
              f"諧讔諧隱 {len(xie)}/{nb_x} bullet；"
              f"章級上界 {len(parse_caps(spec))} 條；包含條件 "
              f"{len(set(CONTAIN_RE.findall(spec.raw)))} 條")
        return 0 if rep.ok() else 1

    paths = [pathlib.Path(f) for f in args.files]
    if args.all:
        paths = sorted(OUT_DIR.glob("b*.json"))
    if not paths:
        print("沒有指定輸出檔（用 --all 或列出 out/bNN.json）")
        return 2

    whole = len(paths) == len(corpus.batch_size)
    rep, rows = check_output(spec, corpus, paths, whole)
    rep.dump("output " + ", ".join(p.name for p in paths))
    report_b_class(spec, corpus, rows)
    return 0 if rep.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
