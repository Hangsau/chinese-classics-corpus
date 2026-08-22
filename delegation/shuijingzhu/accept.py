"""水經注段落標註驗收器：A 類硬條件、B 類數量提示與 SPEC 自檢。

錨點、章名、段號、逐字引句、領域 id、mode id、超長段清單全都在執行時從同目錄 SPEC.md
解析；本檔不維護第二份事實清單（孔叢子 18 個假 FAIL 出自驗收器抄了一份沒被驗證過的清單）。
SPEC 改字後，驗收行為會隨之改變。

本書的兩個特殊處：
  - 夾注 `〈…〉` 佔 98.5% 字元，命中幾乎全來自注文；引句比對一律吃原文（含夾注內文），
    不做「只落注文就要指名注家」那類檢查（本書只有酈道元一家注）。
  - 經文段（整段不含 `〈`，全書 301 段）判空是機械條件，不列表、不手抄，
    由本檔就地判定；唯一例外 `原序`[1] 由 SPEC 條文點名。

用法：
  PYTHONIOENCODING=utf-8 python delegation/shuijingzhu/accept.py --check-spec
  PYTHONIOENCODING=utf-8 python delegation/shuijingzhu/accept.py [b01 b19 ...]
  PYTHONIOENCODING=utf-8 python delegation/shuijingzhu/accept.py --out-dir <dir>
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
SPEC_PATH = os.path.join(BASE, "SPEC.md")

BATCH_RE = re.compile(r"^b\d{2}$")
INLINE_KEY_RE = re.compile(r"`([^`]+)`\[(\d+)\]")

# 五張錨點表的子標題前綴 → 內部代號
ANCHOR_TABLES = [
    ("必須命中", "hit"),
    ("破除側", "xi"),
    ("認證側", "xii"),
    ("過度側", "guo"),
    ("技術側", "noxii"),
]


# ---------------------------------------------------------------------------
# 批次檔


def read_batches():
    """讀 bNN.md，保留夾注原文；同時回報章標頭段數與批摘要的不一致。"""
    paras = {}
    batch_of = {}
    chapter_len = {}
    batch_chapters = {}
    problems = []

    for path in sorted(glob.glob(os.path.join(BASE, "b[0-9][0-9].md"))):
        batch = os.path.basename(path)[:3]
        batch_chapters[batch] = []
        chapter = None
        seen = {}
        summary = None
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                m = re.match(r"^> 本批\s*(\d+)\s*段，含\s*(\d+)\s*章。", line)
                if m:
                    summary = (int(m.group(1)), int(m.group(2)))
                    continue
                m = re.match(r"^## (.+)（(\d+) 段）\s*$", line)
                if m:
                    chapter = m.group(1).strip()
                    chapter_len[chapter] = chapter_len.get(chapter, 0) + int(m.group(2))
                    batch_chapters[batch].append((chapter, int(m.group(2))))
                    seen[chapter] = 0
                    continue
                m = re.match(r"^\[(\d+)\]\s?(.*)$", line.rstrip("\n"))
                if not m:
                    continue
                if chapter is None:
                    problems.append("%s:%d 段落出現在章標頭之前" % (path, lineno))
                    continue
                idx = int(m.group(1))
                key = (chapter, idx)
                if key in paras:
                    problems.append("%s:%d 段序重複 %s[%d]" % (path, lineno, chapter, idx))
                paras[key] = m.group(2)
                batch_of[key] = batch
                seen[chapter] += 1
        if summary:
            n_para = sum(1 for k in batch_of if batch_of[k] == batch)
            if n_para != summary[0] or len(batch_chapters[batch]) != summary[1]:
                problems.append(
                    "%s 批摘要宣告 %d 段 %d 章，實際 %d 段 %d 章"
                    % (path, summary[0], summary[1], n_para, len(batch_chapters[batch]))
                )
        for ch, n in batch_chapters[batch]:
            if seen.get(ch, 0) != n:
                problems.append("%s 章標頭 %s 宣告 %d 段，實際 %d 段" % (path, ch, n, seen.get(ch, 0)))

    return paras, batch_of, chapter_len, batch_chapters, problems


# ---------------------------------------------------------------------------
# SPEC 解析


def _sections(spec):
    out = {}
    for part in re.split(r"^## ", spec, flags=re.M):
        head, sep, _ = part.partition("\n")
        if sep:
            out[head.strip()] = part
    return out


def _cells(line):
    line = line.strip()
    if not (line.startswith("|") and line.endswith("|")):
        return None
    return [c.strip() for c in line[1:-1].split("|")]


def _is_rule_row(cells):
    return bool(cells) and not set("".join(cells)) <= set("-: ")


def anchor_quote_text(cell):
    """表格最外層「」是引句欄的引用框；框內文字（含標點）才須逐字存在。"""
    if len(cell) >= 2 and cell.startswith("「") and cell.endswith("」"):
        return cell[1:-1]
    return cell


def _domain_tokens(text, domains):
    return [t for t in re.findall(r"[IVX]+", text) if t in domains]


def parse_spec():
    with open(SPEC_PATH, encoding="utf-8") as fh:
        spec_text = fh.read()
    secs = _sections(spec_text)

    domains = []
    for line in secs.get("13 個領域（`domains` 只能填這些 id）", "").splitlines():
        c = _cells(line)
        if _is_rule_row(c) and len(c) >= 3 and re.fullmatch(r"[IVX]+", c[0]):
            domains.append(c[0])

    modes = []
    for line in secs.get("8 個 discourse_mode（`modes` 只能填這些 id）", "").splitlines():
        c = _cells(line)
        if _is_rule_row(c) and len(c) >= 3 and re.fullmatch(r"`\w+`", c[0]):
            modes.append(c[0].strip("`"))

    # 錨點五表
    anchors = {code: [] for _, code in ANCHOR_TABLES}
    sec = secs.get(
        "必須命中的錨點（回收後逐條機械檢查，`domains` 必須含指定的格；標「X 或 Y」的至少含其一）", ""
    )
    code = None
    for line in sec.splitlines():
        m = re.match(r"^### (.+)$", line)
        if m:
            title = m.group(1).replace("*", "").strip()
            code = None
            for prefix, c in ANCHOR_TABLES:
                if title.startswith(prefix):
                    code = c
            continue
        if code is None:
            continue
        c = _cells(line)
        if not _is_rule_row(c) or len(c) < 4:
            continue
        m = re.match(r"^\[(\d+)\]$", c[1])
        if not m:
            continue
        entry = {
            "chapter": c[0],
            "para_index": int(m.group(1)),
            "batch": c[2],
            "quote": anchor_quote_text(c[3]),
        }
        if code == "noxii":
            entry["require"] = []
        else:
            entry["require"] = _domain_tokens(c[4] if len(c) > 4 else "", domains)
        anchors[code].append(entry)

    # 純數字章名（條文逐字列出）
    m = re.search(r"純數字章名\**（[^）]*）\**：\n((?:\s*`\d\d`[^\n]*\n)+)", spec_text)
    numeric_chapters = re.findall(r"`(\d\d)`", m.group(1)) if m else []

    # 超長段清單
    m = re.search(r"\*\*13 段超過 3,000 字\*\*[^\n]*\n\n((?:[^\n]*`[^\n]*\n)+)", spec_text)
    superlong = []
    if m:
        for ch, idx, n in re.findall(r"`([^`]+)`\[(\d+)\]\s*(\d+)", m.group(1)):
            superlong.append({"chapter": ch, "para_index": int(idx), "chars": int(n)})

    # 經文段條文宣告的數量與例外
    m = re.search(r"全書\s*(\d+)\s*段，\*\*唯一例外是\s*`([^`]+)`\[(\d+)\]\*\*", spec_text)
    jing = {
        "count": int(m.group(1)) if m else None,
        "exception": (m.group(2), int(m.group(3))) if m else None,
    }

    # A 類條文
    acc = secs.get("驗收條件", "")
    apart = acc.split("### B 類", 1)[0]
    if "### A 類" in apart:
        apart = apart.split("### A 類", 1)[1]
    clauses = {
        int(mm.group(1)): mm.group(2).strip()
        for mm in re.finditer(r"^\s*(\d+)\.\s*(.*?)(?=^\s*\d+\.\s|\Z)", apart, re.M | re.S)
    }

    # 條文宣告的錨點數量（供 --check-spec 與表格對拍）
    declared = {}
    for num, code, pat in (
        (4, "hit", r"必須命中的錨點\s*(\d+)\s*段"),
        (5, "xi", r"破除側\s*(\d+)\s*段"),
        (6, "xii", r"認證側\s*(\d+)\s*段"),
        (7, "guo", r"過度側\s*(\d+)\s*段"),
        (8, "noxii", r"技術側\s*(\d+)\s*段"),
    ):
        mm = re.search(pat, clauses.get(num, "").replace("*", ""))
        if mm:
            declared[code] = int(mm.group(1))

    mm = re.search(r"`domains`\s*長度超過\s*(\d+)", clauses.get(9, ""))
    max_domains = int(mm.group(1)) if mm else 3

    # 章名與段號同時掛兩表的段（條文之外的補述），只作 --check-spec 交叉對照
    cross = re.search(r"\*\*三段同時掛兩張表\*\*(.*?)\n\n", spec_text, re.S)
    cross_keys = [(ch, int(i)) for ch, i in INLINE_KEY_RE.findall(cross.group(1))] if cross else []

    return {
        "text": spec_text,
        "domains": domains,
        "modes": modes,
        "anchors": anchors,
        "numeric_chapters": numeric_chapters,
        "superlong": superlong,
        "jing": jing,
        "clauses": clauses,
        "declared": declared,
        "max_domains": max_domains,
        "cross_keys": cross_keys,
    }


# ---------------------------------------------------------------------------
# 引句比對


_VARIANTS = str.maketrans({"『": "「", "』": "」"})
_ELLIPSIS = re.compile(r"…{2,}|\.{3,}")
_NOTE = re.compile(r"〈[^〈〉]*〉")
_PUNCT = re.compile(r"[，。；：、？！「」『』（）〈〉《》…—·　\s]")


def strip_annotations(text):
    prev = None
    while prev != text:
        prev = text
        text = _NOTE.sub("", text)
    return text


def strip_note_marks(text):
    return text.replace("〈", "").replace("〉", "")


def quote_in_text(text, quote, ignore_punct=False):
    """引句對得上原文：容許夾注符號、節略號分段與巢狀引號的『』寫法。

    本書 98.5% 的內容在 `〈…〉` 內，所以比對基準是「去掉夾注符號的全文」，
    而不是戰國策那種「剝掉夾注只留正文」。`ignore_punct` 另計一類（標點不逐字，
    仍要求去標點後字元相鄰，拼接兩處遠隔句子一樣過不了）。
    """
    bases = [text, strip_note_marks(text), strip_annotations(text)]
    bases += [b.translate(_VARIANTS) for b in bases]
    tiers = [(bases, lambda s: s)]
    if ignore_punct:
        tiers.append(([_PUNCT.sub("", b) for b in bases], lambda s: _PUNCT.sub("", s)))
    frags = [f for f in _ELLIPSIS.split(quote) if f]
    for hays, norm in tiers:
        if all(
            any(norm(f) in h or norm(f.translate(_VARIANTS)) in h for h in hays)
            for f in frags
        ):
            return True
    return False


def extract_reason_quotes(reason):
    if not isinstance(reason, str):
        return []
    return [q for q in re.findall(r"「([^」]+)」", reason) if q]


def occurrence_count(text, quote):
    hay = _PUNCT.sub("", strip_note_marks(text).translate(_VARIANTS))
    needle = _PUNCT.sub("", quote.translate(_VARIANTS))
    if not needle:
        return 0
    n = start = 0
    while True:
        pos = hay.find(needle, start)
        if pos < 0:
            return n
        n += 1
        start = pos + 1


# ---------------------------------------------------------------------------
# SPEC 自檢


def check_spec():
    spec = parse_spec()
    paras, batch_of, _chapter_len, _batch_chapters, batch_problems = read_batches()
    fails = []

    for p in batch_problems:
        fails.append("S0 批次檔本身不一致：%s" % p)

    if len(spec["domains"]) != 13:
        fails.append("S1 領域表解析出 %d 格，應為 13" % len(spec["domains"]))
    if len(spec["modes"]) != 8:
        fails.append("S1 mode 表解析出 %d 個，應為 8" % len(spec["modes"]))

    # S2 條文宣告的錨點數 vs 表格實得
    for _prefix, code in ANCHOR_TABLES:
        got = len(spec["anchors"][code])
        want = spec["declared"].get(code)
        if want is None:
            fails.append("S2 A 類條文沒有宣告 %s 表的段數" % code)
        elif want != got:
            fails.append("S2 %s 表 %d 列，但 A 類條文宣告 %d 段" % (code, got, want))

    # S3 錨點逐條回批次檔對拍
    for _prefix, code in ANCHOR_TABLES:
        seen = set()
        for a in spec["anchors"][code]:
            key = (a["chapter"], a["para_index"])
            if key in seen:
                fails.append("S3 %s 表重複列 %s[%d]" % (code, *key))
            seen.add(key)
            text = paras.get(key)
            if text is None:
                fails.append("S3 %s 表 %s[%d] 在批次檔中不存在" % (code, *key))
                continue
            if batch_of[key] != a["batch"]:
                fails.append(
                    "S3 %s 表 %s[%d] 標批 %s，實際在 %s"
                    % (code, key[0], key[1], a["batch"], batch_of[key])
                )
            if not quote_in_text(text, a["quote"]):
                fails.append("S3 %s 表 %s[%d] 引句對不上原文：「%s」" % (code, key[0], key[1], a["quote"][:24]))
            if code != "noxii" and not a["require"]:
                fails.append("S3 %s 表 %s[%d] 沒解析出必含領域" % (code, *key))
            if code == "xi" and a["require"] != ["XI"]:
                fails.append("S3 破除側 %s[%d] 必含欄不是 XI" % key)
            if code in ("xii", "guo") and a["require"] != ["XII"]:
                fails.append("S3 %s 表 %s[%d] 必含欄不是 XII" % (code, *key))

    # S4 破除側不得與認證／過度側同段（條文 5 要求不得含 XII）
    xi_keys = {(a["chapter"], a["para_index"]) for a in spec["anchors"]["xi"]}
    xii_keys = {(a["chapter"], a["para_index"]) for a in spec["anchors"]["xii"]}
    xii_keys |= {(a["chapter"], a["para_index"]) for a in spec["anchors"]["guo"]}
    noxii_keys = {(a["chapter"], a["para_index"]) for a in spec["anchors"]["noxii"]}
    for key in sorted(xi_keys & xii_keys):
        fails.append("S4 %s[%d] 同時在破除側與認證／過度側，條件互斥" % key)
    for key in sorted(xi_keys & noxii_keys):
        fails.append("S4 %s[%d] 同時在破除側與技術側，語意衝突" % key)
    for key in sorted(xii_keys & noxii_keys):
        fails.append("S4 %s[%d] 同時要求填 XII 與不得填 XII" % key)

    # S5 經文段：SPEC 宣告的數量與例外要對得上批次檔實況
    jing = [k for k, t in paras.items() if "〈" not in t]
    if spec["jing"]["count"] != len(jing):
        fails.append("S5 SPEC 宣告經文段 %s，批次檔實得 %d" % (spec["jing"]["count"], len(jing)))
    exc = spec["jing"]["exception"]
    if exc is None:
        fails.append("S5 SPEC 沒有點名經文段的唯一例外")
    elif exc not in paras:
        fails.append("S5 經文段例外 %s[%d] 不存在" % exc)
    elif "〈" in paras[exc]:
        fails.append("S5 經文段例外 %s[%d] 其實含夾注，不是經文段" % exc)

    # 例外之外的經文段不得同時出現在命中錨點表
    hit_keys = {(a["chapter"], a["para_index"]) for a in spec["anchors"]["hit"]}
    for key in sorted(hit_keys & set(jing)):
        if key != exc:
            fails.append("S5 %s[%d] 是經文段卻列進必須命中表" % key)

    # S6 超長段清單對拍
    actual = {k: len(t) for k, t in paras.items() if len(t) > 3000}
    declared = {(s["chapter"], s["para_index"]): s["chars"] for s in spec["superlong"]}
    if declared != actual:
        for key in sorted(set(declared) | set(actual)):
            if declared.get(key) != actual.get(key):
                fails.append(
                    "S6 超長段 %s[%d]：SPEC 記 %s 字，實際 %s 字"
                    % (key[0], key[1], declared.get(key, "未列"), actual.get(key, "未列"))
                )

    # S7 純數字章名
    actual_numeric = sorted({ch for ch, _ in paras if ch.isdigit()})
    if sorted(spec["numeric_chapters"]) != actual_numeric:
        fails.append(
            "S7 純數字章名 SPEC 列 %s，實際 %s"
            % (sorted(spec["numeric_chapters"]), actual_numeric)
        )

    # S8 條文補述點名的跨表段要真的跨表
    for key in spec["cross_keys"]:
        in_tables = [c for _p, c in ANCHOR_TABLES if key in {
            (a["chapter"], a["para_index"]) for a in spec["anchors"][c]
        }]
        if len(in_tables) < 2:
            fails.append("S8 條文說 %s[%d] 同時掛兩張表，實際只在 %s" % (key[0], key[1], in_tables))

    total = sum(len(v) for v in spec["anchors"].values())
    keys = set()
    for v in spec["anchors"].values():
        keys |= {(a["chapter"], a["para_index"]) for a in v}
    print("SPEC 自檢：批次 %d 段、錨點 %d 列／%d 段、經文段 %d、超長段 %d"
          % (len(paras), total, len(keys), len(jing), len(actual)))
    if fails:
        for f in fails:
            print("  FAIL " + f)
        print("SPEC 自檢：%d 個 FAIL" % len(fails))
        return 1
    print("SPEC 自檢：0 FAIL")
    return 0


# ---------------------------------------------------------------------------
# 回收檢查


def resolve_out_dir(value):
    if value:
        return value if os.path.isabs(value) else os.path.join(BASE, value)
    return os.path.join(BASE, "out")


def load_out(out_dir, wanted, known_batches):
    rows = {}
    errors = []
    dupes = []
    seen_batches = set()
    for path in sorted(glob.glob(os.path.join(out_dir, "b[0-9][0-9].json"))):
        batch = os.path.basename(path)[:3]
        if wanted and batch not in wanted:
            continue
        if batch not in known_batches:
            errors.append("%s 沒有對應的批次檔" % path)
            continue
        seen_batches.add(batch)
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            errors.append("%s 無法解析：%s" % (path, exc))
            continue
        for row in data.get("rows", []):
            ch = row.get("chapter")
            idx = row.get("para_index")
            if not isinstance(ch, str) or not isinstance(idx, int):
                errors.append("%s 有 chapter/para_index 型別不對的 row" % path)
                continue
            key = (ch, idx)
            if key in rows:
                dupes.append(key)
            row["_batch"] = batch
            rows[key] = row
    return rows, seen_batches, dupes, errors


def _list_field(row, name):
    v = row.get(name)
    return v if isinstance(v, list) else []


def run(out_dir, wanted):
    spec = parse_spec()
    paras, batch_of, _cl, _bc, batch_problems = read_batches()
    known = sorted(set(batch_of.values()))
    rows, seen_batches, dupes, load_errors = load_out(out_dir, wanted, known)

    selected = seen_batches if not wanted else (wanted & set(known))
    scope = {k for k in paras if batch_of[k] in selected}

    fails = []
    warns = []

    for p in batch_problems:
        fails.append("A0 批次檔本身不一致：%s" % p)
    for e in load_errors:
        fails.append("A1 " + e)
    for key in sorted(set(dupes)):
        fails.append("A1 %s[%d] 在多個 out 檔重複出現" % key)

    # A1 覆蓋
    missing = sorted(scope - set(rows))
    extra = sorted(set(rows) - scope)
    for key in missing:
        fails.append("A1 缺 row：%s[%d]（%s）" % (key[0], key[1], batch_of[key]))
    for key in extra:
        fails.append("A1 多出 row：%s[%d]" % key)

    live = {k: v for k, v in rows.items() if k in scope}

    # A2 id 合法性 / A9 領域上限 / A10 reason 非空 / A13 worked_instance
    for key in sorted(live):
        row = live[key]
        doms = _list_field(row, "domains")
        modes = _list_field(row, "modes")
        for d in doms:
            if d not in spec["domains"]:
                fails.append("A2 %s[%d] 非法 domain：%r" % (key[0], key[1], d))
        for m in modes:
            if m not in spec["modes"]:
                fails.append("A2 %s[%d] 非法 mode：%r" % (key[0], key[1], m))
        if len(doms) != len(set(doms)):
            fails.append("A2 %s[%d] domains 有重複" % key)
        if len(doms) > spec["max_domains"]:
            fails.append("A9 %s[%d] 標了 %d 個領域，上限 %d"
                         % (key[0], key[1], len(doms), spec["max_domains"]))
        if not str(row.get("reason", "")).strip():
            fails.append("A10 %s[%d] reason 空白" % key)
        if "worked_instance" in modes:
            fails.append("A13 %s[%d] 出現 worked_instance" % key)
        if not modes:
            warns.append("modes 為空：%s[%d]" % key)

    # A3 經文段判空
    exc = spec["jing"]["exception"]
    for key in sorted(scope):
        if "〈" in paras[key] or key == exc:
            continue
        row = live.get(key)
        if row and _list_field(row, "domains"):
            fails.append("A3 %s[%d] 是經文段（整段無夾注）卻命中 %s"
                         % (key[0], key[1], _list_field(row, "domains")))

    # A4–A8 錨點
    def check_anchor(code, label, mode):
        for a in spec["anchors"][code]:
            key = (a["chapter"], a["para_index"])
            if key not in scope:
                continue
            row = live.get(key)
            if row is None:
                continue
            doms = _list_field(row, "domains")
            if mode == "require_any":
                if not any(d in doms for d in a["require"]):
                    fails.append("%s %s[%d] 應含 %s，實得 %s"
                                 % (label, key[0], key[1], "或".join(a["require"]), doms or "[]"))
            elif mode == "forbid_xii":
                if "XII" in doms:
                    fails.append("%s %s[%d] 不得填 XII，實得 %s" % (label, key[0], key[1], doms))

    check_anchor("hit", "A4", "require_any")
    for a in spec["anchors"]["xi"]:
        key = (a["chapter"], a["para_index"])
        if key not in scope or key not in live:
            continue
        doms = _list_field(live[key], "domains")
        if "XI" not in doms:
            fails.append("A5 %s[%d] 破除側應含 XI，實得 %s" % (key[0], key[1], doms or "[]"))
        if "XII" in doms:
            fails.append("A5 %s[%d] 破除側不得含 XII，實得 %s" % (key[0], key[1], doms))
    check_anchor("xii", "A6", "require_any")
    check_anchor("guo", "A7", "require_any")
    check_anchor("noxii", "A8", "forbid_xii")

    # A11 命中理由須含逐字引句且對得上原文
    punct_drift = []
    for key in sorted(live):
        row = live[key]
        if not _list_field(row, "domains"):
            continue
        quotes = extract_reason_quotes(row.get("reason", ""))
        if not quotes:
            fails.append("A11 %s[%d] 命中但 reason 沒有「」逐字引句" % key)
            continue
        text = paras[key]
        for q in quotes:
            if quote_in_text(text, q):
                continue
            if quote_in_text(text, q, ignore_punct=True):
                punct_drift.append((key, q))
                continue
            fails.append("A11 %s[%d] 引句不在本段：「%s」" % (key[0], key[1], q[:26]))

    # A12 超長段引句須唯一定位
    superlong = {(s["chapter"], s["para_index"]) for s in spec["superlong"]}
    for key in sorted(superlong & set(live)):
        row = live[key]
        if not _list_field(row, "domains"):
            continue
        for q in extract_reason_quotes(row.get("reason", "")):
            n = occurrence_count(paras[key], q)
            if n > 1:
                fails.append("A12 %s[%d] 超長段引句在段內出現 %d 次，無法定位：「%s」"
                             % (key[0], key[1], n, q[:26]))

    for key, q in punct_drift:
        warns.append("標點未逐字（去標點後仍相鄰）：%s[%d]「%s」" % (key[0], key[1], q[:26]))

    # 硬規則 8：命中理由宜指名正文／注文
    for key in sorted(live):
        row = live[key]
        if not _list_field(row, "domains"):
            continue
        if not re.search(r"正文|注文|酈注|《水經》", str(row.get("reason", ""))):
            warns.append("reason 未指名正文／注文：%s[%d]" % key)

    # 統計與 B 類
    stats = {"total": len(live), "hit": 0, "empty": 0}
    dom_count = {d: 0 for d in spec["domains"]}
    mode_count = {m: 0 for m in spec["modes"]}
    for row in live.values():
        doms = _list_field(row, "domains")
        stats["hit" if doms else "empty"] += 1
        for d in doms:
            if d in dom_count:
                dom_count[d] += 1
        for m in _list_field(row, "modes"):
            if m in mode_count:
                mode_count[m] += 1

    print("批次 %d／%d，段 %d" % (len(selected), len(known), len(live)))
    if live:
        print("  命中 %d（%.1f%%）／判空 %d"
              % (stats["hit"], 100.0 * stats["hit"] / len(live), stats["empty"]))
        print("  領域：" + "／".join("%s %d" % (d, dom_count[d]) for d in spec["domains"]))
        print("  mode：" + "／".join("%s %d" % (m, mode_count[m]) for m in spec["modes"] if mode_count[m]))

    for w in warns[:40]:
        print("  WARN " + w)
    if len(warns) > 40:
        print("  WARN …另有 %d 則" % (len(warns) - 40))
    for f in fails:
        print("  FAIL " + f)
    print("A 類 FAIL %d／WARN %d" % (len(fails), len(warns)))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="水經注標註驗收（A 類硬條件＋B 類 WARN）")
    ap.add_argument("batches", nargs="*", help="只檢查指定批次，如 b01 b19")
    ap.add_argument("--out-dir", dest="out_dir")
    ap.add_argument("--check-spec", action="store_true", help="只跑 SPEC 自檢")
    args = ap.parse_args(argv)

    if args.check_spec:
        return check_spec()

    wanted = set()
    for b in args.batches:
        if not BATCH_RE.match(b):
            print("批次名不合法：%s" % b)
            return 2
        wanted.add(b)
    return run(resolve_out_dir(args.out_dir), wanted)


if __name__ == "__main__":
    raise SystemExit(main())
