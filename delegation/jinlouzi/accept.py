#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金樓子 標註驗收器。

錨點與數字一律由本檔現場解析 SPEC.md，不在程式裡手抄任何章名、段號、引句或計數。
（孔叢子踩過：手抄錨點造成 18 個假 FAIL。）

用法:
    python accept.py --check-spec           # 只驗規格本身（發包前必跑到 0 FAIL / 0 NOTE）
    python accept.py out/b01.json [...]     # 驗回收的批次輸出
    python accept.py --all                  # 驗 out/ 底下全部批次（含跨批條件）
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = pathlib.Path(__file__).resolve().parent
SPEC_PATH = HERE / "SPEC.md"
OUT_DIR = HERE / "out"

DOMAIN_IDS = ["I", "II", "III", "IV", "V", "VI", "VII",
              "VIII", "IX", "X", "XI", "XII", "XIII"]
MODE_IDS = ["narrative", "observation", "proposition", "prescription",
            "expression", "ritual", "formalization", "worked_instance"]
BANNED_DOMAINS = ["Z-wisdom", "X-modern", "Y-nature"]

ROMAN_RE = re.compile(r"(?<![A-Za-z])(XIII|XII|XI|IX|VIII|VII|VI|IV|III|II|X|V|I)(?![A-Za-z])")
QUOTE_WINDOW = 8          # reason 至少要有這麼長的一段逐字落在該段正文裡


# --------------------------------------------------------------------------

class Report:
    def __init__(self) -> None:
        self.fails: list[str] = []
        self.notes: list[str] = []

    def fail(self, code: str, msg: str) -> None:
        self.fails.append(f"[{code}] {msg}")

    def note(self, code: str, msg: str) -> None:
        self.notes.append(f"[{code}] {msg}")

    def codes(self) -> set[str]:
        return {f[1:f.index("]")] for f in self.fails}

    def note_codes(self) -> set[str]:
        return {n[1:n.index("]")] for n in self.notes}

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
# 語料：bNN.md 是段落文字、章名與批次歸屬的唯一真相
# --------------------------------------------------------------------------

class Corpus:
    def __init__(self, root: pathlib.Path) -> None:
        self.para: dict[tuple[str, int], tuple[str, str]] = {}
        self.chapters: list[tuple[str, str, int]] = []   # (batch, chapter, 宣告段數)
        for f in sorted(root.glob("b[0-9][0-9].md")):
            text = f.read_bytes().decode("utf-8")
            cur = None
            buf_key = None
            for line in text.split("\n"):
                m = re.match(r"^## (.+?)（(\d+) 段）$", line)
                if m:
                    cur = m.group(1)
                    self.chapters.append((f.stem, cur, int(m.group(2))))
                    buf_key = None
                    continue
                m2 = re.match(r"^\[(\d+)\] ?(.*)$", line)
                if m2 and cur:
                    buf_key = (cur, int(m2.group(1)))
                    self.para[buf_key] = (f.stem, m2.group(2))
                    continue
                if buf_key and line.strip():
                    b, t = self.para[buf_key]
                    self.para[buf_key] = (b, t + line)
        if not self.para:
            raise SystemExit("讀不到 bNN.md，語料為空")

        self.chapter_batches: dict[str, list[str]] = defaultdict(list)
        for b, ch, _n in self.chapters:
            self.chapter_batches[ch].append(b)
        self.batch_chapters: dict[str, list[str]] = defaultdict(list)
        for b, ch, _n in self.chapters:
            self.batch_chapters[b].append(ch)
        self.batch_size = Counter(v[0] for v in self.para.values())
        self.chapter_size = Counter(k[0] for k in self.para)
        self.chapter_names = [ch for _b, ch, _n in self.chapters]
        # 同一章可能跨批（興王篇一 b01-b03），去重但保順序
        seen: set[str] = set()
        self.chapter_order = [c for c in self.chapter_names
                              if not (c in seen or seen.add(c))]

    def text(self, key: tuple[str, int]) -> str | None:
        v = self.para.get(key)
        return v[1] if v else None

    def batch_of(self, key: tuple[str, int]) -> str | None:
        v = self.para.get(key)
        return v[0] if v else None

    def quote_hits(self, quote: str) -> list[tuple[str, int]]:
        return [k for k, v in self.para.items() if quote in v[1]]


# --------------------------------------------------------------------------
# SPEC 解析
# --------------------------------------------------------------------------

class Anchor:
    __slots__ = ("chapter", "para_index", "quote", "batch", "group",
                 "kind", "domain", "line_no")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    @property
    def key(self):
        return (self.chapter, self.para_index)

    def label(self) -> str:
        return f"{short(self.chapter)}[{self.para_index}]"


def short(chapter: str) -> str:
    """長章名（含四庫案語）的短稱：截到第一個 `〈`。"""
    return chapter.split("〈")[0]


class Spec:
    ROW_RE = re.compile(r"^\|\s*`([^`]+)`\[(\d+)\]\s*\|\s*`([^`]+)`\s*\|\s*"
                        r"(b\d\d)\s*\|\s*(G\d)\s*\|(.*)$")

    def __init__(self, path: pathlib.Path, corpus_chapters: list[str]) -> None:
        self.raw = path.read_bytes().decode("utf-8")
        self.lines = self.raw.split("\n")
        self.corpus_chapters = corpus_chapters
        self.null = self._table("## 必須判空的錨點", "<!-- ANCHOR-NULL-END -->",
                                "null", has_domain_col=False)
        self.hit = self._table("## 必須命中的錨點", "<!-- ANCHOR-HIT-END -->",
                               "hit", has_domain_col=True)
        self.forbid = self._table("## 禁格錨點", "<!-- ANCHOR-FORBID-END -->",
                                  "forbid", has_domain_col=True)
        self.batch_table = self._parse_batch_table()
        self.dispatch = self._parse_dispatch()
        self.declared = self._parse_declared_numbers()
        self.domain_ids = self._parse_id_table("## 13 個領域")
        self.mode_ids = self._parse_id_table("## 8 個 discourse_mode")
        self.prose_musthave = self._parse_prose_musthave()
        self.prose_forbid = self._parse_prose_forbid()
        self.prose_batch_counts = self._parse_prose_batch_counts()
        self.gray_bullets, self.gray_ref_bullets, self.gray_refs = self._parse_gray()

    # -- 錨點表 -------------------------------------------------------------
    def _segment(self, start: str, end: str) -> tuple[list[str], int]:
        i = next(k for k, l in enumerate(self.lines) if l.startswith(start))
        j = next(k for k, l in enumerate(self.lines) if l.strip() == end)
        assert i < j, f"{start} 與 {end} 順序顛倒"
        return self.lines[i:j], i

    def _table(self, start: str, end: str, kind: str,
               has_domain_col: bool) -> list[Anchor]:
        chunk, base = self._segment(start, end)
        out: list[Anchor] = []
        for off, line in enumerate(chunk):
            m = self.ROW_RE.match(line)
            if not m:
                continue
            rest = [c.strip() for c in m.group(6).split("|")]
            dom = None
            if has_domain_col and rest:
                cell = rest[0]
                if cell not in ("—", "-", ""):
                    found = ROMAN_RE.findall(cell)
                    dom = found[0] if len(found) == 1 else (found or None)
            out.append(Anchor(chapter=self._full(m.group(1)),
                              para_index=int(m.group(2)),
                              quote=m.group(3), batch=m.group(4),
                              group=m.group(5), kind=kind, domain=dom,
                              line_no=base + off + 1))
        return out

    def _full(self, name: str) -> str:
        """錨點表寫短章名，語料是含四庫案語的完整章名。"""
        cand = [c for c in self.corpus_chapters if c.startswith(name + "〈")]
        return cand[0] if len(cand) == 1 else name

    # -- 批次表 -------------------------------------------------------------
    def _parse_batch_table(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for line in self.lines:
            m = re.match(r"^\|\s*(b\d\d)\s*\|\s*(\d+)\s*\|\s*\d+\s*\|", line)
            if m:
                out[m.group(1)] = int(m.group(2))
        return out

    # -- 分派表 -------------------------------------------------------------
    def _parse_dispatch(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for line in self.lines:
            m = re.match(r"^\|\s*(G\d)[^|]*\|([^|]*)\|([^|]*)\|\s*(\d+)／(\d+)\s*\|", line)
            if not m:
                continue
            chapters = [c for c in re.split(r"\s+", m.group(2).strip()) if c]
            chapters = [short(c) for c in chapters]
            batches = re.findall(r"b\d\d", m.group(3))
            rng = re.findall(r"b(\d\d)–b(\d\d)", m.group(3))
            for a, b in rng:
                batches += [f"b{n:02d}" for n in range(int(a), int(b) + 1)]
            out[m.group(1)] = {"chapters": chapters,
                               "batches": sorted(set(batches)),
                               "n_ch": int(m.group(4)), "n_pa": int(m.group(5))}
        return out

    def chapter_group(self, corpus: Corpus) -> dict[str, str]:
        out: dict[str, str] = {}
        for ch in corpus.chapter_order:
            hits = [g for g, d in self.dispatch.items()
                    if any(ch == c or ch.startswith(c + "〈") for c in d["chapters"])]
            if len(hits) == 1:
                out[ch] = hits[0]
        return out

    # -- 條文數字 -----------------------------------------------------------
    def _parse_declared_numbers(self) -> dict[str, int]:
        out: dict[str, int] = {}
        pats = {
            "null": r"「必須判空」表列的 (\d+) 段",
            "hit": r"「必須命中」表列的 (\d+) 段",
            "musthave": r"必含格 (\d+) 條全部滿足",
            "forbid": r"禁格錨點 (\d+) 列全部成立",
            "total": r"\*\*合計 (\d+)\*\*",
            "g5_reg": r"`著書篇十`\[1\]–\[37\]，共 (\d+) 段",
            "g5_self": r"`書後` 3，共 (\d+) 段",
            "gray": r"本節共 (\d+) 條",
            "gray_ref": r"其中 (\d+) 條指名段落",
            "gray_para": r"合計 (\d+) 個相異段",
        }
        for k, p in pats.items():
            m = re.search(p, self.raw)
            if m:
                out[k] = int(m.group(1))
        return out

    def _parse_id_table(self, heading: str) -> list[str]:
        i = next((k for k, l in enumerate(self.lines) if l.startswith(heading)), None)
        if i is None:
            return []
        out: list[str] = []
        for line in self.lines[i:]:
            if line.startswith("## ") and not line.startswith(heading):
                break
            m = re.match(r"^\|\s*`?([A-Za-z_]+|[IVX]+)`?\s*\|", line)
            if m and m.group(1) not in ("id",):
                out.append(m.group(1))
        return out

    # -- A 類散文條件（與表格對拍用，不當第二真相源） ------------------------
    def _prose_line(self, marker: str) -> str:
        for line in self.lines:
            if marker in line:
                return line
        return ""

    def _parse_prose_musthave(self) -> set[tuple[str, int, str]]:
        out: set[tuple[str, int, str]] = set()
        for dom in DOMAIN_IDS:
            line = self._prose_line(f"**含 {dom}（")
            if not line:
                continue
            body = line.split("**：", 1)[-1]
            cur = None
            for m in re.finditer(r"`([^`]+)`|\[(\d+)\]", body):
                if m.group(1):
                    cur = m.group(1)
                elif cur:
                    out.add((cur, int(m.group(2)), dom))
        return out

    def _parse_prose_forbid(self) -> set[tuple[str, int, str]]:
        line = self._prose_line("列全部成立**：")
        out: set[tuple[str, int, str]] = set()
        cur = None
        for m in re.finditer(r"`([^`]+)`\[(\d+)\]|不得含 ([IVX]+)", line):
            if m.group(1):
                cur = (m.group(1), int(m.group(2)))
            elif cur:
                out.add((cur[0], cur[1], m.group(3)))
        return out

    def _parse_prose_batch_counts(self) -> dict[str, int]:
        line = self._prose_line("**`rows` 數等於該批段數**")
        return {m.group(1): int(m.group(2))
                for m in re.finditer(r"(b\d\d) (\d+)", line)}

    def _parse_gray(self) -> tuple[int, int, list[tuple[str, int, int]]]:
        """灰區 bullet 數、指名段落的 bullet 數，以及指名的段落（章, 段, 行號）。"""
        chunk, base = self._segment("## 我不設錨的灰區", "<!-- GRAY-END -->")
        n = n_ref = 0
        refs: list[tuple[str, int, int]] = []
        for off, line in enumerate(chunk):
            if not line.startswith("- "):
                continue
            n += 1
            cur = None
            hit = False
            for m in re.finditer(r"`([^`]+)`(?=\[)|\[(\d+)\]", line):
                if m.group(1):
                    # 只認語料裡真有的章名；認不出就不當章名，沿用前一個。
                    # 漏認會讓下面三個宣告數字對不上，不會靜默。
                    full = self._full(m.group(1))
                    cur = full if full in self.corpus_chapters else cur
                elif cur:
                    hit = True
                    refs.append((cur, int(m.group(2)), base + off + 1))
            n_ref += hit
        return n, n_ref, refs

    # -- G5 兩側（供 A9／A10 用，現場從 SPEC 的小節標題解析） ----------------
    def g5_sides(self) -> dict[str, list[tuple[str, int]]]:
        m = re.search(r"登錄側書目流水帳（`聚書篇六` (\d+) 段＋`著書篇十`\[(\d+)\]–\[(\d+)\]",
                      self.raw)
        if not m:
            return {}
        n_ju, lo, hi = int(m.group(1)), int(m.group(2)), int(m.group(3))
        m2 = re.search(r"自述側（`自序篇十四` (\d+)＋`序` (\d+)＋`書後` (\d+)", self.raw)
        if not m2:
            return {}
        reg = [("聚書篇六", i) for i in range(1, n_ju + 1)]
        reg += [("著書篇十", i) for i in range(lo, hi + 1)]
        slf = [("自序篇十四", i) for i in range(1, int(m2.group(1)) + 1)]
        slf += [("序", i) for i in range(1, int(m2.group(2)) + 1)]
        slf += [("書後", i) for i in range(1, int(m2.group(3)) + 1)]
        return {"registry": reg, "self": slf}


# --------------------------------------------------------------------------
# 規格自檢
# --------------------------------------------------------------------------

def check_spec(spec: Spec, corpus: Corpus) -> Report:
    r = Report()
    anchors = spec.null + spec.hit + spec.forbid

    # S1/S2 錨點落點與引句
    for a in anchors:
        txt = corpus.text(a.key)
        if txt is None:
            r.fail("S1", f"{a.label()} 不在語料裡（SPEC:{a.line_no}）")
            continue
        if a.quote not in txt:
            r.fail("S2", f"{a.label()} 引句不在該段（SPEC:{a.line_no}）：{a.quote[:24]}")
        b = corpus.batch_of(a.key)
        if b != a.batch:
            r.fail("S3", f"{a.label()} 批號標 {a.batch} 實際在 {b}（SPEC:{a.line_no}）")

    # S4 引句全書唯一（不唯一＝定位不住，回批次檔對拍會誤中別段）
    for a in anchors:
        hits = corpus.quote_hits(a.quote)
        if len(hits) > 1:
            other = [f"{short(c)}[{i}]" for c, i in hits if (c, i) != a.key]
            r.fail("S4", f"{a.label()} 引句同時命中 {other}（SPEC:{a.line_no}）")

    # S5 三表互斥關係
    ns = {a.key for a in spec.null}
    hs = {a.key for a in spec.hit}
    fs = {a.key for a in spec.forbid}
    for k in sorted(ns & hs):
        r.fail("S5", f"{short(k[0])}[{k[1]}] 同時列在判空表與命中表")
    for k in sorted(ns & fs):
        r.fail("S5", f"{short(k[0])}[{k[1]}] 同時列在判空表與禁格表")
    for k in sorted(fs - hs):
        r.fail("S5", f"{short(k[0])}[{k[1]}] 在禁格表但不在命中表")

    # S6 禁格與必含不得互相抵銷
    must = {(a.key, a.domain) for a in spec.hit if isinstance(a.domain, str)}
    for a in spec.forbid:
        if (a.key, a.domain) in must:
            r.fail("S6", f"{a.label()} 的 {a.domain} 同時被列為必含與禁填")

    # S7 群標籤與分派表一致
    cg = spec.chapter_group(corpus)
    for ch in corpus.chapter_order:
        if ch not in cg:
            r.fail("S7", f"章「{short(ch)}」無法唯一歸到分派表的某一群")
    for a in anchors:
        if cg.get(a.chapter) and cg[a.chapter] != a.group:
            r.fail("S7", f"{a.label()} 標 {a.group}，分派表歸 {cg[a.chapter]}"
                         f"（SPEC:{a.line_no}）")

    # S8 分派表的章數段數
    for g, d in spec.dispatch.items():
        chs = [c for c in corpus.chapter_order if cg.get(c) == g]
        if len(chs) != d["n_ch"]:
            r.fail("S8", f"{g} 分派表寫 {d['n_ch']} 章，語料 {len(chs)} 章")
        n = sum(corpus.chapter_size[c] for c in chs)
        if n != d["n_pa"]:
            r.fail("S8", f"{g} 分派表寫 {d['n_pa']} 段，語料 {n} 段")
        got = sorted({b for c in chs for b in corpus.chapter_batches[c]})
        if got != d["batches"]:
            r.fail("S8", f"{g} 分派表批號 {d['batches']}，語料 {got}")

    # S9 批次表
    for b, n in spec.batch_table.items():
        if corpus.batch_size[b] != n:
            r.fail("S9", f"批次表 {b} 寫 {n} 段，語料 {corpus.batch_size[b]} 段")
    if set(spec.batch_table) != set(corpus.batch_size):
        r.fail("S9", f"批次表批號與語料不符：{set(spec.batch_table) ^ set(corpus.batch_size)}")
    total = sum(corpus.batch_size.values())
    if spec.declared.get("total") != total:
        r.fail("S9", f"驗收條件寫合計 {spec.declared.get('total')}，語料 {total}")

    # S10 A 類散文的逐批段數必須等於批次表
    if spec.prose_batch_counts != spec.batch_table:
        diff = {k for k in set(spec.prose_batch_counts) | set(spec.batch_table)
                if spec.prose_batch_counts.get(k) != spec.batch_table.get(k)}
        r.fail("S10", f"A 類 1 的逐批段數與批次表不符：{sorted(diff)}")

    # S11 宣告的錨點段數
    for kind, decl, got in (("null", "null", len(ns)), ("hit", "hit", len(hs))):
        if spec.declared.get(decl) != got:
            r.fail("S11", f"驗收條件寫 {kind} {spec.declared.get(decl)} 段，表列 {got} 段")
    if spec.declared.get("forbid") != len(spec.forbid):
        r.fail("S11", f"驗收條件寫禁格 {spec.declared.get('forbid')} 列，"
                      f"表列 {len(spec.forbid)} 列")
    n_must = sum(1 for a in spec.hit if a.domain)
    if spec.declared.get("musthave") != n_must:
        r.fail("S11", f"驗收條件寫必含格 {spec.declared.get('musthave')} 條，"
                      f"命中表 {n_must} 條")

    # S12 散文清單與表格對拍（短章名比對）
    tbl_must = {(short(a.chapter), a.para_index, a.domain)
                for a in spec.hit if isinstance(a.domain, str)}
    if tbl_must != spec.prose_musthave:
        for x in sorted(tbl_must - spec.prose_musthave):
            r.fail("S12", f"命中表有必含 {x[0]}[{x[1]}]={x[2]}，A 類 5 散文沒列")
        for x in sorted(spec.prose_musthave - tbl_must):
            r.fail("S12", f"A 類 5 散文列了 {x[0]}[{x[1]}]={x[2]}，命中表沒有")
    tbl_forbid = {(short(a.chapter), a.para_index, a.domain) for a in spec.forbid}
    if tbl_forbid != spec.prose_forbid:
        for x in sorted(tbl_forbid - spec.prose_forbid):
            r.fail("S12", f"禁格表有 {x[0]}[{x[1]}]∌{x[2]}，A 類 6 散文沒列")
        for x in sorted(spec.prose_forbid - tbl_forbid):
            r.fail("S12", f"A 類 6 散文列了 {x[0]}[{x[1]}]∌{x[2]}，禁格表沒有")

    # S13 id 表
    if spec.domain_ids != DOMAIN_IDS:
        r.fail("S13", f"領域表 id 與程式常數不符：{spec.domain_ids}")
    if sorted(spec.mode_ids) != sorted(MODE_IDS):
        r.fail("S13", f"mode 表 id 與程式常數不符：{spec.mode_ids}")

    # S14 G5 兩側可解析且落在語料裡
    sides = spec.g5_sides()
    if not sides:
        r.fail("S14", "解析不到 G5 兩側的段落範圍")
    else:
        for name, keys in sides.items():
            for ch, i in keys:
                full = next((c for c in corpus.chapter_order
                             if c == ch or c.startswith(ch + "〈")), None)
                if full is None or (full, i) not in corpus.para:
                    r.fail("S14", f"G5 {name} 的 {ch}[{i}] 不在語料裡")
        n_reg, n_self = len(sides["registry"]), len(sides["self"])
        if spec.declared.get("g5_reg") != n_reg:
            r.fail("S14", f"G5 登錄側宣告 {spec.declared.get('g5_reg')} 段，算出 {n_reg}")
        if spec.declared.get("g5_self") != n_self:
            r.fail("S14", f"G5 自述側宣告 {spec.declared.get('g5_self')} 段，算出 {n_self}")

    # S15 每個宣告過的批次都有錨點覆蓋（墨子型整族停擺的護欄）
    covered = {a.batch for a in anchors}
    missing = sorted(set(spec.batch_table) - covered)
    if missing:
        r.note("S15", f"這些批沒有任何錨點：{missing}")

    # S16 灰區：三個數字與宣告相符（驗數量，不驗非空），指名的段落都在語料裡
    for key, got, what in (("gray", spec.gray_bullets, "bullet"),
                           ("gray_ref", spec.gray_ref_bullets, "指名段落的 bullet"),
                           ("gray_para", len({(c, i) for c, i, _ in spec.gray_refs}),
                            "相異段")):
        if got != spec.declared.get(key):
            r.fail("S16", f"灰區{what}解析到 {got}，正文宣告 {spec.declared.get(key)}")
    for chap, idx, ln in spec.gray_refs:
        if (chap, idx) not in corpus.para:
            r.fail("S16", f"L{ln} 灰區指名的 `{chap}`[{idx}] 不在語料裡")

    return r


# --------------------------------------------------------------------------
# 批次輸出驗收
# --------------------------------------------------------------------------

def resolve_chapter(name: str, corpus: Corpus) -> str | None:
    if name in corpus.chapter_size:
        return name
    cand = [c for c in corpus.chapter_order if c.startswith(name + "〈")]
    return cand[0] if len(cand) == 1 else None


def quote_in_para(reason: str, text: str) -> bool:
    body = reason.replace("`", "")
    for i in range(len(body) - QUOTE_WINDOW + 1):
        if body[i:i + QUOTE_WINDOW] in text:
            return True
    return False


def check_batch(path: pathlib.Path, spec: Spec, corpus: Corpus,
                r: Report) -> list[dict]:
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except Exception as exc:                                   # noqa: BLE001
        r.fail("A0", f"{path.name} 不是合法 JSON：{exc}")
        return []
    batch = re.sub(r"\.(json|md)$", "", str(data.get("batch") or path.stem))
    if batch != path.stem:
        r.fail("A0", f"{path.name} 的 batch 欄寫 {data.get('batch')}，與檔名不符")
    rows = data.get("rows")
    if not isinstance(rows, list):
        r.fail("A0", f"{path.name} 缺 rows 陣列")
        return []

    cg = spec.chapter_group(corpus)
    expect = {k for k, v in corpus.para.items() if v[0] == batch}
    seen: set[tuple[str, int]] = set()
    resolved: list[dict] = []

    for n, row in enumerate(rows, 1):
        ch_raw = row.get("chapter")
        idx = row.get("para_index")
        if not isinstance(ch_raw, str) or not isinstance(idx, int):
            r.fail("A1", f"{batch} 第 {n} 列缺 chapter 或 para_index")
            continue
        ch = resolve_chapter(ch_raw, corpus)
        if ch is None:
            r.fail("A1", f"{batch} 第 {n} 列章名不認得：{ch_raw[:20]}")
            continue
        if ch != ch_raw:
            r.fail("A1", f"{batch} {short(ch)}[{idx}] 章名被截短，"
                         f"必須用完整字串（含四庫案語）")
        key = (ch, idx)
        if key not in corpus.para:
            r.fail("A1", f"{batch} {short(ch)}[{idx}] 不存在")
            continue
        if corpus.para[key][0] != batch:
            r.fail("A1", f"{batch} 混進別批的 {short(ch)}[{idx}]"
                         f"（屬於 {corpus.para[key][0]}）")
            continue
        if key in seen:
            r.fail("A1", f"{batch} {short(ch)}[{idx}] 重複出現")
            continue
        seen.add(key)

        doms = row.get("domains")
        modes = row.get("modes")
        reason = row.get("reason")
        if not isinstance(doms, list) or not isinstance(modes, list):
            r.fail("A1", f"{batch} {short(ch)}[{idx}] domains/modes 不是陣列")
            continue
        if not isinstance(reason, str) or not reason.strip():
            r.fail("A1", f"{batch} {short(ch)}[{idx}] reason 空白")
            reason = ""

        if ch not in cg:
            r.fail("A2", f"{batch} 章「{short(ch)}」歸不到任何體例群")

        for d in doms:
            if d in BANNED_DOMAINS:
                r.fail("A12", f"{batch} {short(ch)}[{idx}] domains 出現 {d}")
            elif d not in DOMAIN_IDS:
                r.fail("A12", f"{batch} {short(ch)}[{idx}] 非法 domain：{d}")
        if len(set(doms)) != len(doms):
            r.fail("A12", f"{batch} {short(ch)}[{idx}] domains 有重複值")
        for m in modes:
            if m not in MODE_IDS:
                r.fail("A12", f"{batch} {short(ch)}[{idx}] 非法 mode：{m}")
        if "worked_instance" in modes:
            r.fail("A11", f"{batch} {short(ch)}[{idx}] 出現 worked_instance")
        if len(modes) > 3:
            r.note("B0", f"{batch} {short(ch)}[{idx}] modes 疊了 {len(modes)} 個")

        need = 20 * len(doms)
        if len(reason) < need:
            r.fail("A13", f"{batch} {short(ch)}[{idx}] 標 {len(doms)} 格但 reason "
                          f"只有 {len(reason)} 字（需 ≥ {need}）")
        if reason and not quote_in_para(reason, corpus.text(key)):
            r.fail("A14", f"{batch} {short(ch)}[{idx}] reason 沒有任何 "
                          f"{QUOTE_WINDOW} 字以上的片段逐字落在該段正文裡")

        resolved.append({"key": key, "domains": doms, "modes": modes,
                         "reason": reason, "batch": batch})

    missing = sorted(expect - seen)
    for k in missing:
        r.fail("A1", f"{batch} 缺 {short(k[0])}[{k[1]}]")
    if len(rows) != len(expect) and not missing:
        r.fail("A1", f"{batch} rows {len(rows)} 列，應為 {len(expect)} 列")

    by_key = {d["key"]: d for d in resolved}

    for a in spec.null:
        if a.batch == batch and a.key in by_key and by_key[a.key]["domains"]:
            r.fail("A3", f"{a.label()} 是判空錨點，卻標了 "
                         f"{by_key[a.key]['domains']}（SPEC:{a.line_no}）")
    for a in spec.hit:
        if a.batch != batch or a.key not in by_key:
            continue
        got = by_key[a.key]["domains"]
        if not got:
            r.fail("A4", f"{a.label()} 是命中錨點，卻判空（SPEC:{a.line_no}）")
        elif isinstance(a.domain, str) and a.domain not in got:
            r.fail("A5", f"{a.label()} 必含 {a.domain}，實得 {got}"
                         f"（SPEC:{a.line_no}）")
    for a in spec.forbid:
        if a.batch == batch and a.key in by_key:
            got = by_key[a.key]["domains"]
            if isinstance(a.domain, str) and a.domain in got:
                r.fail("A6", f"{a.label()} 禁填 {a.domain}，實得 {got}"
                             f"（SPEC:{a.line_no}）")

    sides = spec.g5_sides()
    reg = {(resolve_chapter(c, corpus), i) for c, i in sides.get("registry", [])}
    for d in resolved:
        if d["key"] in reg and "formalization" in d["modes"]:
            r.fail("A10", f"{short(d['key'][0])}[{d['key'][1]}] 是書目著錄，"
                          f"modes 不得含 formalization")
    return resolved


def check_cross(all_rows: list[dict], spec: Spec, corpus: Corpus,
                r: Report) -> None:
    by_key = {d["key"]: d for d in all_rows}

    # A8 著書篇十[38] 與 [43] 必須同判
    ch = resolve_chapter("著書篇十", corpus)
    a, b = by_key.get((ch, 38)), by_key.get((ch, 43))
    if a and b and bool(a["domains"]) != bool(b["domains"]):
        r.fail("A8", f"著書篇十[38] 與 [43] 近逐字重出，必須同判，"
                     f"實得 {a['domains']} / {b['domains']}")

    # A9 G5 登錄側命中段數不得多於自述側
    sides = spec.g5_sides()
    if sides:
        def hits(name: str) -> int:
            keys = {(resolve_chapter(c, corpus), i) for c, i in sides[name]}
            return sum(1 for k in keys
                       if k in by_key and by_key[k]["domains"])
        n_reg, n_self = hits("registry"), hits("self")
        if n_reg > n_self:
            r.fail("A9", f"G5 登錄側命中 {n_reg} 段 > 自述側 {n_self} 段，兩側被合併判了")

    if len(all_rows) != sum(corpus.batch_size.values()):
        r.note("B1", f"全書回收 {len(all_rows)} 段，"
                     f"應為 {sum(corpus.batch_size.values())} 段（尚未收齊）")


def report_bands(all_rows: list[dict], spec: Spec, corpus: Corpus) -> None:
    cg = spec.chapter_group(corpus)
    print("\n--- B 類實測（不擋收） ---")
    per = defaultdict(lambda: [0, 0])
    for d in all_rows:
        ch = d["key"][0]
        slot = per[(cg.get(ch, "?"), short(ch))]
        slot[0] += 1
        slot[1] += 1 if d["domains"] else 0
    for (g, ch), (n, h) in sorted(per.items()):
        print(f"  {g} {ch}: {h}/{n} = {h / n:.0%}")
    n = len(all_rows)
    h = sum(1 for d in all_rows if d["domains"])
    if n:
        print(f"  全書: {h}/{n} = {h / n:.0%}")
    dc = Counter(x for d in all_rows for x in d["domains"])
    mc = Counter(x for d in all_rows for x in d["modes"])
    print("  domains:", " ".join(f"{k}={dc.get(k, 0)}" for k in DOMAIN_IDS))
    print("  modes  :", " ".join(f"{k}={mc.get(k, 0)}" for k in MODE_IDS))


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--check-spec", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    corpus = Corpus(HERE)
    spec = Spec(SPEC_PATH, corpus.chapter_order)

    if args.check_spec:
        r = check_spec(spec, corpus)
        r.dump("SPEC 自檢")
        return 0 if (r.ok() and not r.notes) else 1

    paths = [pathlib.Path(f) for f in args.files]
    if args.all:
        paths = sorted(OUT_DIR.glob("b[0-9][0-9].json"))
    if not paths:
        print("沒有指定要驗的檔案（用 out/bNN.json 或 --all）")
        return 2

    r = Report()
    rows: list[dict] = []
    for p in paths:
        rows += check_batch(p, spec, corpus, r)
    if args.all:
        check_cross(rows, spec, corpus, r)
    r.dump("批次驗收：" + " ".join(p.stem for p in paths))
    if args.all and rows:
        report_bands(rows, spec, corpus)
    return 0 if r.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
