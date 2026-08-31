#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""吳越春秋 標註驗收器。

錨點一律由本檔現場解析 SPEC.md 的表格與條文，不在程式裡手抄任何章名、段號或引句。
表格用「表頭欄名」定位欄位，不用欄位序——SPEC 增刪欄位不會讓斷言靜默失效。

用法:
    python accept.py --check-spec              # 只驗規格本身（發包前必跑到 0 FAIL）
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
REPO = HERE.parent.parent
SPEC_PATH = HERE / "SPEC.md"
OUT_DIR = HERE / "out"
RAW_PATH = REPO / "translations" / "wuyue-chunqiu" / "raw" / "original.txt"
MANIFEST_PATH = HERE / "MANIFEST.json"

sys.path.insert(0, str(REPO / "scripts"))
from corpus_text import split_paragraphs  # noqa: E402

DOMAIN_IDS = ["I", "II", "III", "IV", "V", "VI", "VII",
              "VIII", "IX", "X", "XI", "XII", "XIII"]
MODE_IDS = ["observation", "proposition", "prescription", "formalization",
            "narrative", "ritual", "expression", "worked_instance"]
GROUP_IDS = ["G1", "G2", "G3", "G4", "G5"]
BATCH_IDS = [f"b{i:02d}" for i in range(1, 11)]

_ROMAN_RE = re.compile(
    r"(?<![A-Za-z])(XIII|XII|XI|IX|VIII|VII|VI|IV|III|II|X|V|I)(?![A-Za-z])")

# 每張錨點表的語意。key = 標題子字串 + 該標題下的第幾張表。
# 只描述「這張表是什麼意思」，段數與成員一律由 SPEC 現場解析。
SECTION_SEMANTICS = {
    ("必須判空的錨點", 0): {"empty": True},
    ("認證側", 0): {"require": [{"XII"}]},
    ("技術側", 0): {"nonempty": True, "forbid_d": {"XII"}},
    ("破除側／人力側", 0): {"require": [{"XI"}], "forbid_d": {"XII"}},
    ("X 的兩側", 0): {"require": [{"X"}]},
    ("X 的兩側", 1): {"nonempty": True, "forbid_d": {"X"}},
    ("G3 不是判空群", 0): {"nonempty": True},
    ("G4 登錄之外", 0): {"nonempty": True},
}

# A 類條文必須引用到的錨點表（防「加了表卻沒加條文」）
ANCHOR_SECTIONS = list(SECTION_SEMANTICS)


class Report:
    def __init__(self) -> None:
        self.fails: list[str] = []
        self.notes: list[str] = []

    def fail(self, code: str, msg: str) -> None:
        self.fails.append(f"[{code}] {msg}")

    def note(self, code: str, msg: str) -> None:
        self.notes.append(f"[{code}] {msg}")

    def dump(self, title: str) -> int:
        print(f"=== {title} ===")
        for f in self.fails:
            print("FAIL " + f)
        for n in self.notes:
            print("NOTE " + n)
        print(f"--- {len(self.fails)} FAIL / {len(self.notes)} NOTE ---")
        return 1 if self.fails else 0


# ---------------------------------------------------------------- 語料

class Corpus:
    def __init__(self) -> None:
        paras = split_paragraphs(RAW_PATH.read_text(encoding="utf-8"))
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        self.batch_of: dict[str, str] = {}
        self.batch_chapters: dict[str, list[str]] = {}
        for entry in manifest["batches"]:
            b = entry["file"][:3]
            self.batch_chapters[b] = [c["chapter"] for c in entry["chapters"]]
            for c in entry["chapters"]:
                self.batch_of[c["chapter"]] = b

        self.para: dict[tuple[str, int], tuple[str, str]] = {}
        self.order: list[str] = []
        self.chapter_paras: dict[str, list[int]] = defaultdict(list)
        for _t, ch, idx, text in paras:
            if ch not in self.chapter_paras:
                self.order.append(ch)
            self.chapter_paras[ch].append(idx)
            self.para[(ch, idx)] = (self.batch_of.get(ch, "?"), text)

        self.batch_size = Counter(b for b, _t in self.para.values())
        self.full = "".join(t for _b, t in self.para.values())

    def quote_hits(self, q: str) -> list[tuple[str, int]]:
        return [k for k, (_b, t) in self.para.items() if q in t]

    def batch_quote_style(self, b: str) -> tuple[int, int]:
        """回傳該批的（「 次數, “ 次數）。"""
        a = c = 0
        for (ch, _i), (bb, t) in self.para.items():
            if bb == b:
                a += t.count("「")
                c += t.count("“")
        return a, c


# ---------------------------------------------------------------- SPEC

def _strip_parens(cell: str) -> str:
    prev = None
    while prev != cell:
        prev = cell
        cell = re.sub(r"（[^（）]*）", "", cell)
    return cell.strip()


def parse_requirement(cell: str) -> list[set[str]]:
    """把「必須含」欄轉成 require groups：每個 set 代表「至少含其一」。"""
    cell = _strip_parens(cell).replace("**", "").strip()
    if not cell:
        return []
    groups: list[set[str]] = []
    for clause in re.split(r"[＋+，,；;]|\s且\s", cell):
        ids = set(_ROMAN_RE.findall(clause))
        if ids:
            groups.append(ids)
    return groups


class Anchor:
    __slots__ = ("chapter", "para_index", "quote", "batch", "group",
                 "require", "forbid_d", "empty", "nonempty", "section")

    def __init__(self, chapter, para_index, quote, batch, group, section):
        self.chapter = chapter
        self.para_index = para_index
        self.quote = quote
        self.batch = batch
        self.group = group
        self.section = section
        self.require: list[set[str]] = []
        self.forbid_d: set[str] = set()
        self.empty = False
        self.nonempty = False

    def key(self) -> tuple[str, int]:
        return (self.chapter, self.para_index)

    def label(self) -> str:
        return f"`{self.chapter}`[{self.para_index}]"


class Spec:
    def __init__(self, path: pathlib.Path) -> None:
        self.raw = path.read_text(encoding="utf-8")
        self.lines = self.raw.split("\n")
        self.tables: dict[tuple[str, int], list[dict[str, str]]] = {}
        self.headings: list[str] = []
        self._parse_tables()
        self.anchors: list[Anchor] = []
        self._build_anchors()

    # -- 表格：以最近一個標題 + 該標題下的表序為 key，欄位以表頭欄名定位
    def _parse_tables(self) -> None:
        heading = ""
        seen_under: Counter[str] = Counter()
        i = 0
        while i < len(self.lines):
            line = self.lines[i]
            if line.startswith("#"):
                heading = line.lstrip("#").strip()
                self.headings.append(heading)
                i += 1
                continue
            if line.startswith("|") and i + 1 < len(self.lines) \
                    and re.match(r"^\|[\s:|-]+\|$", self.lines[i + 1]):
                header = [c.strip() for c in line.strip("|").split("|")]
                rows: list[dict[str, str]] = []
                j = i + 2
                while j < len(self.lines) and self.lines[j].startswith("|"):
                    cells = [c.strip() for c in self.lines[j].strip("|").split("|")]
                    if len(cells) < len(header):
                        cells += [""] * (len(header) - len(cells))
                    rows.append(dict(zip(header, cells)))
                    j += 1
                self.tables[(heading, seen_under[heading])] = rows
                seen_under[heading] += 1
                i = j
                continue
            i += 1

    def heading_for(self, frag: str) -> str | None:
        for h in self.headings:
            if frag in h:
                return h
        return None

    def table(self, frag: str, idx: int = 0) -> list[dict[str, str]] | None:
        h = self.heading_for(frag)
        if h is None:
            return None
        return self.tables.get((h, idx))

    def heading_count(self, frag: str) -> int | None:
        h = self.heading_for(frag)
        if h is None:
            return None
        m = re.search(r"（(\d+) 段", h)
        return int(m.group(1)) if m else None

    def number(self, pattern: str) -> int | None:
        m = re.search(pattern, self.raw)
        return int(m.group(1)) if m else None

    def _build_anchors(self) -> None:
        for (frag, idx), sem in SECTION_SEMANTICS.items():
            rows = self.table(frag, idx)
            if rows is None:
                continue
            for row in rows:
                cell = row.get("章[段]", "")
                m = re.match(r"^`(.+?)`\[(\d+)\]$", cell)
                if not m:
                    continue
                q = re.match(r"^「(.+)」$", row.get("逐字引句", ""))
                a = Anchor(m.group(1), int(m.group(2)),
                           q.group(1) if q else "",
                           row.get("批", ""), row.get("群", ""),
                           (frag, idx))
                a.empty = bool(sem.get("empty"))
                a.nonempty = bool(sem.get("nonempty"))
                a.require = [set(g) for g in sem.get("require", [])]
                a.forbid_d = set(sem.get("forbid_d", set()))
                a.require += parse_requirement(row.get("必須含", ""))
                self.anchors.append(a)

    def section_anchors(self, frag: str, idx: int = 0) -> list[Anchor]:
        return [a for a in self.anchors if a.section == (frag, idx)]


# ---------------------------------------------------------------- 分派表

def group_map(spec: Spec, corpus: Corpus, r: Report) -> dict[str, str]:
    """從分派表建 章名 -> 群 對照，同時驗表本身。"""
    rows = spec.table("閘門：五個體例群")
    if rows is None:
        r.fail("S6", "找不到分派表——標題被改過，S6 這一族斷言已停跑")
        return {}
    gmap: dict[str, str] = {}
    seen_groups: list[str] = []
    for row in rows:
        gcell = row.get("群", "")
        gid = gcell.split()[0] if gcell else ""
        if gid not in GROUP_IDS:
            r.fail("S6", f"分派表出現未知群「{gcell}」")
            continue
        seen_groups.append(gid)
        chapters = row.get("章", "").split()
        for ch in chapters:
            if ch in gmap:
                r.fail("S6", f"章「{ch}」同時被分到 {gmap[ch]} 與 {gid}")
            gmap[ch] = gid
            if ch not in corpus.chapter_paras:
                r.fail("S6", f"分派表章名「{ch}」在語料裡不存在")
        m = re.match(r"^(\d+)／(\d+)$", row.get("章／段", ""))
        if not m:
            r.fail("S6", f"{gid} 讀不到「章／段」宣告")
        else:
            nc, np_ = int(m.group(1)), int(m.group(2))
            if nc != len(chapters):
                r.fail("S6", f"{gid} 宣告 {nc} 章，表列 {len(chapters)} 章")
            real = sum(len(corpus.chapter_paras.get(c, [])) for c in chapters)
            if np_ != real:
                r.fail("S6", f"{gid} 宣告 {np_} 段，語料實際 {real} 段")
        # 批範圍
        bcell = row.get("批", "")
        bs = re.findall(r"b\d{2}", bcell)
        if bs:
            lo, hi = bs[0], bs[-1]
            allowed = {b for b in BATCH_IDS if lo <= b <= hi}
            for ch in chapters:
                if corpus.batch_of.get(ch) not in allowed:
                    r.fail("S6", f"{gid} 宣告批 {bcell}，但「{ch}」在 "
                                 f"{corpus.batch_of.get(ch)}")
    if seen_groups != GROUP_IDS:
        r.fail("S6", f"分派表群序 {seen_groups}，預期 {GROUP_IDS}")
    missing = set(corpus.chapter_paras) - set(gmap)
    if missing:
        r.fail("S6", f"有 {len(missing)} 章沒被分派表涵蓋：{sorted(missing)}")
    return gmap


# ---------------------------------------------------------------- check-spec

def check_spec(spec: Spec, corpus: Corpus, r: Report) -> dict[str, str]:
    # S1 每張錨點表都在
    for frag, idx in ANCHOR_SECTIONS:
        if spec.table(frag, idx) is None:
            r.fail("S1", f"找不到錨點表「{frag}」第 {idx} 張——"
                         f"SPEC 標題或表頭被改過，這一族斷言已經停跑")
    if not spec.anchors:
        r.fail("S1", "一條錨點都沒解析到")

    # S2 標題宣告段數 == 表格列數
    for frag in ["必須判空的錨點", "認證側", "技術側", "破除側／人力側",
                 "G3 不是判空群", "G4 登錄之外"]:
        declared = spec.heading_count(frag)
        rows = spec.table(frag, 0)
        if rows is None:
            continue
        if declared is None:
            r.fail("S2", f"「{frag}」標題裡讀不到宣告段數")
        elif declared != len(rows):
            r.fail("S2", f"「{frag}」標題宣告 {declared} 段，表格實際 {len(rows)} 列")

    # X 的兩側：段數宣告在粗體行不在標題
    for label, idx in (("命中側", 0), ("判空側", 1)):
        m = re.search(rf"\*\*{label}（(\d+) 段", spec.raw)
        rows = spec.table("X 的兩側", idx)
        if m is None:
            r.fail("S2", f"「X 的兩側」讀不到{label}段數宣告")
        elif rows is not None and int(m.group(1)) != len(rows):
            r.fail("S2", f"X {label}宣告 {m.group(1)} 段，表格實際 {len(rows)} 列")

    gmap = group_map(spec, corpus, r)

    # S3 每條錨點回語料對拍
    for a in spec.anchors:
        if a.key() not in corpus.para:
            r.fail("S3", f"{a.label()} 在語料裡不存在")
            continue
        batch, text = corpus.para[a.key()]
        if a.batch and a.batch != batch:
            r.fail("S3", f"{a.label()} SPEC 寫 {a.batch}，實際在 {batch}")
        if a.group and gmap.get(a.chapter) and a.group != gmap[a.chapter]:
            r.fail("S3", f"{a.label()} SPEC 寫群 {a.group}，分派表是 {gmap[a.chapter]}")
        if not a.quote:
            r.fail("S3", f"{a.label()} 讀不到逐字引句")
            continue
        parts = [p for p in re.split(r"…+", a.quote) if p]
        for p in parts:
            if p not in text:
                r.fail("S3", f"{a.label()} 引句對不上原文：{p[:24]}")
            elif len(corpus.quote_hits(p)) != 1:
                r.fail("S3", f"{a.label()} 引句在全書出現 "
                             f"{len(corpus.quote_hits(p))} 次，不唯一：{p[:24]}")

    # S4 錨點段落不得跨表重複
    for k, c in Counter(a.key() for a in spec.anchors).items():
        if c > 1:
            r.fail("S4", f"{k[0]}[{k[1]}] 出現在 {c} 張錨點表")

    # S5 批次段數：A 類第 1 條的散文宣告 + 批次表
    m = re.search("／".join(rf"{b} (\d+)" for b in BATCH_IDS) + r"，合計 (\d+)",
                  spec.raw)
    if not m:
        r.fail("S5", "A 類第 1 條讀不到批次段數宣告——條文被改寫，這一族斷言已停跑")
    else:
        for i, b in enumerate(BATCH_IDS):
            if corpus.batch_size[b] != int(m.group(i + 1)):
                r.fail("S5", f"{b} 宣告 {m.group(i + 1)} 段，"
                             f"實際 {corpus.batch_size[b]} 段")
        if int(m.group(11)) != sum(corpus.batch_size.values()):
            r.fail("S5", f"合計宣告 {m.group(11)}，"
                         f"實際 {sum(corpus.batch_size.values())}")

    brows = spec.table("批次表")
    if brows is None:
        r.fail("S5", "找不到批次表")
    else:
        if len(brows) != len(BATCH_IDS):
            r.fail("S5", f"批次表 {len(brows)} 列，預期 {len(BATCH_IDS)}")
        for row in brows:
            b = row.get("批", "")
            if b not in corpus.batch_size:
                r.fail("S5", f"批次表出現未知批「{b}」")
                continue
            if int(row.get("段", "0")) != corpus.batch_size[b]:
                r.fail("S5", f"批次表 {b} 段數 {row.get('段')}，"
                             f"實際 {corpus.batch_size[b]}")
            declared_ch = [c for c in row.get("章", "").split("／") if c]
            if declared_ch != corpus.batch_chapters[b]:
                r.fail("S5", f"批次表 {b} 章名與 MANIFEST 不符："
                             f"{declared_ch} vs {corpus.batch_chapters[b]}")

    # S7 底本異體字與引號總數
    base = [("為", r"`為`（全書 (\d+) 次"), ("眾", r"`眾`（(\d+) 次"),
            ("裏", r"`裏`（(\d+) 次"), ("於", r"`於`（(\d+)）"),
            ("于", r"`于`（(\d+)）"), ("高", r"`高`（(\d+) 次）"),
            ("髙", r"`髙`（(\d+) 次）")]
    for ch, pat in base:
        n = spec.number(pat)
        if n is None:
            r.fail("S7", f"讀不到 `{ch}` 的字數宣告")
        elif n != corpus.full.count(ch):
            r.fail("S7", f"`{ch}` 宣告 {n} 次，實際 {corpus.full.count(ch)} 次")
    for ch in ["爲", "衆", "裡"]:
        if f"沒有一個 `{ch}`" in spec.raw or f"沒有 `{ch}`" in spec.raw:
            if corpus.full.count(ch):
                r.fail("S7", f"SPEC 宣告沒有 `{ch}`，實際 {corpus.full.count(ch)} 次")
        else:
            r.fail("S7", f"讀不到「沒有 `{ch}`」的宣告")
    qm = re.search(r"`「` (\d+) `」` (\d+)、`“` (\d+) `”` (\d+)", spec.raw)
    if not qm:
        r.fail("S7", "讀不到全書引號總數宣告")
    else:
        real = [corpus.full.count(c) for c in "「」“”"]
        for i, c in enumerate("「」“”"):
            if int(qm.group(i + 1)) != real[i]:
                r.fail("S7", f"`{c}` 宣告 {qm.group(i + 1)}，實際 {real[i]}")

    # S8 A 類條文宣告的段數 vs 錨點表列數
    a_counts = [("必須判空的錨點", 0, r"「必須判空」的 (\d+) 段"),
                ("認證側", 0, r"認證側 (\d+) 段全部含 XII"),
                ("技術側", 0, r"技術側 (\d+) 段 `domains` 全部非空"),
                ("破除側／人力側", 0, r"破除側 (\d+) 段全部含 XI"),
                ("X 的兩側", 0, r"X 命中側 (\d+) 段全部含 X")]
    for frag, idx, pat in a_counts:
        n = spec.number(pat)
        rows = spec.table(frag, idx)
        if n is None:
            r.fail("S8", f"A 類條文讀不到「{frag}」段數——條文被改寫，斷言已停跑")
        elif rows is not None and n != len(rows):
            r.fail("S8", f"A 類條文說「{frag}」{n} 段，表格 {len(rows)} 列")

    # S9 領域表 13 列、mode 表 8 列、XII 五側表 5 列
    for frag, want, name in [("13 個領域", 13, "領域"),
                             ("8 個 discourse_mode", 8, "mode"),
                             ("XII 要五分", 5, "XII 側")]:
        rows = spec.table(frag)
        if rows is None:
            r.fail("S9", f"找不到{name}表")
        elif len(rows) != want:
            r.fail("S9", f"{name}表 {len(rows)} 列，預期 {want}")
    drows = spec.table("13 個領域") or []
    ids = [row.get("id", "") for row in drows]
    if ids != DOMAIN_IDS:
        r.fail("S9", f"領域 id 序 {ids} 與標準不符")
    mrows = spec.table("8 個 discourse_mode") or []
    mids = [row.get("id", "").strip("`") for row in mrows]
    if sorted(mids) != sorted(MODE_IDS):
        r.fail("S9", f"mode id {mids} 與標準不符")

    # S10 灰區與硬規則提到的章名都存在
    for ch in re.findall(r"`([^`]+)`\[\d+\]", spec.raw):
        if ch not in corpus.chapter_paras:
            r.fail("S10", f"SPEC 提到的章名「{ch}」在語料裡不存在")

    # S11 引號體例分裂宣告與實測一致
    for mark, pat in [("“", r"`“ ”`：((?:b\d{2} ?)+)"),
                      ("「", r"`「 」`：((?:b\d{2} ?)+)")]:
        m = re.search(pat, spec.raw)
        if not m:
            r.fail("S11", f"讀不到 `{mark}` 的批次宣告")
            continue
        declared = set(re.findall(r"b\d{2}", m.group(1)))
        for b in BATCH_IDS:
            a_cnt, c_cnt = corpus.batch_quote_style(b)
            uses = "“" if c_cnt > a_cnt else "「"
            if (b in declared) != (uses == mark):
                r.fail("S11", f"{b} 宣告用 {mark} = {b in declared}，"
                              f"實際「{a_cnt} “{c_cnt}")

    # S12 試金石：兩段必須分屬認證側與技術側
    m = re.search(r"\*\*`(.+?)`\[(\d+)\] 含 XII；`(.+?)`\[(\d+)\] 非空且不含 XII。\*\*",
                  spec.raw)
    if not m:
        r.fail("S12", "讀不到 XII 試金石條文——條文被改寫，斷言已停跑")
    else:
        pos, neg = (m.group(1), int(m.group(2))), (m.group(3), int(m.group(4)))
        cert = {a.key() for a in spec.section_anchors("認證側", 0)}
        tech = {a.key() for a in spec.section_anchors("技術側", 0)}
        if pos not in cert:
            r.fail("S12", f"試金石正例 {pos} 不在認證側表")
        if neg not in tech:
            r.fail("S12", f"試金石反例 {neg} 不在技術側表")

    # S13 六章裸年號存在，且各有第 1 段
    m = re.search(r"六章裸年號（([^）]+)）", spec.raw)
    if not m:
        r.fail("S13", "A 類條文讀不到裸年號章清單——條文被改寫，斷言已停跑")
    else:
        for ch in m.group(1).split():
            if ch not in corpus.chapter_paras:
                r.fail("S13", f"裸年號章「{ch}」在語料裡不存在")
            elif 1 not in corpus.chapter_paras[ch]:
                r.fail("S13", f"裸年號章「{ch}」沒有第 1 段")

    # S14 每張錨點表都被至少一條 A 類條文提到
    a_block = spec.raw.split("### A 類")[-1].split("### B 類")[0]
    for frag, idx in ANCHOR_SECTIONS:
        probe = frag.split("／")[0]
        if probe not in a_block and spec.table(frag, idx):
            r.fail("S14", f"錨點表「{frag}」沒有任何 A 類條文引用它")

    # S15 底本事實 7 的硬斷行段全表，逐段回語料對拍
    m = re.search(r"\*\*硬斷行段全表（(\d+) 段）\*\*：(.+?)。", spec.raw, re.S)
    if not m:
        r.fail("S15", "讀不到硬斷行段全表——底本事實 7 被改寫，斷言已停跑")
    else:
        declared_n = int(m.group(1))
        listed: set[tuple[str, int]] = set()
        for chunk in m.group(2).split("、"):
            cm = re.match(r"`([^`]+)`((?:\[\d+\])+)$", chunk.strip())
            if not cm:
                r.fail("S15", f"硬斷行段全表格式壞掉，解析不出：{chunk.strip()!r}")
                continue
            ch = cm.group(1)
            for i in (int(x) for x in re.findall(r"\[(\d+)\]", cm.group(2))):
                listed.add((ch, i))
        if len(listed) != declared_n:
            r.fail("S15", f"硬斷行段全表宣告 {declared_n} 段，實際列出 {len(listed)} 段")
        actual = {(ch, i) for (ch, i), (_b, t) in corpus.para.items() if len(t) == 30}
        for key in sorted(listed - actual):
            got = corpus.para.get(key)
            n = "不存在" if got is None else f"{len(got[1])} 字"
            r.fail("S15", f"硬斷行段全表列了 `{key[0]}`[{key[1]}]，但它在語料裡是{n}，不是 30 字")
        for key in sorted(actual - listed):
            r.fail("S15", f"`{key[0]}`[{key[1]}] 是 30 字硬斷行段，但沒列進全表")

    # S16 底本事實 8 的來源殘留全表，雙向對拍
    # 「〈 〉」是佚文的校勘夾注（底本事實 3 管），這裡只咬括號類殘留。
    m = re.search(r"\*\*來源殘留全表（(\d+) 處）\*\*：(.+?)。", spec.raw, re.S)
    if not m:
        r.fail("S16", "讀不到來源殘留全表——底本事實 8 被改寫，斷言已停跑")
    else:
        declared_n = int(m.group(1))
        listed_r: dict[tuple[str, int], str] = {}
        for chunk in m.group(2).split("、"):
            cm = re.match(r"`([^`]+)`\[(\d+)\]\s*`([^`]+)`$", chunk.strip())
            if not cm:
                r.fail("S16", f"來源殘留全表格式壞掉，解析不出：{chunk.strip()!r}")
                continue
            listed_r[(cm.group(1), int(cm.group(2)))] = cm.group(3)
        if len(listed_r) != declared_n:
            r.fail("S16", f"來源殘留全表宣告 {declared_n} 處，實際列出 {len(listed_r)} 處")
        for key, frag in sorted(listed_r.items()):
            got = corpus.para.get(key)
            if got is None:
                r.fail("S16", f"來源殘留全表列了 `{key[0]}`[{key[1]}]，語料裡沒有這一段")
            elif frag not in got[1]:
                r.fail("S16", f"`{key[0]}`[{key[1]}] 裡找不到宣告的殘留 {frag!r}")
        actual_r = {(ch, i) for (ch, i), (_b, t) in corpus.para.items()
                    if any(c in t for c in "（）()[]")}
        for key in sorted(actual_r - set(listed_r)):
            r.fail("S16", f"`{key[0]}`[{key[1]}] 含括號類來源殘留，但沒列進全表")

    # S17 發包輸入 bNN.md 的段落文字必須與底本逐字相同、且剛好涵蓋全部段落。
    # 兩邊一旦漂開，判者讀的與驗收器對拍的就是兩份文本，A15 與
    # check-reason-quotes.py 的每一條結果都變成噪音，而且不會有任何斷言報錯。
    covered: set[tuple[str, int]] = set()
    for path in sorted(HERE.glob("b*.md")):
        chapter = None
        for line in path.read_text(encoding="utf-8").splitlines():
            head = re.match(r"^## (.+?)（\d+ 段）\s*$", line)
            if head:
                chapter = head.group(1)
                continue
            row = re.match(r"^\[(\d+)\] (.*)$", line)
            if not row or chapter is None:
                continue
            key = (chapter, int(row.group(1)))
            covered.add(key)
            got = corpus.para.get(key)
            if got is None:
                r.fail("S17", f"{path.name} 有 `{key[0]}`[{key[1]}]，底本裡沒有這一段")
            elif got[1] != row.group(2):
                r.fail("S17", f"{path.name} `{key[0]}`[{key[1]}] 的文字與底本不符")
    if not covered:
        r.fail("S17", "一段發包輸入都沒解析到——bNN.md 格式已變，斷言已停跑")
    for key in sorted(set(corpus.para) - covered):
        r.fail("S17", f"底本的 `{key[0]}`[{key[1]}] 沒有出現在任何 bNN.md")

    return gmap


# ---------------------------------------------------------------- 批次輸出

def load_batch(path: pathlib.Path, r: Report):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:                                   # noqa: BLE001
        r.fail("A1", f"{path.name} 不是合法 JSON：{exc}")
        return None
    if not isinstance(data.get("rows"), list):
        r.fail("A1", f"{path.name} 沒有 rows 陣列")
        return None
    return data


def check_rows(batch: str, rows: list, spec: Spec, corpus: Corpus,
               gmap: dict[str, str], r: Report) -> dict[tuple[str, int], dict]:
    want = {k for k, (b, _t) in corpus.para.items() if b == batch}
    got: dict[tuple[str, int], dict] = {}

    for row in rows:
        ch, pi = row.get("chapter"), row.get("para_index")
        if not isinstance(ch, str) or not isinstance(pi, int):
            r.fail("A1", f"{batch} 有列缺 chapter/para_index：{str(row)[:60]}")
            continue
        key = (ch, pi)
        if key in got:
            r.fail("A1", f"{batch} {ch}[{pi}] 重複出現")
        got[key] = row
        if key not in corpus.para:
            r.fail("A1", f"{batch} {ch}[{pi}] 不存在於語料")
            continue
        if corpus.para[key][0] != batch:
            r.fail("A1", f"{batch} {ch}[{pi}] 其實屬於 {corpus.para[key][0]}")

        doms = row.get("domains")
        modes = row.get("modes")
        reason = row.get("reason", "")
        if not isinstance(doms, list) or not isinstance(modes, list):
            r.fail("A1", f"{batch} {ch}[{pi}] domains/modes 不是陣列")
            continue
        if not isinstance(reason, str) or not reason.strip():
            r.fail("A1", f"{batch} {ch}[{pi}] reason 為空")

        # A11 id 合法
        for d in doms:
            if d not in DOMAIN_IDS:
                r.fail("A11", f"{batch} {ch}[{pi}] 非法 domain「{d}」")
        for md in modes:
            if md not in MODE_IDS:
                r.fail("A11", f"{batch} {ch}[{pi}] 非法 mode「{md}」")
        if len(set(doms)) != len(doms):
            r.fail("A11", f"{batch} {ch}[{pi}] domains 有重複")

        # A12 worked_instance 全書 0 段
        if "worked_instance" in modes:
            r.fail("A12", f"{batch} {ch}[{pi}] 出現 worked_instance")

        # A13 reason 長度 >= N*20
        if doms and len(reason) < len(doms) * 20:
            r.fail("A13", f"{batch} {ch}[{pi}] 標 {len(doms)} 格但 reason "
                          f"只有 {len(reason)} 字")

        # A14 章名歸群
        if ch in corpus.chapter_paras and ch not in gmap:
            r.fail("A14", f"{batch} {ch} 不屬於分派表任何一群")

        # A15 引號種類：reason 引原文時必須與該段底本一致
        text = corpus.para[key][1]
        wrong = "「」" if "“" in text else "“”"
        if text.count("「") or text.count("“"):
            op, cl = wrong[0], wrong[1]
            for span in re.findall(re.escape(op) + r"([^" + re.escape(op + cl)
                                   + r"]{6,})" + re.escape(cl), reason):
                if span in text:
                    r.fail("A15", f"{batch} {ch}[{pi}] reason 用 {op}{cl} 引原文，"
                                  f"該段底本用另一種：{span[:20]}")

    missing = want - set(got)
    extra = set(got) - want
    if missing:
        r.fail("A1", f"{batch} 缺 {len(missing)} 段：{sorted(missing)[:5]}")
    if extra:
        r.fail("A1", f"{batch} 多出 {len(extra)} 段：{sorted(extra)[:5]}")
    return got


def check_anchors(spec: Spec, got: dict[tuple[str, int], dict],
                  batch: str, r: Report) -> None:
    for a in spec.anchors:
        if a.batch != batch or a.key() not in got:
            continue
        row = got[a.key()]
        doms = set(row.get("domains") or [])
        if a.empty and doms:
            r.fail("A2", f"{a.label()} 必須判空，實得 {sorted(doms)}")
        if a.nonempty and not doms:
            r.fail("A4", f"{a.label()} 必須非空，實得 []")
        for bad in a.forbid_d & doms:
            r.fail("A4", f"{a.label()} 不得含 {bad}，實得 {sorted(doms)}")
        for grp in a.require:
            if not (grp & doms):
                r.fail("A3", f"{a.label()} 必須含 {'或'.join(sorted(grp))}，"
                             f"實得 {sorted(doms)}")


def check_prose_rules(spec: Spec, got: dict[tuple[str, int], dict],
                      r: Report) -> None:
    # A10 九術清單不得含 XII
    m = re.search(r"\*\*`(.+?)`\[(\d+)\]（九術清單）不得含 XII", spec.raw)
    if not m:
        r.fail("A10", "讀不到九術條文——條文被改寫，斷言已停跑")
    else:
        key = (m.group(1), int(m.group(2)))
        if key in got and "XII" in (got[key].get("domains") or []):
            r.fail("A10", f"`{key[0]}`[{key[1]}] 是列術不是行術，不得含 XII")

    # A16 六章裸年號第 1 段 reason 必須出現「夫差」
    m = re.search(r"六章裸年號（([^）]+)）各自第 1 段的 `reason` 必須出現「(.+?)」",
                  spec.raw)
    if not m:
        r.fail("A16", "讀不到裸年號條文——條文被改寫，斷言已停跑")
    else:
        who = m.group(2)
        for ch in m.group(1).split():
            row = got.get((ch, 1))
            if row is not None and who not in (row.get("reason") or ""):
                r.fail("A16", f"`{ch}`[1] 的 reason 沒註明「{who}」")


def report_b_class(all_rows: dict[tuple[str, int], dict], corpus: Corpus,
                   gmap: dict[str, str], r: Report) -> None:
    dom = Counter()
    mod = Counter()
    empty_by_group = Counter()
    total_by_group = Counter()
    empties = 0
    for (ch, _pi), row in all_rows.items():
        doms = row.get("domains") or []
        dom.update(doms)
        mod.update(row.get("modes") or [])
        g = gmap.get(ch, "?")
        total_by_group[g] += 1
        if not doms:
            empties += 1
            empty_by_group[g] += 1
    r.note("B", f"全書判空 {empties} 段 / {len(all_rows)}")
    for g in GROUP_IDS:
        if total_by_group[g]:
            hit = total_by_group[g] - empty_by_group[g]
            r.note("B", f"{g} 命中 {hit}/{total_by_group[g]} "
                        f"({hit / total_by_group[g]:.0%})，判空 {empty_by_group[g]}")
    r.note("B", "領域分佈 " + "、".join(
        f"{d}:{dom[d]}" for d in DOMAIN_IDS if dom[d]))
    r.note("B", "體裁分佈 " + "、".join(
        f"{m}:{mod[m]}" for m in MODE_IDS if mod[m]))
    zero = [d for d in DOMAIN_IDS if not dom[d]]
    if zero:
        r.note("B", f"零段領域 {zero}")


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--check-spec", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    corpus = Corpus()
    spec = Spec(SPEC_PATH)
    r = Report()
    gmap = check_spec(spec, corpus, r)

    if args.check_spec:
        return r.dump("check-spec")

    paths = [pathlib.Path(f) for f in args.files]
    if args.all:
        paths = sorted(OUT_DIR.glob("b*.json"))
    if not paths:
        print("沒有要驗的批次；用 --check-spec 或給 out/bNN.json")
        return r.dump("check-spec only")

    all_rows: dict[tuple[str, int], dict] = {}
    for p in paths:
        data = load_batch(p, r)
        if data is None:
            continue
        batch = p.stem
        got = check_rows(batch, data["rows"], spec, corpus, gmap, r)
        check_anchors(spec, got, batch, r)
        all_rows.update(got)

    check_prose_rules(spec, all_rows, r)

    if args.all:
        if len(all_rows) != len(corpus.para):
            r.fail("A1", f"--all 共收 {len(all_rows)} 段，語料 {len(corpus.para)} 段")
        report_b_class(all_rows, corpus, gmap, r)

    return r.dump("accept " + ", ".join(p.name for p in paths))


if __name__ == "__main__":
    sys.exit(main())
