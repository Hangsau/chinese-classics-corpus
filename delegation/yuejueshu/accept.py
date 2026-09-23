#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""越絕書 標註驗收器。

錨點一律由本檔現場解析 SPEC.md 的表格與條文，不在程式裡手抄任何章名、段號或引句。
表格用「表頭欄名」定位欄位，不用欄位序——SPEC 增刪欄位不會讓斷言靜默失效。

與吳越春秋版的差別（改動過的地方都在這裡，不要反向抄回去）：
  - 六群 G1–G6、十七批 b01–b17。
  - 分派表的群→批一律用**集合相等**比對，不用 `lo <= b <= hi` 區間法。本書六群
    在卷次上交錯（G1 拿 b03 b08，而 b04–b07 全是 G2），區間法會讓 G2 把 b03／b08
    一起收進 allowed 而靜默放行。
  - 技術側只 forbid XII、不要求非空（占候條目判空＋formalization 是正解）。
  - S11 斷言全書彎引號為 0，不逐批分引號家族。
  - S15／S16 換成 `□` 闕字與 `〈 〉` 夾注兩張全表（本書沒有硬斷行殘句，也沒有
    括號類來源殘留，那兩件事改成反向斷言）。

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
RAW_PATH = REPO / "translations" / "yuejueshu" / "raw" / "original.txt"
MANIFEST_PATH = HERE / "MANIFEST.json"

sys.path.insert(0, str(REPO / "scripts"))
from corpus_text import split_paragraphs  # noqa: E402

DOMAIN_IDS = ["I", "II", "III", "IV", "V", "VI", "VII",
              "VIII", "IX", "X", "XI", "XII", "XIII"]
MODE_IDS = ["observation", "proposition", "prescription", "formalization",
            "narrative", "ritual", "expression", "worked_instance"]
GROUP_IDS = ["G1", "G2", "G3", "G4", "G5", "G6"]
BATCH_IDS = [f"b{i:02d}" for i in range(1, 18)]

_ROMAN_RE = re.compile(
    r"(?<![A-Za-z])(XIII|XII|XI|IX|VIII|VII|VI|IV|III|II|X|V|I)(?![A-Za-z])")

# 每張錨點表的語意。key = 標題子字串 + 該標題下的第幾張表。
# 只描述「這張表是什麼意思」，段數與成員一律由 SPEC 現場解析。
SECTION_SEMANTICS = {
    ("必須判空的錨點", 0): {"empty": True},
    ("認證側", 0): {"require": [{"XII"}]},
    ("破除側", 0): {"require": [{"XI"}], "forbid_d": {"XII"}},
    # 技術側刻意不要求非空：占候條目照 §2.5① 判空＋formalization 是正解，
    # 要求非空等於逼判者湊格。這一側要擋的是 XII 外溢，不是判空。
    ("技術側", 0): {"forbid_d": {"XII"}},
    ("說辭側與過度側", 0): {"nonempty": True, "forbid_d": {"XII"}},
    ("X 的兩側", 0): {"require": [{"X"}]},
    ("X 的兩側", 1): {"nonempty": True, "forbid_d": {"X"}},
    ("G1 不是判空群", 0): {"nonempty": True},
    ("G3 不是判空群", 0): {"nonempty": True},
    ("G5 不是判空群", 0): {"nonempty": True},
    ("G6 不是判空群", 0): {"nonempty": True},
    ("G4 登錄之外", 0): {"nonempty": True, "forbid_d": {"XII"}},
}

# A 類條文必須引用到的錨點表（防「加了表卻沒加條文」）
ANCHOR_SECTIONS = list(SECTION_SEMANTICS)

# 標題裡帶「（N 段」宣告的錨點表。X 的兩側把段數寫在粗體行，另外處理。
HEADING_COUNT_SECTIONS = ["必須判空的錨點", "認證側", "破除側", "技術側",
                          "說辭側與過度側", "G1 不是判空群", "G3 不是判空群",
                          "G5 不是判空群", "G6 不是判空群", "G4 登錄之外"]

# 底本事實 4／5 的異體字正負雙面：(本書用字, 宣告 regex, 不該出現的字)
VARIANT_PAIRS = [
    ("為", r"`為`（全書 (\d+) 次", "爲"),
    ("眾", r"`眾`（(\d+) 次，沒有 `衆`）", "衆"),
    ("裏", r"`裏`（(\d+) 次，沒有 `裡`）", "裡"),
    ("餘", r"`餘`（(\d+) 次，沒有 `余`）", "余"),
    ("句踐", r"`句踐`（(\d+) 次，沒有 `勾踐`）", "勾踐"),
    ("闔廬", r"`闔廬`（(\d+) 次，沒有 `闔閭`）", "闔閭"),
    ("無餘", r"`無餘`（(\d+) 次，沒有 `無余`）", "無余"),
]


class Report:
    def __init__(self) -> None:
        self.fails: list[str] = []
        self.notes: list[str] = []

    def fail(self, code: str, msg: str) -> None:
        self.fails.append(f"[{code}] {msg}")

    def note(self, code: str, msg: str) -> None:
        self.notes.append(f"[{code}] {msg}")

    def codes(self) -> set[str]:
        """探針用：in-process 取 FAIL 碼集合，不要去 grep stdout。"""
        return {f.split("]")[0].lstrip("[") for f in self.fails}

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
        self.raw_text = RAW_PATH.read_text(encoding="utf-8")
        paras = split_paragraphs(self.raw_text)
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

    def batch_text(self, b: str) -> str:
        return "".join(t for (_c, _i), (bb, t) in self.para.items() if bb == b)


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
    rows = spec.table("閘門：六個體例群")
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
        # 批：集合相等，雙向。本書六群在卷次上交錯，用區間法（lo <= b <= hi）
        # 會讓 G2 的 b02..b15 把 G1 的 b03／b08 一起收進 allowed 而靜默放行。
        declared_b = set(re.findall(r"b\d{2}", row.get("批", "")))
        if not declared_b:
            r.fail("S6", f"{gid} 讀不到批宣告")
        else:
            bad = declared_b - set(BATCH_IDS)
            if bad:
                r.fail("S6", f"{gid} 宣告了不存在的批 {sorted(bad)}")
            real_b = {corpus.batch_of[c] for c in chapters
                      if c in corpus.batch_of}
            if declared_b != real_b:
                r.fail("S6", f"{gid} 宣告批 {sorted(declared_b)}，"
                             f"該群章實際落在 {sorted(real_b)}")
    if seen_groups != GROUP_IDS:
        r.fail("S6", f"分派表群序 {seen_groups}，預期 {GROUP_IDS}")
    missing = set(corpus.chapter_paras) - set(gmap)
    if missing:
        r.fail("S6", f"有 {len(missing)} 章沒被分派表涵蓋：{sorted(missing)}")
    # 每一批只屬一個群（SPEC 明文宣告「十七批每一批都只屬一個體例群」）
    batch_groups: dict[str, set[str]] = defaultdict(set)
    for ch, g in gmap.items():
        if ch in corpus.batch_of:
            batch_groups[corpus.batch_of[ch]].add(g)
    for b, gs in sorted(batch_groups.items()):
        if len(gs) > 1:
            r.fail("S6", f"{b} 橫跨 {sorted(gs)} 兩群，與「一批只屬一群」牴觸")
    uncovered = set(BATCH_IDS) - set(batch_groups)
    if uncovered:
        r.fail("S6", f"這些批沒被任何群涵蓋：{sorted(uncovered)}")
    return gmap


# ---------------------------------------------------------------- check-spec

def check_spec(spec: Spec, corpus: Corpus, r: Report) -> dict[str, str]:
    # S0 錨點未填完的佔位標記還在，任何其他綠燈都不算數
    if "ANCHORS-PENDING" in spec.raw:
        r.fail("S0", "SPEC 還留著 ANCHORS-PENDING 標記，錨點沒填完，不准發包")

    # S1 每張錨點表都在，且解析出的錨點數 == 各表列數總和
    expected_rows = 0
    for frag, idx in ANCHOR_SECTIONS:
        rows = spec.table(frag, idx)
        if rows is None:
            r.fail("S1", f"找不到錨點表「{frag}」第 {idx} 張——"
                         f"SPEC 標題或表頭被改過，這一族斷言已經停跑")
        else:
            expected_rows += len(rows)
    if not spec.anchors:
        r.fail("S1", "一條錨點都沒解析到")
    elif len(spec.anchors) != expected_rows:
        # 驗數量不驗非空：某一列的「章[段]」格式壞掉會讓該列悄悄消失，
        # 其餘列照樣命中、涵蓋率掉一格而自檢照樣全綠（晏子型局部失明）。
        r.fail("S1", f"錨點表共 {expected_rows} 列，只解析出 "
                     f"{len(spec.anchors)} 條錨點——有列的「章[段]」格式壞掉")

    # S2 標題宣告段數 == 表格列數
    for frag in HEADING_COUNT_SECTIONS:
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
        # 硬規則 6：引句不得跨越內層引號拼接
        if "：「" in a.quote:
            r.fail("S3", f"{a.label()} 引句跨越了內層引號（含 `：「`），違反硬規則 6")

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
        total = int(m.group(len(BATCH_IDS) + 1))
        if total != sum(corpus.batch_size.values()):
            r.fail("S5", f"合計宣告 {total}，"
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
            if int(row.get("字", "0")) != len(corpus.batch_text(b)):
                r.fail("S5", f"批次表 {b} 字數 {row.get('字')}，"
                             f"實際 {len(corpus.batch_text(b))}")
            declared_ch = [c for c in row.get("章", "").split("／") if c]
            if declared_ch != corpus.batch_chapters[b]:
                r.fail("S5", f"批次表 {b} 章名與 MANIFEST 不符："
                             f"{declared_ch} vs {corpus.batch_chapters[b]}")

    # S7 底本異體字與引號總數，正負雙面
    for ch, pat, bad in VARIANT_PAIRS:
        n = spec.number(pat)
        if n is None:
            r.fail("S7", f"讀不到 `{ch}` 的字數宣告——條文被改寫，這一條已停跑")
        elif n != corpus.full.count(ch):
            r.fail("S7", f"`{ch}` 宣告 {n} 次，實際 {corpus.full.count(ch)} 次")
        if f"沒有一個 `{bad}`" in spec.raw or f"沒有 `{bad}`" in spec.raw:
            if corpus.full.count(bad):
                r.fail("S7", f"SPEC 宣告沒有 `{bad}`，"
                             f"實際 {corpus.full.count(bad)} 次")
        else:
            r.fail("S7", f"讀不到「沒有 `{bad}`」的宣告")
    qm = re.search(r"`「` (\d+) `」` (\d+)、`“` (\d+) `”` (\d+)", spec.raw)
    if not qm:
        r.fail("S7", "讀不到全書引號總數宣告")
    else:
        for i, c in enumerate("「」“”"):
            real = corpus.full.count(c)
            if int(qm.group(i + 1)) != real:
                r.fail("S7", f"`{c}` 宣告 {qm.group(i + 1)}，實際 {real}")

    # S8 A 類條文宣告的段數 vs 錨點表列數
    a_counts = [("必須判空的錨點", 0, r"「必須判空」的 (\d+) 段"),
                ("認證側", 0, r"認證側 (\d+) 段含 XII"),
                ("破除側", 0, r"破除側 (\d+) 段全部含 XI"),
                ("技術側", 0, r"技術側 (\d+) 段全部不含 XII"),
                ("說辭側與過度側", 0, r"說辭側與過度側 (\d+) 段 `domains` 全部非空"),
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

    # S10 SPEC 正文提到的每一個 `章`[段] 都要在語料裡存在（章名與段號都驗）
    for ch, idx in re.findall(r"`([^`]+)`\[(\d+)\]", spec.raw):
        if ch not in corpus.chapter_paras:
            r.fail("S10", f"SPEC 提到的章名「{ch}」在語料裡不存在")
        elif int(idx) not in corpus.chapter_paras[ch]:
            r.fail("S10", f"SPEC 提到 `{ch}`[{idx}]，該章沒有這一段")

    # S11 全書彎引號為 0（不逐批分引號家族——本書 17 批統一 `「 」`）
    for mark in "“”":
        if corpus.full.count(mark):
            r.fail("S11", f"全書應無 `{mark}`，實際 {corpus.full.count(mark)} 個")
    m = re.search(r"本書 (\d+) 批全部用 `「 」`", spec.raw)
    if not m:
        r.fail("S11", "A 類條文讀不到「N 批全部用 `「 」`」宣告——條文被改寫，斷言已停跑")
    elif int(m.group(1)) != len(BATCH_IDS):
        r.fail("S11", f"條文說 {m.group(1)} 批，實際 {len(BATCH_IDS)} 批")
    else:
        for b in BATCH_IDS:
            t = corpus.batch_text(b)
            if t.count("“") or t.count("”"):
                r.fail("S11", f"{b} 含彎引號，與「17 批全部用 `「 」`」牴觸")

    # S12 兩個試金石條文：解析得出，且兩邊各自落在正確的錨點表
    m = re.search(r"\*\*`(.+?)`\[(\d+)\] 非空且含 (\w+) 且不含 XII；"
                  r"`(.+?)`\[(\d+)\] 不含 XII。\*\*", spec.raw)
    if not m:
        r.fail("S12", "讀不到 G4 試金石條文（記軍氣 [1] vs [2]）——條文被改寫，斷言已停跑")
    else:
        pos, neg = (m.group(1), int(m.group(2))), (m.group(4), int(m.group(5)))
        out = {a.key(): a for a in spec.section_anchors("G4 登錄之外", 0)}
        tech = {a.key() for a in spec.section_anchors("技術側", 0)}
        if pos not in out:
            r.fail("S12", f"G4 試金石正例 {pos} 不在「G4 登錄之外」表")
        elif not any(m.group(3) in g for g in out[pos].require):
            r.fail("S12", f"條文要求 {pos} 含 {m.group(3)}，表的「必須含」欄沒有")
        if neg not in tech:
            r.fail("S12", f"G4 試金石反例 {neg} 不在技術側表")
        if pos[0] != neg[0]:
            r.fail("S12", f"G4 試金石兩段不同章（{pos[0]} vs {neg[0]}），"
                          f"「同章相鄰」的說法不成立")

    m = re.search(r"\*\*`(.+?)`\[(\d+)\] 含 X，而同群的 `(.+?)`\[(\d+)\]、"
                  r"`(.+?)`\[(\d+)\] 判空。\*\*", spec.raw)
    if not m:
        r.fail("S12", "讀不到配套 (2) 試金石條文（冢的三段）——條文被改寫，斷言已停跑")
    else:
        hit = (m.group(1), int(m.group(2)))
        empties = [(m.group(3), int(m.group(4))), (m.group(5), int(m.group(6)))]
        xs = {a.key() for a in spec.section_anchors("X 的兩側", 0)}
        es = {a.key() for a in spec.section_anchors("必須判空的錨點", 0)}
        if hit not in xs:
            r.fail("S12", f"配套 (2) 試金石命中段 {hit} 不在 X 命中側表")
        for k in empties:
            if k not in es:
                r.fail("S12", f"配套 (2) 試金石判空段 {k} 不在必須判空表")
        for k in [hit] + empties:
            if k in corpus.para and not ({"冢", "葬"} & set(corpus.para[k][1])):
                r.fail("S12", f"{k[0]}[{k[1]}] 既無「冢」也無「葬」，"
                              f"這組試金石的前提不成立")
        if len({gmap.get(k[0]) for k in [hit] + empties}) != 1:
            r.fail("S12", "配套 (2) 試金石三段不同群，「同群」的說法不成立")

    # S13 書級規模宣告 + `卷五` 不是純卷題段
    m = re.search(r"\*\*(\d+) 章 (\d+) 段 ([\d,]+) 字\*\*", spec.raw)
    if not m:
        r.fail("S13", "讀不到書級規模宣告（N 章 N 段 N 字）——條文被改寫，斷言已停跑")
    else:
        if int(m.group(1)) != len(corpus.chapter_paras):
            r.fail("S13", f"宣告 {m.group(1)} 章，實際 {len(corpus.chapter_paras)} 章")
        if int(m.group(2)) != len(corpus.para):
            r.fail("S13", f"宣告 {m.group(2)} 段，實際 {len(corpus.para)} 段")
        if int(m.group(3).replace(",", "")) != len(corpus.full):
            r.fail("S13", f"宣告 {m.group(3)} 字，307 段實際 {len(corpus.full)} 字")
    m = re.search(r"\*\*底本檔本身是 ([\d,]+) 字.*?多出來的部分是"
                  r"(.+?)條不足 12 字的地志短條目\*\*（(.+?)）。", spec.raw, re.S)
    if not m:
        r.fail("S13", "讀不到底本檔字數與短條目全表——條文被改寫，斷言已停跑")
    else:
        if int(m.group(1).replace(",", "")) != len(corpus.raw_text):
            r.fail("S13", f"底本檔宣告 {m.group(1)} 字，"
                          f"實際 {len(corpus.raw_text)} 字")
        listed = re.findall(r"`([^`]+)`", m.group(3))
        dropped = [ln.strip() for ln in corpus.raw_text.split("\n")
                   if ln.strip() and not ln.startswith("===")
                   and ln.strip() not in {t for _b, t in corpus.para.values()}]
        if listed != dropped:
            r.fail("S13", f"短條目全表與實際濾掉的不符：宣告 {listed}，"
                          f"實際 {dropped}")
        want_n = {"九": 9}.get(m.group(2).strip(), None)
        if want_n is None:
            r.fail("S13", f"短條目條數「{m.group(2).strip()}」讀不成數字")
        elif want_n != len(dropped):
            r.fail("S13", f"宣告 {want_n} 條短條目，實際 {len(dropped)} 條")
    m = re.search(r"\*\*正文是完整的請糴故事\*\*（`(.+?)`\[(\d+)\]「(.+?)」）", spec.raw)
    if not m:
        r.fail("S13", "讀不到 `卷五` 正文性質的條文——條文被改寫，斷言已停跑")
    else:
        key = (m.group(1), int(m.group(2)))
        got = corpus.para.get(key)
        if got is None:
            r.fail("S13", f"`{key[0]}`[{key[1]}] 在語料裡不存在")
        elif m.group(3) not in got[1]:
            r.fail("S13", f"`{key[0]}`[{key[1]}] 裡找不到宣告的引句 {m.group(3)[:20]}")

    # G1／G2 的散文段數要與分派表對得上（兩份真相，人改一邊就會漂）
    for pat, gid in [(r"全書 \d+ 段裡 \*\*(\d+) 段（\d+%）是地理登錄\*\*", "G1"),
                     (r"\*\*敘事只佔 (\d+) 段（\d+%）。\*\*", "G2")]:
        n = spec.number(pat)
        if n is None:
            r.fail("S13", f"讀不到 {gid} 的散文段數宣告——條文被改寫，斷言已停跑")
        else:
            real = sum(len(v) for c, v in corpus.chapter_paras.items()
                       if gmap.get(c) == gid)
            if n != real:
                r.fail("S13", f"散文說 {gid} {n} 段，分派表歸群後實際 {real} 段")

    # S14 每張錨點表都被至少一條 A 類條文提到
    a_block = spec.raw.split("### A 類")[-1].split("### B 類")[0]
    for frag, idx in ANCHOR_SECTIONS:
        probe = frag.split("／")[0]
        if probe not in a_block and spec.table(frag, idx):
            r.fail("S14", f"錨點表「{frag}」沒有任何 A 類條文引用它")

    # S15 底本事實 3 的 `□` 闕字全表，逐段逐次雙向對拍
    m = re.search(r"\*\*`□` 闕字全表（(\d+) 段 (\d+) 處）\*\*：(.+?)。", spec.raw, re.S)
    if not m:
        r.fail("S15", "讀不到 `□` 闕字全表——底本事實 3 被改寫，斷言已停跑")
    else:
        declared_seg, declared_hit = int(m.group(1)), int(m.group(2))
        listed: dict[tuple[str, int], int] = {}
        for chunk in m.group(3).split("、"):
            cm = re.match(r"`([^`]+)`\[(\d+)\]×(\d+)$", chunk.strip())
            if not cm:
                r.fail("S15", f"`□` 全表格式壞掉，解析不出：{chunk.strip()!r}")
                continue
            listed[(cm.group(1), int(cm.group(2)))] = int(cm.group(3))
        if len(listed) != declared_seg:
            r.fail("S15", f"`□` 全表宣告 {declared_seg} 段，實際列出 {len(listed)} 段")
        if sum(listed.values()) != declared_hit:
            r.fail("S15", f"`□` 全表宣告 {declared_hit} 處，"
                          f"逐段相加 {sum(listed.values())} 處")
        for key, n in sorted(listed.items()):
            got = corpus.para.get(key)
            if got is None:
                r.fail("S15", f"`□` 全表列了 `{key[0]}`[{key[1]}]，語料裡沒有這一段")
            elif got[1].count("□") != n:
                r.fail("S15", f"`{key[0]}`[{key[1]}] 宣告 {n} 個 `□`，"
                              f"實際 {got[1].count('□')} 個")
        actual = {k for k, (_b, t) in corpus.para.items() if "□" in t}
        for key in sorted(actual - set(listed)):
            r.fail("S15", f"`{key[0]}`[{key[1]}] 含 `□`，但沒列進全表")
        if corpus.full.count("□") != declared_hit:
            r.fail("S15", f"全書 `□` 宣告 {declared_hit} 處，"
                          f"實際 {corpus.full.count('□')} 處")

    # S16 底本事實 2 的 `〈 〉` 夾注全表，逐處雙向對拍；
    #     外加「沒有硬斷行殘句、沒有括號類來源殘留」的反向斷言。
    m = re.search(r"\*\*`〈 〉` 夾注全表（(\d+) 處）\*\*：(.+?)。\n", spec.raw, re.S)
    if not m:
        r.fail("S16", "讀不到 `〈 〉` 夾注全表——底本事實 2 被改寫，斷言已停跑")
    else:
        declared_n = int(m.group(1))
        listed_j: dict[tuple[str, int], str] = {}
        for chunk in m.group(2).split("、"):
            cm = re.match(r"`([^`]+)`\[(\d+)\]\s*`([^`]+)`$", chunk.strip())
            if not cm:
                r.fail("S16", f"`〈 〉` 全表格式壞掉，解析不出：{chunk.strip()!r}")
                continue
            listed_j[(cm.group(1), int(cm.group(2)))] = cm.group(3)
        if len(listed_j) != declared_n:
            r.fail("S16", f"`〈 〉` 全表宣告 {declared_n} 處，"
                          f"實際列出 {len(listed_j)} 處")
        for key, frag in sorted(listed_j.items()):
            got = corpus.para.get(key)
            if got is None:
                r.fail("S16", f"`〈 〉` 全表列了 `{key[0]}`[{key[1]}]，語料裡沒有這一段")
            elif frag not in got[1]:
                r.fail("S16", f"`{key[0]}`[{key[1]}] 裡找不到宣告的夾注 {frag!r}")
            elif got[1].count("〈") != 1:
                r.fail("S16", f"`{key[0]}`[{key[1]}] 有 {got[1].count('〈')} 處夾注，"
                              f"全表只登錄了 1 處")
        actual_j = {k for k, (_b, t) in corpus.para.items() if "〈" in t}
        for key in sorted(actual_j - set(listed_j)):
            r.fail("S16", f"`{key[0]}`[{key[1]}] 含 `〈 〉` 夾注，但沒列進全表")
        if corpus.full.count("〈") != declared_n \
                or corpus.full.count("〉") != declared_n:
            r.fail("S16", f"全書 `〈` {corpus.full.count('〈')} `〉` "
                          f"{corpus.full.count('〉')}，宣告 {declared_n}")
        # 全表宣告「無一句是評斷語」，逐條確認它們都是「一作某字」型異文
        for key, frag in sorted(listed_j.items()):
            if not frag.startswith("一作"):
                r.fail("S16", f"`{key[0]}`[{key[1]}] 的夾注 {frag!r} 不是「一作某字」型，"
                              f"底本事實 2「無一句是評斷語」的宣告不成立")

    # 反向斷言：本書沒有硬斷行殘句，也沒有括號類來源殘留
    m = re.search(r"\*\*本書沒有硬斷行殘句，也沒有任何括號類來源殘留。\*\*", spec.raw)
    if not m:
        r.fail("S16", "讀不到「沒有硬斷行殘句／括號類殘留」的宣告——條文被改寫，斷言已停跑")
    else:
        dirty = sorted(k for k, (_b, t) in corpus.para.items()
                       if any(c in t for c in "（）()[]"))
        for key in dirty:
            r.fail("S16", f"`{key[0]}`[{key[1]}] 含括號類來源殘留，"
                          f"與「本書一處都沒有」的宣告牴觸")
        # 硬折行的指紋是「某個長度一枝獨秀」，不是「某個長度有好幾段」——
        # 本書地志條目天然集中在二三十字，光看眾數會全是假 FAIL。
        lens = Counter(len(t) for _b, t in corpus.para.values())
        (top_len, top_n), (_l2, n2) = lens.most_common(2)
        if top_n >= 3 * n2:
            r.fail("S16", f"有 {top_n} 段長度都是 {top_len} 字（次高只有 {n2} 段），"
                          f"像硬折行段，與「沒有硬斷行殘句」的宣告牴觸")
    n = spec.number(r"最短段 (\d+) 字，段長分佈自然")
    if n is None:
        r.fail("S16", "讀不到最短段字數宣告——條文被改寫，斷言已停跑")
    else:
        real = min(len(t) for _b, t in corpus.para.values())
        if n != real:
            r.fail("S16", f"最短段宣告 {n} 字，實際 {real} 字")

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
            elif got[0] != path.stem:
                r.fail("S17", f"{path.name} 收了 `{key[0]}`[{key[1]}]，"
                              f"MANIFEST 說它屬 {got[0]}")
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

        # A6 引號種類：本書全書統一 `「 」`，reason 出現彎引號即退回
        for mark in "“”":
            if mark in reason:
                r.fail("A6", f"{batch} {ch}[{pi}] reason 出現 `{mark}`，"
                              f"本書全書統一 `「 」`")
                break

        # A7 字面：reason 不得出現《吳越春秋》字面或自改的異體字
        for bad in ["勾踐", "闔閭", "無余", "爲", "衆", "裡"]:
            if bad in reason:
                r.fail("A7", f"{batch} {ch}[{pi}] reason 出現 `{bad}`，"
                             f"本書底本不用這個字面")

        # A20 引句不得跨越內層引號拼接（硬規則 6）
        text = corpus.para[key][1]
        for span in re.findall(r"「([^「」]{4,})」", reason):
            if "：" in span and span not in text:
                r.fail("A20", f"{batch} {ch}[{pi}] reason 的引句疑似吞掉內層 "
                              f"`「`：{span[:24]}")

        # A21 `〈 〉` 夾注不得被引為承重句
        #
        # 本書六處夾注一律是 `一作「X」。`，**自己就含一對 `「 」`**——只拿
        # `「([^「」]{4,})」` 掃 reason 的引句永遠掃不到它們，這一條會變成文心型
        # 的死斷言（看著活，肯定的那一半從來不叫）。所以夾注原文直接比對，不經
        # 引句切割；下面的 span 迴圈留給夾注是成句評斷語的書。
        if doms:
            spans = re.findall(r"「([^「」]{4,})」", reason)
            for jm in re.findall(r"〈(.+?)〉", text):
                core = jm.strip("。，")
                if core and core in reason:
                    r.fail("A21", f"{batch} {ch}[{pi}] reason 引了 `〈 〉` 夾注："
                                  f"{core[:24]}")
                    continue
                for span in spans:
                    if span in jm:
                        r.fail("A21", f"{batch} {ch}[{pi}] 承重引句落在 "
                                      f"`〈 〉` 夾注裡：{span[:24]}")

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
        for bad in sorted(a.forbid_d & doms):
            r.fail("A4", f"{a.label()} 不得含 {bad}，實得 {sorted(doms)}")
        for grp in a.require:
            if not (grp & doms):
                r.fail("A3", f"{a.label()} 必須含 {'或'.join(sorted(grp))}，"
                             f"實得 {sorted(doms)}")


def _fits_over_box(src: str, span: str) -> bool:
    """span 不是 src 的子字串，但把 src 的 `□` 當任意一字就對得上——即補字。"""
    n = len(span)
    for i in range(len(src) - n + 1):
        if all(src[i + j] == span[j] or src[i + j] == "□" for j in range(n)):
            return True
    return False


def check_prose_rules(spec: Spec, got: dict[tuple[str, int], dict],
                      corpus: Corpus, r: Report) -> None:
    # A22 `□` 必須原樣保留：reason 引到闕字句時不得把 `□` 補成別的字
    m = re.search(r"\*\*`□` 闕字全表（\d+ 段 (\d+) 處）\*\*：(.+?)。", spec.raw, re.S)
    if not m:
        r.fail("A22", "讀不到 `□` 闕字全表——條文被改寫，斷言已停跑")
    else:
        seen = 0
        for chunk in m.group(2).split("、"):
            cm = re.match(r"`([^`]+)`\[(\d+)\](?:×\d+)?$", chunk.strip())
            if not cm:
                continue
            seen += 1
            key = (cm.group(1), int(cm.group(2)))
            row = got.get(key)
            if row is None:
                continue
            src = corpus.para.get(key, ("?", ""))[1]
            for span in re.findall(r"「([^「」]{4,})」", row.get("reason") or ""):
                if span in src:
                    continue
                if _fits_over_box(src, span):
                    r.fail("A22", f"`{key[0]}`[{key[1]}] 的 reason 把闕字補掉了："
                                  f"「{span}」")
        if seen == 0:
            r.fail("A22", "`□` 闕字全表解析到 0 段——格式已變，斷言停跑")

    # 配套 (2) 試金石：三段的實得必須分開，判齊即退回
    m = re.search(r"\*\*`(.+?)`\[(\d+)\] 含 X，而同群的 `(.+?)`\[(\d+)\]、"
                  r"`(.+?)`\[(\d+)\] 判空。\*\*", spec.raw)
    if not m:
        r.fail("A15", "讀不到配套 (2) 試金石條文——條文被改寫，斷言已停跑")
    else:
        hit = got.get((m.group(1), int(m.group(2))))
        others = [got.get((m.group(3), int(m.group(4)))),
                  got.get((m.group(5), int(m.group(6))))]
        if hit is not None and all(o is not None for o in others):
            hx = "X" in (hit.get("domains") or [])
            ox = [bool(o.get("domains")) for o in others]
            if not hx or any(ox):
                r.fail("A15", "配套 (2) 試金石判齊了：命中段含 X ="
                              f"{hx}，兩個判空段非空 = {ox}")


def report_b_class(all_rows: dict[tuple[str, int], dict], corpus: Corpus,
                   gmap: dict[str, str], r: Report) -> None:
    dom = Counter()
    mod = Counter()
    empty_by_group = Counter()
    total_by_group = Counter()
    empty_by_chapter = Counter()
    total_by_chapter = Counter()
    empties = 0
    for (ch, _pi), row in all_rows.items():
        doms = row.get("domains") or []
        dom.update(doms)
        mod.update(row.get("modes") or [])
        g = gmap.get(ch, "?")
        total_by_group[g] += 1
        total_by_chapter[ch] += 1
        if not doms:
            empties += 1
            empty_by_group[g] += 1
            empty_by_chapter[ch] += 1
    r.note("B", f"全書判空 {empties} 段 / {len(all_rows)}")
    for g in GROUP_IDS:
        if total_by_group[g]:
            hit = total_by_group[g] - empty_by_group[g]
            r.note("B", f"{g} 命中 {hit}/{total_by_group[g]} "
                        f"({hit / total_by_group[g]:.0%})，判空 {empty_by_group[g]}")
    # G4 兩章必須分開報（SPEC B 類明文要求，合併報等於把 20 段當成一個群）
    for ch in [c for c, g in gmap.items() if g == "G4"]:
        if total_by_chapter[ch]:
            hit = total_by_chapter[ch] - empty_by_chapter[ch]
            r.note("B", f"G4／{ch} 命中 {hit}/{total_by_chapter[ch]}，"
                        f"判空 {empty_by_chapter[ch]}")
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

    check_prose_rules(spec, all_rows, corpus, r)

    if args.all:
        if len(all_rows) != len(corpus.para):
            r.fail("A1", f"--all 共收 {len(all_rows)} 段，語料 {len(corpus.para)} 段")
        report_b_class(all_rows, corpus, gmap, r)

    return r.dump("accept " + ", ".join(p.name for p in paths))


if __name__ == "__main__":
    sys.exit(main())
