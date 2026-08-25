#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""晏子春秋 標註驗收器。

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

JUAN_ORDER = ["諫上", "外篇重而異者", "問上", "諫下",
              "雜上", "外篇不合經術者", "雜下", "問下"]

_ROMAN_RE = re.compile(
    r"(?<![A-Za-z])(XIII|XII|XI|IX|VIII|VII|VI|IV|III|II|X|V|I)(?![A-Za-z])")
_CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
       "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

# 每張錨點表的語意。key 是標題子字串 + 該標題下的第幾張表。
# 只描述「這張表是什麼意思」，段數與成員一律由 SPEC 現場解析。
SECTION_SEMANTICS = {
    ("必須判空的錨點", 0): {"empty": True},
    ("破除側", 0): {"require": [{"XI"}], "forbid_d": {"XII"}},
    ("破除側", 1): {},
    ("認證側", 0): {"require": [{"XII"}]},
    ("技術側", 0): {"nonempty": True, "forbid_d": {"XII"}},
    ("X 的兩側", 0): {},
    ("敘事套語不是判空理由", 0): {},
    ("G2 論說群", 0): {},
    ("G1 敘事群", 0): {},
}


class Report:
    def __init__(self) -> None:
        self.fails: list[str] = []
        self.notes: list[str] = []

    def fail(self, code: str, msg: str) -> None:
        self.fails.append(f"[{code}] {msg}")

    def note(self, code: str, msg: str) -> None:
        self.notes.append(f"[{code}] {msg}")

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

def chapter_number(name: str) -> int:
    m = re.search(r"第([一二三四五六七八九十]+)$", name)
    if not m:
        raise ValueError(f"章名沒有章序號: {name}")
    t = m.group(1)
    if t == "十":
        return 10
    if t.startswith("十"):
        return 10 + _CN[t[1]]
    if len(t) == 2 and t[1] == "十":
        return _CN[t[0]] * 10
    if len(t) == 3 and t[1] == "十":
        return _CN[t[0]] * 10 + _CN[t[2]]
    return _CN[t]


class Corpus:
    """delegation/yanzi-chunqiu/bNN.md 是段落文字與批次歸屬的唯一真相。"""

    def __init__(self, root: pathlib.Path) -> None:
        self.para: dict[tuple[str, int], tuple[str, str]] = {}
        self.chapters: list[tuple[str, str, int]] = []   # (batch, chapter, n_para)
        for f in sorted(root.glob("b*.md")):
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

        self.juan: dict[str, str] = {}
        j, prev = 0, 0
        for _b, ch, _n in self.chapters:
            k = chapter_number(ch)
            if k != prev + 1:
                j += 1 if prev else 0
                prev = 0
            if j >= len(JUAN_ORDER):
                raise SystemExit(f"卷切分溢出，章序在 {ch} 處重啟第 {j + 1} 次")
            self.juan[ch] = JUAN_ORDER[j]
            prev = k

        self.batch_size = Counter(v[0] for v in self.para.values())
        self.batch_chapters = defaultdict(list)
        for b, ch, _n in self.chapters:
            self.batch_chapters[b].append(ch)
        self.juan_chapters = Counter(self.juan[ch] for _b, ch, _n in self.chapters)
        self.juan_paras = Counter()
        for _b, ch, n in self.chapters:
            self.juan_paras[self.juan[ch]] += n
        self.all_text = "".join(v[1] for v in self.para.values()) + \
                        "".join(ch for _b, ch, _n in self.chapters)

    def quote_hits(self, quote: str) -> list[tuple[str, int]]:
        return [k for k, v in self.para.items() if quote in v[1]]


# --------------------------------------------------------------------------
# SPEC 解析
# --------------------------------------------------------------------------

def _strip_parens(cell: str) -> str:
    prev = None
    out = cell
    while prev != out:
        prev = out
        out = re.sub(r"（[^（）]*）", "", out)
    return out


def parse_requirement(cell: str):
    """把「必須含」欄解析成 (require_groups, forbid_domains, forbid_modes, skip)。

    require_groups 是 set 的 list，每個 set 代表「至少含其中一個」。
    """
    if "見灰區" in cell:
        return [], set(), set(), True
    body = _strip_parens(cell)
    body = body.replace("*", "").replace("`", "")
    require: list[set[str]] = []
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
        elif doms:
            if "＋" in clause or "+" in clause:
                for d in doms:
                    require.append({d})
            else:
                require.append(set(doms))
    return require, forbid_d, forbid_m, False


class Anchor:
    __slots__ = ("chapter", "para_index", "quote", "batch", "juan",
                 "require", "forbid_d", "forbid_m", "empty", "nonempty",
                 "section", "line_no")

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
        self.headings: list[tuple[int, str]] = []
        self.tables: dict[tuple[str, int], list[tuple[int, list[str]]]] = {}
        self.table_header: dict[tuple[str, int], list[str]] = {}
        self.heading_text: dict[str, str] = {}
        self._parse_tables()
        self.anchors: list[Anchor] = []
        self._build_anchors()

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
                self.headings.append((i, cur_heading))
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

    def _match_section(self, heading: str) -> str | None:
        for (frag, _idx) in SECTION_SEMANTICS:
            if frag in heading:
                return frag
        return None

    def _build_anchors(self) -> None:
        for (heading, idx), rows in self.tables.items():
            frag = self._match_section(heading)
            if frag is None:
                continue
            sem = SECTION_SEMANTICS.get((frag, idx))
            if sem is None:
                continue
            header = self.table_header[(heading, idx)]
            req_col = header.index("必須含") if "必須含" in header else None
            self.heading_text[frag] = heading
            for line_no, cells in rows:
                m = re.match(r"^`(.+?)`\[(\d+)\]$", cells[0])
                if not m:
                    continue
                q = re.match(r"^「(.+)」$", cells[1])
                quote = q.group(1) if q else None
                require = [set(g) for g in sem.get("require", [])]
                forbid_d = set(sem.get("forbid_d", set()))
                forbid_m = set(sem.get("forbid_m", set()))
                empty = bool(sem.get("empty"))
                nonempty = bool(sem.get("nonempty"))
                if req_col is not None and req_col < len(cells):
                    r2, fd2, fm2, skip = parse_requirement(cells[req_col])
                    if skip:
                        continue
                    require += r2
                    forbid_d |= fd2
                    forbid_m |= fm2
                self.anchors.append(Anchor(
                    chapter=m.group(1), para_index=int(m.group(2)),
                    quote=quote, batch=cells[2], juan=cells[3],
                    require=require, forbid_d=forbid_d, forbid_m=forbid_m,
                    empty=empty, nonempty=nonempty or bool(require),
                    section=frag, line_no=line_no))

    def section_anchors(self, frag: str) -> list[Anchor]:
        return [a for a in self.anchors if a.section == frag]

    # -- 條文數字 -----------------------------------------------------------
    def number(self, pattern: str):
        m = re.search(pattern, self.raw)
        return int(m.group(1)) if m else None

    def heading_count(self, frag: str):
        head = self.heading_text.get(frag)
        if head is None:
            return None
        m = re.search(r"（(\d+) 段", head)
        return int(m.group(1)) if m else None


# --------------------------------------------------------------------------
# --check-spec
# --------------------------------------------------------------------------

# 條文數字 → 該數字必須等於哪一組錨點的列數。
CLAUSE_COUNTS = [
    ("S8a", r"「必須判空」的 (\d+) 段", "必須判空的錨點", None),
    ("S8b", r"破除側 (\d+) 段全部含", "破除側", "primary"),
    ("S8c", r"認證側 (\d+) 段全部含", "認證側", None),
    ("S8d", r"技術側 (\d+) 段 `domains`", "技術側", None),
    ("S8e", r"G2 論說群指定的 (\d+) 段", "G2 論說群", None),
]

TOUCHSTONE_RE = re.compile(
    r"\*\*`(.+?)`\[(\d+)\] 含 XII；`(.+?)`\[(\d+)\] 含 XI 不含 XII。\*\*")

BASE_FACTS = [
    ("為", r"`為` (\d+) 次"),
    ("爲", r"`爲` \*\*(\d+)\*\* 次"),
    ("眾", r"`眾` (\d+) 次"),
    ("衆", r"`衆` \*\*(\d+)\*\* 次"),
    ("並", r"`並` (\d+) 次"),
    ("竝", r"`竝` \*\*(\d+)\*\* 次"),
    ("於", r"`於`（(\d+) 次）"),
    ("于", r"`于`（(\d+) 次）"),
    ("「", r"開 (\d+)／閉 \d+"),
    ("」", r"開 \d+／閉 (\d+)"),
    ("\U00021898", r"`𡢘`（U\+21898）出現 (\d+) 次"),
]


def check_spec(spec: Spec, corpus: Corpus) -> Report:
    r = Report()

    # S1 每個宣告的區段都要找得到；找不到代表 parser 咬空了（斷掉會更綠，不是報錯）
    for (frag, idx) in SECTION_SEMANTICS:
        matched = [h for (h, i) in spec.tables if frag in h and i == idx]
        if not matched:
            r.fail("S1", f"找不到區段表格「{frag}」第 {idx} 張——SPEC 標題或表頭被改過，"
                          f"這一族斷言已經停跑")
    if not spec.anchors:
        r.fail("S1", "一條錨點都沒解析到")

    # S2 標題宣告的段數 == 實際列數
    for frag in ["必須判空的錨點", "破除側", "認證側", "技術側", "G2 論說群", "G1 敘事群"]:
        declared = spec.heading_count(frag)
        if declared is None:
            r.fail("S2", f"「{frag}」標題裡讀不到宣告段數")
            continue
        rows = spec.tables.get((spec.heading_text.get(frag), 0), [])
        if declared != len(rows):
            r.fail("S2", f"「{frag}」標題宣告 {declared} 段，表格實際 {len(rows)} 列")

    # X 的兩側：標題宣告命中 N／判空 M，要對上 require/forbid 的列數
    xhead = spec.heading_text.get("X 的兩側")
    if xhead is None:
        r.fail("S2", "找不到「X 的兩側」標題")
    else:
        m = re.search(r"命中 (\d+) 段.*判空側 (\d+) 段", xhead)
        if not m:
            r.fail("S2", "「X 的兩側」標題讀不到命中／判空段數")
        else:
            xs = spec.section_anchors("X 的兩側")
            hit = [a for a in xs if any("X" in g for g in a.require)]
            null = [a for a in xs if "X" in a.forbid_d]
            if len(hit) != int(m.group(1)):
                r.fail("S2", f"X 命中側宣告 {m.group(1)} 段，表格實際 {len(hit)} 列")
            if len(null) != int(m.group(2)):
                r.fail("S2", f"X 判空側宣告 {m.group(2)} 段，表格實際 {len(null)} 列")

    # S3 每條錨點回語料對拍
    for a in spec.anchors:
        key = a.key()
        if key not in corpus.para:
            r.fail("S3", f"{a.label()} 在語料裡不存在")
            continue
        batch, text = corpus.para[key]
        if a.batch != batch:
            r.fail("S3", f"{a.label()} SPEC 寫 {a.batch}，實際在 {batch}")
        if a.juan != corpus.juan[a.chapter]:
            r.fail("S3", f"{a.label()} SPEC 寫卷「{a.juan}」，實際「{corpus.juan[a.chapter]}」")
        if not a.quote:
            r.fail("S3", f"{a.label()} 讀不到逐字引句")
        elif a.quote not in text:
            r.fail("S3", f"{a.label()} 引句對不上原文：{a.quote[:20]}")
        elif len(corpus.quote_hits(a.quote)) != 1:
            r.fail("S3", f"{a.label()} 引句在全書出現 "
                         f"{len(corpus.quote_hits(a.quote))} 次，不唯一：{a.quote[:20]}")

    # S4 錨點段落不得重複登場（重複要嘛是漏改，要嘛得明文宣告）
    dup = [k for k, c in Counter(a.key() for a in spec.anchors).items() if c > 1]
    for k in dup:
        r.fail("S4", f"{k[0]}[{k[1]}] 出現在多張錨點表")

    # S5 批次表
    declared_batches = {}
    m = re.search(r"b01 (\d+)／b02 (\d+)／b03 (\d+)／b04 (\d+)／"
                  r"b05 (\d+)／b06 (\d+)／b07 (\d+)，合計 (\d+)", spec.raw)
    if not m:
        r.fail("S5", "A 類第 1 條讀不到批次段數宣告——條文被改寫，這一族斷言已停跑")
    else:
        for i in range(7):
            declared_batches[f"b0{i + 1}"] = int(m.group(i + 1))
        total = int(m.group(8))
        for b, n in declared_batches.items():
            if corpus.batch_size[b] != n:
                r.fail("S5", f"{b} 宣告 {n} 段，實際 {corpus.batch_size[b]} 段")
        if total != sum(corpus.batch_size.values()):
            r.fail("S5", f"合計宣告 {total}，實際 {sum(corpus.batch_size.values())}")

    for line in spec.lines:
        m = re.match(r"^\| (b0\d) \| (\d+) \| (\d+) \| ", line)
        if m:
            b, np_, nc = m.group(1), int(m.group(2)), int(m.group(3))
            if corpus.batch_size[b] != np_:
                r.fail("S5", f"批次表 {b} 段數 {np_}，實際 {corpus.batch_size[b]}")
            if len(corpus.batch_chapters[b]) != nc:
                r.fail("S5", f"批次表 {b} 章數 {nc}，實際 {len(corpus.batch_chapters[b])}")

    # S6 卷結構表
    seen_juan = set()
    for line in spec.lines:
        m = re.match(r"^\| (\d) \| (\S+?) \| (G[12]) \| (\d+) \| (\d+) \| ", line)
        if not m:
            continue
        idx, juan, grp, nc, np_ = (int(m.group(1)), m.group(2), m.group(3),
                                   int(m.group(4)), int(m.group(5)))
        seen_juan.add(juan)
        if juan not in JUAN_ORDER:
            r.fail("S6", f"卷結構表出現未知卷名 {juan}")
            continue
        if JUAN_ORDER[idx - 1] != juan:
            r.fail("S6", f"卷結構表第 {idx} 列是 {juan}，語料實際順序是 {JUAN_ORDER[idx - 1]}")
        if corpus.juan_chapters[juan] != nc:
            r.fail("S6", f"卷 {juan} 宣告 {nc} 章，實際 {corpus.juan_chapters[juan]} 章")
        if corpus.juan_paras[juan] != np_:
            r.fail("S6", f"卷 {juan} 宣告 {np_} 段，實際 {corpus.juan_paras[juan]} 段")
    missing_juan = set(JUAN_ORDER) - seen_juan
    if missing_juan:
        r.fail("S6", f"卷結構表漏列：{sorted(missing_juan)}")

    # S7 兩章多段表
    multi = {ch: n for _b, ch, n in corpus.chapters if n > 1}
    declared_multi = {}
    for line in spec.lines:
        m = re.match(r"^\| `(.+?)` \| (\d+) \| (b0\d) \|$", line)
        if m:
            declared_multi[m.group(1)] = (int(m.group(2)), m.group(3))
    if set(declared_multi) != set(multi):
        r.fail("S7", f"多段章宣告 {sorted(declared_multi)}，實際 {sorted(multi)}")
    for ch, (n, b) in declared_multi.items():
        if ch in multi and multi[ch] != n:
            r.fail("S7", f"{ch} 宣告 {n} 段，實際 {multi[ch]} 段")
        if ch in corpus.juan and corpus.para.get((ch, 1), ("?",))[0] != b:
            r.fail("S7", f"{ch} 宣告在 {b}，實際 {corpus.para[(ch, 1)][0]}")
    m = re.search(r"其餘 (\d+) 章各 1 段", spec.raw)
    if m is None:
        r.fail("S7", "讀不到「其餘 N 章各 1 段」宣告")
    elif int(m.group(1)) != len(corpus.chapters) - len(multi):
        r.fail("S7", f"其餘章數宣告 {m.group(1)}，實際 {len(corpus.chapters) - len(multi)}")

    # S8 A 類條文數字 == 錨點表列數
    for code, pat, frag, mode in CLAUSE_COUNTS:
        n = spec.number(pat)
        if n is None:
            r.fail(code, f"A 類條文讀不到數字（pattern={pat}）——條文被改寫，斷言已停跑")
            continue
        head = spec.heading_text.get(frag)
        rows = len(spec.tables.get((head, 0), [])) if head else 0
        if n != rows:
            r.fail(code, f"條文寫 {frag} {n} 段，錨點表 {rows} 列")

    n = spec.number(r"X 命中側 (\d+) 段全部含 X")
    xs = spec.section_anchors("X 的兩側")
    hit = len([a for a in xs if any("X" in g for g in a.require)])
    null = len([a for a in xs if "X" in a.forbid_d])
    if n is None:
        r.fail("S8f", "A 類讀不到 X 命中側段數")
    elif n != hit:
        r.fail("S8f", f"條文寫 X 命中側 {n} 段，表格 {hit} 列")
    n = spec.number(r"X 判空側 (\d+) 段")
    if n is None:
        r.fail("S8g", "A 類讀不到 X 判空側段數")
    elif n != null:
        r.fail("S8g", f"條文寫 X 判空側 {n} 段，表格 {null} 列")

    # G1 硬條件段數 = 表列數 - 灰區排除數
    n = spec.number(r"G1 敘事群指定的 (\d+) 段")
    g1_rows = spec.tables.get((spec.heading_text.get("G1 敘事群"), 0), [])
    g1_hard = len(spec.section_anchors("G1 敘事群"))
    if n is None:
        r.fail("S8h", "A 類讀不到 G1 硬條件段數")
    elif n != g1_hard:
        r.fail("S8h", f"條文寫 G1 {n} 段，扣掉灰區後表格實得 {g1_hard} 列")
    if len(g1_rows) - g1_hard != 1:
        r.fail("S8h", f"G1 表 {len(g1_rows)} 列裡有 {len(g1_rows) - g1_hard} 列被灰區排除，"
                      f"SPEC 只交代了 1 列（景公成柏寢）")

    # S9 底本事實
    for ch, pat in BASE_FACTS:
        n = spec.number(pat)
        actual = corpus.all_text.count(ch)
        if n is None:
            r.fail("S9", f"讀不到底本事實宣告（{ch}，pattern={pat}）")
        elif n != actual:
            r.fail("S9", f"底本事實 {ch} 宣告 {n} 次，實際 {actual} 次")

    names = [ch for _b, ch, _n in corpus.chapters]
    for label, sym, pat in [("逗號", "，", r"\*\*(\d+) 個含全形逗號\*\*"),
                            ("冒號", "：", r"\*\*(\d+) 個含全形冒號\*\*"),
                            ("頓號", "、", r"\*\*(\d+) 個含頓號\*\*")]:
        n = spec.number(pat)
        actual = len([c for c in names if sym in c])
        if n is None:
            r.fail("S9", f"讀不到章名{label}數宣告")
        elif n != actual:
            r.fail("S9", f"章名含{label}宣告 {n} 個，實際 {actual} 個")
    n = spec.number(r"(\d+) 個章名中")
    if n is None:
        r.fail("S9", "讀不到章名總數宣告")
    elif n != len(names):
        r.fail("S9", f"章名總數宣告 {n}，實際 {len(names)}")

    brackets = sum(corpus.all_text.count(c) for c in "〈〉〔〕【】")
    if brackets:
        r.fail("S9", f"SPEC 宣告全書沒有夾注符號，實際出現 {brackets} 個")

    # S10 領域表與 mode 表
    spec_domains = re.findall(r"^\| (XIII|XII|XI|IX|VIII|VII|VI|IV|III|II|X|V|I) \| ",
                              spec.raw, re.M)
    if sorted(spec_domains, key=DOMAIN_IDS.index) != DOMAIN_IDS or \
            len(spec_domains) != len(DOMAIN_IDS):
        r.fail("S10", f"領域表列出 {len(spec_domains)} 個 id，與 13 個標準 id 不符：{spec_domains}")
    spec_modes = re.findall(r"^\| `([a-z_]+)` \| ", spec.raw, re.M)
    if sorted(spec_modes) != sorted(MODE_IDS):
        r.fail("S10", f"mode 表列出 {spec_modes}，與 8 個標準 id 不符")

    # S11 灰區段落必須存在於語料
    # 只驗「至少解析到一條」會讓格式漂掉的那幾條靜靜消失（墨子事故的形態）：
    # 改成灰區那一節底下每一個 bullet 都必須解析得出來。
    sect = re.search(r"^## 我不設錨的灰區.*?(?=^## )", spec.raw, re.M | re.S)
    if sect is None:
        r.fail("S11", "找不到灰區區段——條文被改寫，斷言已停跑")
        gray = []
    else:
        bullets = re.findall(r"^- .*$", sect.group(0), re.M)
        gray = re.findall(r"^- `(.+?)`\[(\d+)\]（b0\d）", sect.group(0), re.M)
        if len(gray) != len(bullets):
            r.fail("S11", f"灰區有 {len(bullets)} 個 bullet，只解析出 {len(gray)} 條——"
                          f"格式漂掉的那幾條已停跑")
    for ch, pi in gray:
        if (ch, int(pi)) not in corpus.para:
            r.fail("S11", f"灰區 {ch}[{pi}] 在語料裡不存在")

    # S12 reason 長度係數
    n = spec.number(r"不得少於 N × (\d+) 字元")
    if n is None:
        r.fail("S12", "A 類讀不到 reason 長度係數")

    # S13 試金石條文可解析，且兩段都在語料裡（A6 靠這條規則活著）
    m = TOUCHSTONE_RE.search(spec.raw)
    if m is None:
        r.fail("S13", "A 類第 6 條試金石讀不出兩段——A6 已停跑")
    else:
        for ch, pi in [(m.group(1), int(m.group(2))), (m.group(3), int(m.group(4)))]:
            if (ch, int(pi)) not in corpus.para:
                r.fail("S13", f"試金石 {ch}[{pi}] 在語料裡不存在")

    return r


# --------------------------------------------------------------------------
# 批次輸出驗收（A 類）
# --------------------------------------------------------------------------

def check_output(spec: Spec, corpus: Corpus, paths: list[pathlib.Path],
                 whole_book: bool) -> Report:
    r = Report()
    rows: dict[tuple[str, int], dict] = {}
    seen_batches = []

    for p in paths:
        try:
            obj = json.loads(p.read_bytes().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            r.fail("A1", f"{p.name} 不是合法 JSON：{e}")
            continue
        batch = re.sub(r"\.md$", "", str(obj.get("batch", p.stem)))
        seen_batches.append(batch)
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
            ch = row.get("chapter")
            pi = row.get("para_index")
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
            reason = row.get("reason") or ""
            if not str(reason).strip():
                r.fail("A1", f"{ch}[{pi}] 沒有 reason")

        # 每章 para_index 從 1 連號無缺
        by_ch = defaultdict(set)
        for row in rs:
            if isinstance(row.get("para_index"), int):
                by_ch[row.get("chapter")].add(row["para_index"])
        for _b, ch, n in corpus.chapters:
            if _b != batch:
                continue
            if by_ch.get(ch) != set(range(1, n + 1)):
                r.fail("A1", f"{ch} 的 para_index 應為 1..{n}，實得 {sorted(by_ch.get(ch, []))}")

    def dom(key):
        v = rows.get(key, {}).get("domains")
        return v if isinstance(v, list) else None

    def mod(key):
        v = rows.get(key, {}).get("modes")
        return v if isinstance(v, list) else None

    # A13 詞彙合法
    for key, row in rows.items():
        for d in row.get("domains") or []:
            if d not in DOMAIN_IDS:
                r.fail("A13", f"{key[0]}[{key[1]}] domains 出現非法值 {d!r}")
        for m in row.get("modes") or []:
            if m not in MODE_IDS:
                r.fail("A13", f"{key[0]}[{key[1]}] modes 出現非法值 {m!r}")

    # A2–A12 錨點
    for a in spec.anchors:
        key = a.key()
        if key not in rows:
            continue  # 該批未回收
        ds = dom(key)
        ms = mod(key)
        if ds is None:
            r.fail("A1", f"{a.label()} 沒有 domains 陣列")
            continue
        code = {"必須判空的錨點": "A2", "破除側": "A3", "認證側": "A5",
                "技術側": "A7", "X 的兩側": "A8", "敘事套語不是判空理由": "A10",
                "G2 論說群": "A11", "G1 敘事群": "A12"}.get(a.section, "A4")
        if a.empty and ds:
            r.fail(code, f"{a.label()} 必須判空，實得 {ds}")
        if a.nonempty and not ds:
            r.fail(code, f"{a.label()} 必須非空，實得 []")
        for g in a.require:
            if not (set(ds) & g):
                r.fail(code, f"{a.label()} 必須含 {'或'.join(sorted(g))}，實得 {ds}")
        bad = set(ds) & a.forbid_d
        if bad:
            r.fail(code, f"{a.label()} 不得含 {sorted(bad)}，實得 {ds}")
        if ms is not None:
            badm = set(ms) & a.forbid_m
            if badm:
                r.fail(code, f"{a.label()} modes 不得含 {sorted(badm)}，實得 {ms}")

    # A6 試金石：認證側與破除側不得判齊
    m = TOUCHSTONE_RE.search(spec.raw)
    if m is None:
        r.fail("A6", "讀不到試金石條文——A 類第 6 條已停跑")
    else:
        k1 = (m.group(1), int(m.group(2)))
        k2 = (m.group(3), int(m.group(4)))
        if k1 in rows and k2 in rows:
            d1, d2 = set(dom(k1) or []), set(dom(k2) or [])
            if ("XII" in d1) == ("XII" in d2):
                r.fail("A6", f"試金石判齊：{k1[0]} XII={'XII' in d1}，"
                             f"{k2[0]} XII={'XII' in d2}")

    # A14 worked_instance 全書 0 段
    wi = [f"{k[0]}[{k[1]}]" for k, row in rows.items()
          if "worked_instance" in (row.get("modes") or [])]
    if wi:
        r.fail("A14", f"worked_instance 應為 0 段，實得 {len(wi)}：{wi[:5]}")

    # A15 reason 長度 >= N × 係數
    coef = spec.number(r"不得少於 N × (\d+) 字元")
    if coef is None:
        r.fail("A15", "讀不到 reason 長度係數——A 類第 15 條已停跑")
    else:
        for key, row in rows.items():
            n = len(row.get("domains") or [])
            if n and len(str(row.get("reason") or "")) < n * coef:
                r.fail("A15", f"{key[0]}[{key[1]}] 標了 {n} 格，reason 只有 "
                              f"{len(str(row.get('reason') or ''))} 字元（需 ≥ {n * coef}）")

    # A16 章名歸卷
    if whole_book:
        got_ch = Counter(corpus.juan[c] for c in {k[0] for k in rows}
                         if c in corpus.juan)
        got_pa = Counter(corpus.juan[k[0]] for k in rows if k[0] in corpus.juan)
        for j in JUAN_ORDER:
            if got_ch[j] != corpus.juan_chapters[j]:
                r.fail("A16", f"卷 {j} 回收 {got_ch[j]} 章，應為 {corpus.juan_chapters[j]} 章")
            if got_pa[j] != corpus.juan_paras[j]:
                r.fail("A16", f"卷 {j} 回收 {got_pa[j]} 段，應為 {corpus.juan_paras[j]} 段")
        missing = set(corpus.para) - set(rows)
        if missing:
            r.fail("A1", f"全書漏了 {len(missing)} 段，例：{sorted(missing)[:3]}")

    return r, rows


def report_b_class(corpus: Corpus, rows: dict) -> None:
    if not rows:
        return
    print("\n=== B 類實測（不擋收） ===")
    dc = Counter(d for row in rows.values() for d in (row.get("domains") or []))
    mc = Counter(m for row in rows.values() for m in (row.get("modes") or []))
    empty = [k for k, row in rows.items() if not (row.get("domains") or [])]
    g1 = [k for k in rows if corpus.juan.get(k[0]) not in ("問上", "問下")]
    g2 = [k for k in rows if corpus.juan.get(k[0]) in ("問上", "問下")]
    def rate(ks):
        if not ks:
            return "n/a"
        hit = len([k for k in ks if rows[k].get("domains")])
        return f"{hit}/{len(ks)} = {hit / len(ks):.0%}"
    print(f"G1 敘事群命中 {rate(g1)}；G2 論說群命中 {rate(g2)}")
    print(f"判空 {len(empty)} 段")
    print("領域：" + "  ".join(f"{d}={dc[d]}" for d in DOMAIN_IDS))
    print("mode：" + "  ".join(f"{m}={mc[m]}" for m in MODE_IDS))
    print(f"零段領域：{[d for d in DOMAIN_IDS if not dc[d]]}")
    print("跨批盲測：本書不設（跨批最高相似度 0.392 < 0.45 門檻）")


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
        # 印出解析涵蓋量：斷言族斷掉的表現是「更綠」而不是報錯，
        # 這幾行是唯一看得出 parser 有沒有咬空的地方。
        print("\n--- 解析涵蓋 ---")
        print(f"語料 {len(corpus.chapters)} 章 / {len(corpus.para)} 段 / "
              f"{len(corpus.batch_size)} 批 / {len(JUAN_ORDER)} 卷")
        print(f"錨點共 {len(spec.anchors)} 條，分佈：")
        for frag in dict.fromkeys(f for (f, _i) in SECTION_SEMANTICS):
            ax = spec.section_anchors(frag)
            req = sum(len(a.require) for a in ax)
            fb = sum(len(a.forbid_d) + len(a.forbid_m) for a in ax)
            print(f"  {frag:<16} {len(ax):>2} 條  require群 {req:>2}  forbid {fb:>2}")
        print(f"灰區 {len(re.findall(r'^- `(.+?)`\[(\d+)\]（b0\d）', spec.raw, re.M))} 段")
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
    report_b_class(corpus, rows)
    return 0 if rep.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
