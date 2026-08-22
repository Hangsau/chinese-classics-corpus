"""戰國策段落標註驗收器：A 類硬條件、B 類數量提示與 SPEC 自檢。

錨點、章名、段號、逐字引句、領域 id、mode id、A 類分組及 B 類帶寬全都在執行時
從同目錄 SPEC.md 解析；本檔不維護第二份事實清單。SPEC 改字後，驗收行為會隨之改變。

反向驗證紀錄（2026-08-22，Python 3.12）：
  - 由 SPEC 與 65 個批次合成 1034 段 perfect 回收，完整執行為 0 個 A 類 FAIL。
  - 單一故障注入逐項命中：刪 row→A1；判空錨點改命中→A3；命中錨點清空→A4；
    禁填格注入→A5；敘事套語注入禁格→A6；群體污名兩側不再判開→A7；
    命中理由只引注文而未指名注家→A11。共同錨點造成的預期重疊另以完整條款集核對，
    沒有出現不相關的 A 類 FAIL。

用法：
  PYTHONIOENCODING=utf-8 python delegation/zhanguoce/accept.py --check-spec
  PYTHONIOENCODING=utf-8 python delegation/zhanguoce/accept.py [b01 b27 ...]
  PYTHONIOENCODING=utf-8 python delegation/zhanguoce/accept.py --out-dir <dir>
"""

import argparse
import glob
import json
import os
import re
import sys


BASE = os.path.dirname(os.path.abspath(__file__))
BATCH_RE = re.compile(r"^b\d{2}$")
INLINE_KEY_RE = re.compile(r"`([^`]+)`\[(\d+)\]")


# ---------------------------------------------------------------------------
# 批次檔


def read_batches():
    """讀取 bNN.md，保留夾注原文，並回報章標頭／段序／批摘要的不一致。"""
    paras = {}
    chapter_len = {}
    batch_chapters = {}
    problems = []
    paths = sorted(glob.glob(os.path.join(BASE, "b[0-9][0-9].md")))

    for path in paths:
        batch = os.path.basename(path)[:3]
        batch_chapters[batch] = []
        actual_indexes = {}
        chapter = None
        summary = None

        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                m = re.match(r"^> 本批\s*(\d+)\s*段，含\s*(\d+)\s*章。", line)
                if m:
                    summary = (int(m.group(1)), int(m.group(2)))
                    continue

                # 章名可含 [n]；只讓全形括號中的「N 段」界定標頭尾端。
                m = re.match(r"^## (.+)（(\d+) 段）\s*$", line)
                if m:
                    chapter = m.group(1)
                    declared = int(m.group(2))
                    if chapter in chapter_len:
                        old_batch = chapter_len[chapter][0]
                        problems.append(
                            "%s:%d 章名重複：%s（先前在 %s）"
                            % (batch, lineno, chapter, old_batch)
                        )
                    else:
                        chapter_len[chapter] = (batch, declared)
                    batch_chapters[batch].append(chapter)
                    actual_indexes.setdefault(chapter, [])
                    continue

                m = re.match(r"^\[(\d+)\] (.*)$", line)
                if not m:
                    continue
                if chapter is None:
                    problems.append("%s:%d 段落出現在第一個章標頭之前" % (batch, lineno))
                    continue
                idx = int(m.group(1))
                key = (chapter, idx)
                if key in paras:
                    problems.append("%s:%d 段號重複：%s[%d]" % (batch, lineno, chapter, idx))
                else:
                    # 不移除 〈…〉，也不做任何文字正規化。
                    paras[key] = (batch, m.group(2).rstrip("\r\n"))
                actual_indexes[chapter].append(idx)

        for ch in batch_chapters[batch]:
            declared = chapter_len.get(ch, (batch, 0))[1]
            got = actual_indexes.get(ch, [])
            if len(got) != declared:
                problems.append(
                    "%s %s 標頭寫 %d 段，實際 %d 段"
                    % (batch, ch, declared, len(got))
                )
            if sorted(got) != list(range(1, declared + 1)):
                problems.append(
                    "%s %s 段序應為 1–%d，實際 %s"
                    % (batch, ch, declared, sorted(got))
                )

        real_paras = sum(len(actual_indexes.get(ch, [])) for ch in batch_chapters[batch])
        if summary is None:
            problems.append("%s 找不到『本批 N 段，含 N 章』摘要" % batch)
        else:
            if summary[0] != real_paras:
                problems.append(
                    "%s 批摘要寫 %d 段，實際 %d 段" % (batch, summary[0], real_paras)
                )
            if summary[1] != len(batch_chapters[batch]):
                problems.append(
                    "%s 批摘要寫 %d 章，實際 %d 章"
                    % (batch, summary[1], len(batch_chapters[batch]))
                )

    return paras, chapter_len, batch_chapters, problems


# ---------------------------------------------------------------------------
# SPEC 解析


def _sections(spec):
    sections = {}
    for part in re.split(r"^## ", spec, flags=re.M):
        head, sep, _rest = part.partition("\n")
        if sep:
            sections[head.strip()] = part
    return sections


def _table_cells(line):
    line = line.strip()
    if not (line.startswith("|") and line.endswith("|")):
        return None
    return [cell.strip() for cell in line[1:-1].split("|")]


def _clean_md(text):
    return re.sub(r"\s+", " ", text.replace("**", "")).strip()


def _a_clauses(section):
    apart = section.split("### B 類", 1)[0]
    if "### A 類" in apart:
        apart = apart.split("### A 類", 1)[1]
    out = {}
    pattern = re.compile(r"^\s*(\d+)\.\s*(.*?)(?=^\s*\d+\.\s|\Z)", re.M | re.S)
    for match in pattern.finditer(apart):
        out[int(match.group(1))] = match.group(2).strip()
    return out


def _inline_keys(text):
    return [(ch, int(idx)) for ch, idx in INLINE_KEY_RE.findall(text)]


def _domain_tokens(text, domains):
    return [tok for tok in re.findall(r"[IVX]+", text) if tok in domains]


def anchor_quote_text(cell):
    """表格最外層「」是引句欄的引用框；框內文字（含其標點）才須逐字存在。"""
    if len(cell) >= 2 and cell.startswith("「") and cell.endswith("」"):
        return cell[1:-1]
    return cell


def _parse_split_rule(number, clause, domains):
    clean = _clean_md(clause)
    rule = {"number": number, "raw": clause}

    # A7/A9：某子表全判空，另一個由條文點名的段命中特定格。
    m = re.search(
        r"(.+?)表的\s*(\d+)\s*段判空.*?`([^`]+)`\[(\d+)\].*?命中\s*([IVX]+)",
        clean,
    )
    if m:
        rule.update(
            {
                "kind": "table_vs_hit",
                "empty_group": m.group(1).strip(),
                "empty_count": int(m.group(2)),
                "hit_key": (m.group(3), int(m.group(4))),
                "hit_domain": m.group(5) if m.group(5) in domains else None,
            }
        )
        return rule

    # A8：條文直接列出判空側與命中側；章名只能由反引號界定。
    m = re.search(r"(.+?)必須判開：(.*?)判空，(.*?)命中", clean)
    if m:
        rule.update(
            {
                "kind": "listed_sides",
                "label": m.group(1).strip(),
                "empty_keys": _inline_keys(m.group(2)),
                "hit_keys": _inline_keys(m.group(3)),
            }
        )
        return rule

    rule["kind"] = "unparsed"
    return rule


def _parse_b_expectations(text):
    exp = {"raw": text, "domain_caps": []}

    m = re.search(r"全書判空預期\s*(\d+)[–-](\d+)%", text)
    if m:
        exp["empty_rate"] = (int(m.group(1)), int(m.group(2)))

    m = re.search(r"遊說辭密集的批（([^）]+)）判空率預期低於全書均值", text)
    if m:
        exp["dense_batches"] = re.findall(r"b\d{2}", m.group(1))

    m = re.search(r"`([^`]+)` 預期為最大 mode，≥\s*(\d+)\s*段", text)
    if m:
        exp["largest_mode"] = (m.group(1), int(m.group(2)))

    m = re.search(
        r"命中領域預期\s*(\d+)[–-](\d+)\s*格；\s*([IVX]+)\s*預期為最大領域，\s*([IVX]+)\s*次之",
        text,
    )
    if m:
        exp["domain_spread"] = (int(m.group(1)), int(m.group(2)))
        exp["domain_rank"] = (m.group(3), m.group(4))

    for dom, cap in re.findall(
        r"([IVX]+)(?:\s*全書)?\s*預期\s*≤\s*(\d+)\s*段", text
    ):
        exp["domain_caps"].append((dom, int(cap)))

    m = re.search(r"命中由注文成立的段預期\s*(\d+)[–-](\d+)\s*段", text)
    if m:
        exp["note_hits"] = (int(m.group(1)), int(m.group(2)))
    return exp


def parse_spec():
    """從 SPEC.md 現場解析所有驗收事實；不在 Python 另抄錨點。"""
    spec_path = os.path.join(BASE, "SPEC.md")
    with open(spec_path, encoding="utf-8") as fh:
        spec = fh.read()
    secs = _sections(spec)
    result = {
        "spec": spec,
        "sections": secs,
        "book": {},
        "domains": [],
        "modes": [],
        "empty_ch": [],
        "empty": [],
        "hit": [],
        "no_xii": [],
        "a_clauses": {},
        "declared": {},
        "split_rules": {},
        "b": {},
    }

    # 合法 id 本身也由 SPEC 的兩張定義表解析。
    for head, body in secs.items():
        if head.startswith("13 個領域"):
            for line in body.splitlines():
                cells = _table_cells(line)
                if cells and len(cells) >= 3 and re.fullmatch(r"[IVX]+", cells[0]):
                    result["domains"].append(cells[0])
        elif head.startswith("8 個 discourse_mode"):
            for line in body.splitlines():
                cells = _table_cells(line)
                if not cells or len(cells) < 3:
                    continue
                mode = cells[0].strip("`")
                if re.fullmatch(r"[a-z_]+", mode) and mode != "id":
                    result["modes"].append(mode)

    domains = set(result["domains"])

    for head, body in secs.items():
        if head.startswith("這部書是什麼"):
            m = re.search(r"本庫切成\s*\*\*(\d+) 批、(\d+) 章、(\d+) 段\*\*", body)
            if m:
                result["book"] = {
                    "batches": int(m.group(1)),
                    "chapters": int(m.group(2)),
                    "paras": int(m.group(3)),
                }

        elif head.startswith("必須整章判空的章"):
            for line in body.splitlines():
                cells = _table_cells(line)
                if not cells or len(cells) != 4 or not re.fullmatch(r"b\d{2}", cells[1]):
                    continue
                try:
                    count = int(cells[2])
                except ValueError:
                    continue
                mm = re.search(r"`modes`\s*含\s*`([^`]+)`", cells[3])
                result["empty_ch"].append(
                    {
                        "chapter": cells[0],
                        "batch": cells[1],
                        "count": count,
                        "reason": cells[3],
                        "mode": mm.group(1) if mm else None,
                    }
                )

        elif head.startswith("必須判空的錨點"):
            group = None
            for line in body.splitlines():
                if line.startswith("### "):
                    # A 類條文以子表簡稱引用，去掉標題尾端的說明性括號。
                    group = re.sub(r"（[^）]*）\s*$", "", line[4:].strip())
                    continue
                cells = _table_cells(line)
                if not cells or len(cells) != 4:
                    continue
                m = re.fullmatch(r"\[(\d+)\]", cells[1])
                if not (m and re.fullmatch(r"b\d{2}", cells[2])):
                    continue
                result["empty"].append(
                    {
                        "chapter": cells[0],
                        "index": int(m.group(1)),
                        "batch": cells[2],
                        "quote": cells[3],
                        "group": group,
                    }
                )

        elif head.startswith("必須命中的錨點"):
            for line in body.splitlines():
                cells = _table_cells(line)
                if not cells or len(cells) != 5:
                    continue
                m = re.fullmatch(r"\[(\d+)\]", cells[1])
                if not (m and re.fullmatch(r"b\d{2}", cells[2])):
                    continue
                result["hit"].append(
                    {
                        "chapter": cells[0],
                        "index": int(m.group(1)),
                        "batch": cells[2],
                        "quote": cells[3],
                        "required_cell": cells[4],
                        "required": _domain_tokens(cells[4], domains),
                    }
                )

        elif head.startswith("一格都不得填 XII"):
            for m in re.finditer(r"`([^`]+)`\[(\d+)\](?:（([^）]*)）)?", body):
                note = m.group(3) or ""
                forbidden = _domain_tokens(head + " " + note, domains)
                result["no_xii"].append(
                    {
                        "chapter": m.group(1),
                        "index": int(m.group(2)),
                        "forbidden": forbidden,
                        "note": note,
                    }
                )

        elif head.startswith("驗收條件"):
            clauses = _a_clauses(body)
            result["a_clauses"] = clauses
            if 3 in clauses:
                m = re.search(r"「必須判空」表的\s*(\d+)\s*段", clauses[3])
                if m:
                    result["declared"]["empty_distinct"] = int(m.group(1))
            if 4 in clauses:
                m = re.search(r"「必須命中」表的\s*(\d+)\s*段", clauses[4])
                if m:
                    result["declared"]["hit_distinct"] = int(m.group(1))
            if 2 in clauses:
                clean = _clean_md(clauses[2])
                m = re.search(
                    r"`([^`]+)`\s*(\d+)\s*段全部為\s*`\[\]`\s*且\s*`modes`\s*含\s*`([^`]+)`",
                    clean,
                )
                if m:
                    result["a2"] = (m.group(1), int(m.group(2)), m.group(3))
            if 6 in clauses:
                clean = _clean_md(clauses[6])
                m = re.search(r"(.+?)表的\s*(\d+)\s*段一律不含\s*([IVX]+)", clean)
                if m:
                    result["a6"] = {
                        "group": m.group(1).strip(),
                        "count": int(m.group(2)),
                        "forbidden": m.group(3) if m.group(3) in domains else None,
                    }
            for number in (7, 8, 9):
                if number in clauses:
                    result["split_rules"][number] = _parse_split_rule(
                        number, clauses[number], domains
                    )
            if 10 in clauses:
                result["zero_modes"] = re.findall(
                    r"`([a-z_]+)`\s*全書\s*0\s*段", clauses[10]
                )
            if 11 in clauses:
                m = re.search(r"注家名（([^）]+)）", clauses[11])
                if m:
                    result["commentators"] = [x.strip() for x in m.group(1).split("／")]

            if "### B 類" in body:
                btext = body.split("### B 類", 1)[1]
                result["b"] = _parse_b_expectations(btext)

    return result


def empty_groups(spec):
    groups = {}
    for anchor in spec["empty"]:
        groups.setdefault(anchor["group"], []).append(anchor)
    return groups


def empty_anchor_map(spec):
    out = {}
    for anchor in spec["empty"]:
        key = (anchor["chapter"], anchor["index"])
        out.setdefault(key, []).append(anchor)
    return out


def hit_anchor_map(spec):
    return {(a["chapter"], a["index"]): a for a in spec["hit"]}


# ---------------------------------------------------------------------------
# SPEC 自檢


def check_spec():
    paras, chapter_len, batch_chapters, source_bad = read_batches()
    spec = parse_spec()
    bad = ["S0 批次檔：" + item for item in source_bad]
    empty_map = empty_anchor_map(spec)
    hit_map = hit_anchor_map(spec)
    groups = empty_groups(spec)

    print(
        "批次檔：%d 批 %d 章 %d 段"
        % (len(batch_chapters), len(chapter_len), len(paras))
    )
    print(
        "SPEC 解析：整章判空 %d 章；逐段判空 %d 列／%d distinct 段／%d 子表；"
        "必須命中 %d 列／%d distinct 段；禁填清單 %d 段"
        % (
            len(spec["empty_ch"]),
            len(spec["empty"]),
            len(empty_map),
            len(groups),
            len(spec["hit"]),
            len(hit_map),
            len(spec["no_xii"]),
        )
    )

    # S1：書級宣告與批次實況。
    book = spec["book"]
    if not book:
        bad.append("S1 無法解析『這部書是什麼』的批／章／段合計")
    else:
        for label, got, key in (
            ("批", len(batch_chapters), "batches"),
            ("章", len(chapter_len), "chapters"),
            ("段", len(paras), "paras"),
        ):
            if got != book[key]:
                bad.append("S1 批次檔 %d %s，SPEC 宣告 %d" % (got, label, book[key]))

    if len(spec["domains"]) != len(set(spec["domains"])) or len(spec["domains"]) != 13:
        bad.append("S1 領域表應解析 13 個 distinct id，實得 %s" % spec["domains"])
    if len(spec["modes"]) != len(set(spec["modes"])) or len(spec["modes"]) != 8:
        bad.append("S1 mode 表應解析 8 個 distinct id，實得 %s" % spec["modes"])
    if set(spec["a_clauses"]) != set(range(1, 12)):
        bad.append("S1 A 類應解析 1–11，實得 %s" % sorted(spec["a_clauses"]))

    # S2：A3/A4 的宣告數比 distinct key，不拿表列數誤判刻意重複列。
    declared_empty = spec["declared"].get("empty_distinct")
    declared_hit = spec["declared"].get("hit_distinct")
    if declared_empty is None:
        bad.append("S2 無法從 A3 解析判空 distinct 段數")
    elif len(empty_map) != declared_empty:
        bad.append(
            "S2 判空表 %d distinct 段，A3 宣告 %d" % (len(empty_map), declared_empty)
        )
    if declared_hit is None:
        bad.append("S2 無法從 A4 解析命中 distinct 段數")
    elif len(hit_map) != declared_hit:
        bad.append(
            "S2 命中表 %d distinct 段，A4 宣告 %d" % (len(hit_map), declared_hit)
        )

    # S3：整章判空表。
    for item in spec["empty_ch"]:
        ch, batch, count = item["chapter"], item["batch"], item["count"]
        if ch not in chapter_len:
            bad.append("S3 整章判空章名不存在：%s" % ch)
            continue
        real_batch, real_count = chapter_len[ch]
        if batch != real_batch:
            bad.append("S3 %s 批次 SPEC=%s，實際=%s" % (ch, batch, real_batch))
        if count != real_count:
            bad.append("S3 %s 段數 SPEC=%d，實際=%d" % (ch, count, real_count))
        if item["mode"] not in spec["modes"]:
            bad.append("S3 %s 的 mode 無法由理由欄解析或不合法：%s" % (ch, item["mode"]))

    a2 = spec.get("a2")
    if not a2:
        bad.append("S3 無法解析 A2 的章／段數／mode")
    elif not any(
        (x["chapter"], x["count"], x["mode"]) == a2 for x in spec["empty_ch"]
    ):
        bad.append("S3 A2 與整章判空表不一致：%s" % (a2,))

    # S4/S5：所有逐段錨點的章、批、段與逐字引句。
    for label, anchors in (("判空", spec["empty"]), ("命中", spec["hit"])):
        for anchor in anchors:
            ch = anchor["chapter"]
            idx = anchor["index"]
            batch = anchor["batch"]
            key = (ch, idx)
            if ch not in chapter_len:
                bad.append("S4 %s錨點章名不存在：%s[%d]" % (label, ch, idx))
                continue
            real_batch, count = chapter_len[ch]
            if batch != real_batch:
                bad.append(
                    "S4 %s[%d] 批次 SPEC=%s，實際=%s" % (ch, idx, batch, real_batch)
                )
            if not 1 <= idx <= count or key not in paras:
                bad.append("S4 %s錨點段不存在：%s[%d]" % (label, ch, idx))
                continue
            quote = anchor_quote_text(anchor["quote"])
            if not quote or quote not in paras[key][1]:
                bad.append("S5 逐字引句不在原文：%s[%d] %s" % (ch, idx, quote))
            if label == "命中":
                if not anchor["required"]:
                    bad.append(
                        "S5 命中錨點『必含』解不出合法領域：%s[%d] %s"
                        % (ch, idx, anchor["required_cell"])
                    )

    overlap = sorted(set(empty_map) & set(hit_map))
    for ch, idx in overlap:
        bad.append("S6 判空集合與命中集合相交：%s[%d]" % (ch, idx))

    # S7：禁填清單以反引號界定章名，並且每段存在。
    for item in spec["no_xii"]:
        key = (item["chapter"], item["index"])
        if key not in paras:
            bad.append("S7 禁填清單段不存在：%s[%d]" % key)
        if not item["forbidden"]:
            bad.append("S7 禁填清單解不出領域：%s[%d]" % key)
        for dom in item["forbidden"]:
            if dom not in spec["domains"]:
                bad.append("S7 禁填清單有非法領域：%s[%d] %s" % (*key, dom))

    # S8：A6 與 A7–A9 的兩側必須能從 SPEC 對回錨點表。
    a6 = spec.get("a6")
    if not a6 or a6["group"] not in groups or a6["forbidden"] not in spec["domains"]:
        bad.append("S8 A6 無法完整解析或找不到對應子表：%s" % a6)
    elif len({(x["chapter"], x["index"]) for x in groups[a6["group"]]}) != a6["count"]:
        bad.append("S8 A6 子表 distinct 段數與條文不一致")

    for number in (7, 8, 9):
        rule = spec["split_rules"].get(number)
        if not rule or rule.get("kind") == "unparsed":
            bad.append("S8 A%d 判開條文無法解析" % number)
            continue
        if rule["kind"] == "table_vs_hit":
            group = rule["empty_group"]
            if group not in groups:
                bad.append("S8 A%d 找不到判空子表：%s" % (number, group))
            elif len({(x["chapter"], x["index"]) for x in groups[group]}) != rule["empty_count"]:
                bad.append("S8 A%d 子表 distinct 段數與條文不一致" % number)
            hit = hit_map.get(rule["hit_key"])
            if hit is None:
                bad.append("S8 A%d 命中側不在命中表：%s" % (number, rule["hit_key"]))
            elif rule["hit_domain"] not in hit["required"]:
                bad.append("S8 A%d 命中側領域與命中表不一致" % number)
        else:
            for key in rule["empty_keys"]:
                if key not in empty_map:
                    bad.append("S8 A%d 判空側不在判空表：%s" % (number, key))
            for key in rule["hit_keys"]:
                if key not in hit_map:
                    bad.append("S8 A%d 命中側不在命中表：%s" % (number, key))
            if not rule["empty_keys"] or not rule["hit_keys"]:
                bad.append("S8 A%d 至少一側為空" % number)

    zero_modes = spec.get("zero_modes", [])
    if not zero_modes or any(mode not in spec["modes"] for mode in zero_modes):
        bad.append("S8 A10 的零段 mode 無法解析或不合法：%s" % zero_modes)
    commentators = spec.get("commentators", [])
    if not commentators:
        bad.append("S8 A11 解不出注家名")

    b = spec["b"]
    required_b = {"empty_rate", "dense_batches", "largest_mode", "domain_spread", "domain_rank", "note_hits"}
    missing_b = sorted(required_b - set(b))
    cap_mentions = re.findall(
        r"([IVX]+)(?:\s*全書)?\s*預期\s*≤\s*\d+\s*段", b.get("raw", "")
    )
    parsed_caps = [domain for domain, _cap in b.get("domain_caps", [])]
    if missing_b or parsed_caps != cap_mentions:
        bad.append("S9 B 類帶寬解析不完整：缺 %s；caps=%s" % (missing_b, b.get("domain_caps")))
    if b.get("largest_mode", (None,))[0] not in spec["modes"]:
        bad.append("S9 B 類最大 mode 不是 mode 表合法 id：%s" % (b.get("largest_mode"),))
    if any(batch not in batch_chapters for batch in b.get("dense_batches", [])):
        bad.append("S9 B 類遊說辭密集批含不存在的批次：%s" % b.get("dense_batches"))
    rank = b.get("domain_rank", ())
    if any(domain not in spec["domains"] for domain in rank + tuple(parsed_caps)):
        bad.append("S9 B 類含不合法領域 id：rank=%s caps=%s" % (rank, parsed_caps))

    print("--- SPEC 自檢 FAIL：%d ---" % len(bad))
    for item in bad:
        print(item)
    return 0 if not bad else 1


# ---------------------------------------------------------------------------
# 回收載入與 A 類


def resolve_out_dir(value):
    if os.path.isabs(value):
        return os.path.normpath(value)
    cwd_path = os.path.abspath(value)
    base_path = os.path.abspath(os.path.join(BASE, value))
    if os.path.exists(cwd_path):
        return cwd_path
    if os.path.exists(base_path):
        return base_path
    # 一般 CLI 習慣以目前工作目錄為基準；仍保留 _selftest/perfect 這類範本相容性。
    if value.startswith("_selftest" + os.sep) or value == "_selftest":
        return base_path
    return cwd_path


def load_out(out_dir, wanted, known_batches):
    """保留 raw rows 供 A1 雙向檢查；只有合法 key 進入 rows 供其餘條款使用。"""
    rows = {}
    raw_by_batch = {}
    batches = []
    duplicate_keys = []
    errors = []

    wanted_clean = []
    for value in wanted:
        if not BATCH_RE.fullmatch(value):
            errors.append("A1 非法批次參數：%s（應為 bNN）" % value)
        elif value not in wanted_clean:
            wanted_clean.append(value)

    if wanted_clean:
        paths = []
        for batch in wanted_clean:
            path = os.path.join(out_dir, batch + ".json")
            if os.path.isfile(path):
                paths.append(path)
            else:
                errors.append("A1 指定批次缺少輸出檔：%s" % batch)
    else:
        paths = sorted(glob.glob(os.path.join(out_dir, "b[0-9][0-9].json")))

    for path in paths:
        batch = os.path.basename(path)[:3]
        batches.append(batch)
        raw_by_batch[batch] = []
        if batch not in known_batches:
            errors.append("A1 輸出檔批次不存在於發包檔：%s" % batch)
        try:
            with open(path, "rb") as fh:
                payload = fh.read()
            if payload.startswith(b"\xef\xbb\xbf"):
                errors.append("A1 %s 不是無 BOM UTF-8" % batch)
                payload = payload[3:]
            if b"\r" in payload:
                errors.append("A1 %s 含 CR/CRLF，輸出必須使用 LF" % batch)
            data = json.loads(payload.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append("A1 %s 無法讀取 JSON：%s" % (batch, exc))
            continue
        if not isinstance(data, dict):
            errors.append("A1 %s JSON 頂層必須是 object" % batch)
            continue
        if data.get("batch") != batch + ".md":
            errors.append(
                "A1 %s 頂層 batch 應為 %s.md，實得 %r"
                % (batch, batch, data.get("batch"))
            )
        raw = data.get("rows")
        if not isinstance(raw, list):
            errors.append("A1 %s rows 必須是 list" % batch)
            continue
        raw_by_batch[batch] = raw
        for pos, item in enumerate(raw, 1):
            if not isinstance(item, dict):
                errors.append("A1 %s rows[%d] 必須是 object" % (batch, pos - 1))
                continue
            ch = item.get("chapter")
            idx = item.get("para_index")
            if not isinstance(ch, str) or type(idx) is not int:
                continue
            key = (ch, idx)
            row = dict(item)
            row["_batch"] = batch
            if key in rows:
                duplicate_keys.append(key)
            else:
                rows[key] = row

    if not paths and not errors:
        errors.append("A1 輸出目錄沒有任何 bNN.json：%s" % out_dir)
    return rows, raw_by_batch, batches, duplicate_keys, errors


def _list_field(row, name):
    value = row.get(name, [])
    return value if isinstance(value, list) else []


def a1_shape(rows, raw_by_batch, batches, duplicate_keys, load_errors, chapter_len, batch_chapters, spec):
    """A1：rows 雙向覆蓋、欄位型別、章段 key、reason、值域與多標上限。"""
    fails = list(load_errors)
    domains = set(spec["domains"])
    modes = set(spec["modes"])

    for ch, idx in duplicate_keys:
        fails.append("A1 重複段：%s[%d]" % (ch, idx))

    for batch in batches:
        raw = raw_by_batch.get(batch, [])
        chapters = batch_chapters.get(batch, [])
        expected = sum(chapter_len[ch][1] for ch in chapters)
        if len(raw) != expected:
            fails.append("A1 %s rows %d ≠ 該批段數 %d" % (batch, len(raw), expected))
        allowed_chapters = set(chapters)

        seen = {}
        for pos, item in enumerate(raw, 1):
            if not isinstance(item, dict):
                continue
            ch = item.get("chapter")
            idx = item.get("para_index")
            source_label = "%s rows[%d]" % (batch, pos - 1)
            row_label = (
                "%s[%d]" % (ch, idx)
                if isinstance(ch, str) and type(idx) is int
                else source_label
            )

            if not isinstance(ch, str):
                fails.append("A1 %s chapter 必須是字串，實得 %r" % (source_label, ch))
            elif ch not in allowed_chapters:
                fails.append("A1 %s 出現非該批章名" % row_label)

            if type(idx) is not int:
                fails.append("A1 %s para_index 必須是整數，實得 %r" % (source_label, idx))
            elif isinstance(ch, str) and ch in allowed_chapters:
                seen.setdefault(ch, []).append(idx)
                count = chapter_len[ch][1]
                if not 1 <= idx <= count:
                    fails.append("A1 %s para_index 超出該章 1–%d" % (row_label, count))

            reason = item.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                fails.append("A1 %s reason 空白或不是字串" % row_label)

            row_domains = item.get("domains")
            if not isinstance(row_domains, list):
                fails.append("A1 %s domains 必須是 list" % row_label)
            else:
                invalid = [
                    value
                    for value in row_domains
                    if not isinstance(value, str) or value not in domains
                ]
                if invalid:
                    fails.append("A1 %s 非法 domain：%s" % (row_label, invalid))
                if len(row_domains) > 3:
                    fails.append("A1 %s domains 最多 3 個，實得 %d" % (row_label, len(row_domains)))
                if len(row_domains) != len(set(map(repr, row_domains))):
                    fails.append("A1 %s domains 有重複值：%s" % (row_label, row_domains))

            row_modes = item.get("modes")
            if not isinstance(row_modes, list):
                fails.append("A1 %s modes 必須是 list" % row_label)
            else:
                invalid = [
                    value
                    for value in row_modes
                    if not isinstance(value, str) or value not in modes
                ]
                if invalid:
                    fails.append("A1 %s 非法 mode：%s" % (row_label, invalid))
                if len(row_modes) > 2:
                    fails.append("A1 %s modes 最多 2 個，實得 %d" % (row_label, len(row_modes)))
                if len(row_modes) != len(set(map(repr, row_modes))):
                    fails.append("A1 %s modes 有重複值：%s" % (row_label, row_modes))

        for ch in chapters:
            expected_indexes = list(range(1, chapter_len[ch][1] + 1))
            got = sorted(seen.get(ch, []))
            if got != expected_indexes:
                fails.append(
                    "A1 %s para_index 應為 1–%d 各一次，實得 %s"
                    % (ch, chapter_len[ch][1], got)
                )
    return fails


def _is_selected(key, batches, paras):
    return key in paras and paras[key][0] in batches


def a2_empty_chapters(rows, batches, spec, paras):
    """A2：整章判空，且每段含表／條文宣告的 mode。"""
    fails = []
    for item in spec["empty_ch"]:
        ch = item["chapter"]
        if item["batch"] not in batches:
            continue
        for idx in range(1, item["count"] + 1):
            row = rows.get((ch, idx))
            if row is None:
                fails.append("A2 缺段 %s[%d]" % (ch, idx))
                continue
            if _list_field(row, "domains"):
                fails.append("A2 整章判空章被填 %s[%d] → %s" % (ch, idx, row.get("domains")))
            if item["mode"] not in _list_field(row, "modes"):
                fails.append(
                    "A2 %s[%d] modes 未含 %s → %s"
                    % (ch, idx, item["mode"], row.get("modes"))
                )
    return fails


def a3_empty_anchors(rows, batches, spec, paras):
    """A3：判空錨點以 distinct 段檢查；訊息保留所有所屬子表。"""
    fails = []
    for key, anchors in empty_anchor_map(spec).items():
        if not _is_selected(key, batches, paras):
            continue
        ch, idx = key
        labels = "／".join(dict.fromkeys(a["group"] for a in anchors))
        row = rows.get(key)
        if row is None:
            fails.append("A3 缺段 %s[%d]（%s）" % (ch, idx, labels))
        elif _list_field(row, "domains"):
            fails.append(
                "A3 必須判空錨點被填 %s[%d]（%s）→ %s"
                % (ch, idx, labels, row.get("domains"))
            )
    return fails


def a4_hit_anchors(rows, batches, spec, paras):
    """A4：必含欄為「X 或 Y」時至少命中其中一格。"""
    fails = []
    for anchor in spec["hit"]:
        key = (anchor["chapter"], anchor["index"])
        if not _is_selected(key, batches, paras):
            continue
        row = rows.get(key)
        if row is None:
            fails.append("A4 缺段 %s[%d]" % key)
            continue
        got = _list_field(row, "domains")
        if not any(value in got for value in anchor["required"]):
            fails.append(
                "A4 必須命中錨點缺格 %s[%d] 需 %s 至少一，實得 %s"
                % (*key, " 或 ".join(anchor["required"]), got)
            )
    return fails


def a5_forbidden_domains(rows, batches, spec, paras):
    """A5：從禁填段落內文解析每段禁用格（含另註的額外禁格）。"""
    fails = []
    for item in spec["no_xii"]:
        key = (item["chapter"], item["index"])
        if not _is_selected(key, batches, paras):
            continue
        row = rows.get(key)
        if row is None:
            fails.append("A5 缺段 %s[%d]" % key)
            continue
        got = _list_field(row, "domains")
        bad = [value for value in item["forbidden"] if value in got]
        if bad:
            fails.append(
                "A5 禁填段落含禁用格 %s[%d] 禁 %s，實得 %s"
                % (*key, "/".join(item["forbidden"]), got)
            )
    return fails


def a6_narrative_formula(rows, batches, spec, paras):
    """A6：條文點名子表的每個 distinct 段不得含指定格。"""
    fails = []
    rule = spec.get("a6")
    if not rule:
        return ["A6 SPEC 條文無法解析"]
    anchors = empty_groups(spec).get(rule["group"], [])
    for key in dict.fromkeys((a["chapter"], a["index"]) for a in anchors):
        if not _is_selected(key, batches, paras):
            continue
        row = rows.get(key)
        if row is None:
            fails.append("A6 缺段 %s[%d]（%s）" % (*key, rule["group"]))
        elif rule["forbidden"] in _list_field(row, "domains"):
            fails.append(
                "A6 %s[%d]（%s）不得含 %s，實得 %s"
                % (*key, rule["group"], rule["forbidden"], row.get("domains"))
            )
    return fails


def _split_table_vs_hit(number, rows, batches, spec, paras):
    fails = []
    rule = spec["split_rules"].get(number)
    if not rule or rule.get("kind") != "table_vs_hit":
        return ["A%d SPEC 判開條文無法解析" % number]

    empty_keys = list(
        dict.fromkeys(
            (a["chapter"], a["index"])
            for a in empty_groups(spec).get(rule["empty_group"], [])
        )
    )
    empty_verdicts = []
    for key in empty_keys:
        if not _is_selected(key, batches, paras):
            continue
        row = rows.get(key)
        if row is None:
            fails.append("A%d 缺段 %s[%d]（%s）" % (number, *key, rule["empty_group"]))
            continue
        hit = bool(_list_field(row, "domains"))
        empty_verdicts.append(hit)
        if hit:
            fails.append(
                "A%d 判空側被填 %s[%d]（%s）→ %s"
                % (number, *key, rule["empty_group"], row.get("domains"))
            )

    hit_key = rule["hit_key"]
    hit_verdict = None
    if _is_selected(hit_key, batches, paras):
        row = rows.get(hit_key)
        if row is None:
            fails.append("A%d 缺段 %s[%d]（命中側）" % (number, *hit_key))
        else:
            got = _list_field(row, "domains")
            hit_verdict = bool(got)
            if rule["hit_domain"] not in got:
                fails.append(
                    "A%d 命中側 %s[%d] 應含 %s，實得 %s"
                    % (number, *hit_key, rule["hit_domain"], got)
                )

    if empty_verdicts and hit_verdict is not None and all(v == hit_verdict for v in empty_verdicts):
        fails.append("A%d 兩側判齊，必須判開" % number)
    return fails


def a7_group_stigma_split(rows, batches, spec, paras):
    """A7：群體污名子表與條文點名的機制句必須判開。"""
    return _split_table_vs_hit(7, rows, batches, spec, paras)


def a8_allegory_split(rows, batches, spec, paras):
    """A8：條文逐一列出的寓言判空側與命中側必須相反。"""
    fails = []
    rule = spec["split_rules"].get(8)
    if not rule or rule.get("kind") != "listed_sides":
        return ["A8 SPEC 判開條文無法解析"]

    verdicts = {"empty": [], "hit": []}
    for side, keys in (("empty", rule["empty_keys"]), ("hit", rule["hit_keys"])):
        for key in keys:
            if not _is_selected(key, batches, paras):
                continue
            row = rows.get(key)
            if row is None:
                fails.append("A8 缺段 %s[%d]（%s側）" % (*key, "判空" if side == "empty" else "命中"))
                continue
            is_hit = bool(_list_field(row, "domains"))
            verdicts[side].append(is_hit)
            if side == "empty" and is_hit:
                fails.append("A8 判空側被填 %s[%d] → %s" % (*key, row.get("domains")))
            if side == "hit" and not is_hit:
                fails.append("A8 命中側被判空 %s[%d]" % key)

    if verdicts["empty"] and verdicts["hit"]:
        all_values = verdicts["empty"] + verdicts["hit"]
        if len(set(all_values)) == 1:
            fails.append("A8 兩側判齊，必須判開")
    return fails


def a9_virtue_split(rows, batches, spec, paras):
    """A9：德目工具化子表與條文點名的德目主張必須判開。"""
    return _split_table_vs_hit(9, rows, batches, spec, paras)


def a10_zero_modes(rows, spec):
    """A10：條文宣告為全書零段的 mode 不得出現。"""
    fails = []
    for mode in spec.get("zero_modes", []):
        found = sorted(key for key, row in rows.items() if mode in _list_field(row, "modes"))
        if found:
            examples = "、".join("%s[%d]" % key for key in found[:5])
            fails.append("A10 %s 應為 0 段，實得 %d：%s" % (mode, len(found), examples))
    return fails


def extract_reason_quotes(reason):
    if not isinstance(reason, str):
        return []
    # 容忍理由中巢狀書名式引號；每個右引號結束一個機械引句。
    return [quote for quote in re.findall(r"「([^」]+)」", reason) if quote]


# 本書的夾注插在句子中間，逐字引句在原文裡會被 〈…〉 切斷；又有 93% 的段落自帶「」
# 對白，引句巢狀時只能改寫成『』。兩者都會讓單純的子字串比對誤報成「引句不在原文」。
_VARIANTS = str.maketrans({"䤈": "醯", "『": "「", "』": "」"})
_ELLIPSIS = re.compile(r"…{2,}|\.{3,}")
_NOTE = re.compile(r"〈[^〈〉]*〉")


def strip_annotations(text):
    prev = None
    while prev != text:
        prev = text
        text = _NOTE.sub("", text)
    return text


def quote_in_text(text, quote):
    """引句對得上原文：容許夾注切斷、節略號分段、異體字與巢狀引號的『』寫法。"""
    bases = (text, strip_annotations(text))
    haystacks = bases + tuple(base.translate(_VARIANTS) for base in bases)
    fragments = [frag for frag in _ELLIPSIS.split(quote) if frag]
    return all(
        any(frag in hay or frag.translate(_VARIANTS) in hay for hay in haystacks)
        for frag in fragments
    )


def annotation_intervals(text):
    """回傳所有配對 〈…〉 區間；任一不成對時保守回傳空集合。"""
    stack = []
    intervals = []
    for pos, char in enumerate(text):
        if char == "〈":
            stack.append(pos)
        elif char == "〉":
            if not stack:
                return []
            start = stack.pop()
            intervals.append((start, pos + 1))
    if stack:
        return []
    return intervals


def _all_occurrences(text, needle):
    if not needle:
        return []
    out = []
    start = 0
    while True:
        pos = text.find(needle, start)
        if pos < 0:
            return out
        out.append((pos, pos + len(needle)))
        start = pos + 1


def quote_only_in_annotations(text, quote, intervals=None):
    if intervals is None:
        intervals = annotation_intervals(text)
    if not intervals:
        return False
    occurrences = _all_occurrences(text, quote)
    if not occurrences:
        return False
    return all(
        any(begin <= pos and end <= finish for begin, finish in intervals)
        for pos, end in occurrences
    )


def note_only_reason_quotes(row, text):
    intervals = annotation_intervals(text)
    return [
        quote
        for quote in extract_reason_quotes(row.get("reason", ""))
        if quote_only_in_annotations(text, quote, intervals)
    ]


def a11_commentary_reasons(rows, spec, paras):
    """A11：注家名→須有原文引句；命中理由只落注文→須指名注家。"""
    fails = []
    commentators = spec.get("commentators", [])
    for key, row in sorted(rows.items()):
        if key not in paras:
            continue
        text = paras[key][1]
        reason = row.get("reason", "")
        quotes = extract_reason_quotes(reason)
        named = [name for name in commentators if name in reason]
        exact = [quote for quote in quotes if quote_in_text(text, quote)]

        if named and not exact:
            fails.append(
                "A11 %s[%d] reason 指名注家 %s，卻沒有任何原文內的「」引句"
                % (*key, "/".join(named))
            )

        if _list_field(row, "domains"):
            note_quotes = note_only_reason_quotes(row, text)
            if note_quotes and not named:
                fails.append(
                    "A11 %s[%d] 命中理由引句只出現在夾注，卻未指名注家：『%s』"
                    % (*key, note_quotes[0][:40])
                )
    return fails


# ---------------------------------------------------------------------------
# WARN 與統計


def hard_rule_7_warnings(rows, paras):
    bad = []
    for key, row in sorted(rows.items()):
        if not _list_field(row, "domains") or key not in paras:
            continue
        text = paras[key][1]
        if not any(
            quote_in_text(text, quote)
            for quote in extract_reason_quotes(row.get("reason", ""))
        ):
            bad.append(key)
    return bad


def compute_stats(rows, spec, paras):
    stats = {
        "total": len(rows),
        "empty": 0,
        "domains": {name: 0 for name in spec["domains"]},
        "modes": {name: 0 for name in spec["modes"]},
        "per_batch": {},
        "note_hits": 0,
    }
    for key, row in rows.items():
        batch = row.get("_batch")
        per = stats["per_batch"].setdefault(batch, {"total": 0, "empty": 0})
        per["total"] += 1
        domains = _list_field(row, "domains")
        modes = _list_field(row, "modes")
        if not domains:
            stats["empty"] += 1
            per["empty"] += 1
        for value in domains:
            if isinstance(value, str) and value in stats["domains"]:
                stats["domains"][value] += 1
        for value in modes:
            if isinstance(value, str) and value in stats["modes"]:
                stats["modes"][value] += 1
        if domains and key in paras and note_only_reason_quotes(row, paras[key][1]):
            stats["note_hits"] += 1
    stats["hit_domain_count"] = sum(value > 0 for value in stats["domains"].values())
    stats["zero_domains"] = [name for name, value in stats["domains"].items() if value == 0]
    return stats


def b_comparisons(spec, stats):
    """回傳 (符合帶寬?, 實測對照文字)；所有結果都只是提示。"""
    exp = spec["b"]
    out = []
    total = stats["total"]
    rate = 100.0 * stats["empty"] / total if total else 0.0

    if "empty_rate" in exp:
        low, high = exp["empty_rate"]
        out.append((low <= rate <= high, "全書判空率 %.1f%%；宣告 %d–%d%%" % (rate, low, high)))

    if exp.get("dense_batches"):
        values = []
        ok = True
        for batch in exp["dense_batches"]:
            item = stats["per_batch"].get(batch, {"total": 0, "empty": 0})
            value = 100.0 * item["empty"] / item["total"] if item["total"] else 0.0
            values.append("%s=%.1f%%" % (batch, value))
            ok = ok and item["total"] > 0 and value < rate
        out.append((ok, "遊說辭密集批判空率 %s；宣告皆低於全書 %.1f%%" % ("、".join(values), rate)))

    if "largest_mode" in exp:
        mode, floor = exp["largest_mode"]
        largest = max(stats["modes"].items(), key=lambda item: item[1]) if stats["modes"] else ("(無)", 0)
        value = stats["modes"].get(mode, 0)
        out.append(
            (
                largest[0] == mode and value >= floor,
                "%s=%d、最大 mode=%s(%d)；宣告 %s 最大且 ≥%d"
                % (mode, value, largest[0], largest[1], mode, floor),
            )
        )

    if "domain_spread" in exp:
        low, high = exp["domain_spread"]
        value = stats["hit_domain_count"]
        out.append((low <= value <= high, "命中領域 %d 格；宣告 %d–%d 格" % (value, low, high)))

    if "domain_rank" in exp:
        first, second = exp["domain_rank"]
        ranked = sorted(stats["domains"].items(), key=lambda item: (-item[1], spec["domains"].index(item[0])))
        actual = ranked[:2]
        ok = len(actual) >= 2 and actual[0][0] == first and actual[1][0] == second
        out.append(
            (
                ok,
                "領域前二 %s；宣告 %s 最大、%s 次之"
                % ("、".join("%s=%d" % item for item in actual), first, second),
            )
        )

    for domain, cap in exp.get("domain_caps", []):
        value = stats["domains"].get(domain, 0)
        out.append((value <= cap, "%s=%d；宣告 ≤%d" % (domain, value, cap)))

    if "note_hits" in exp:
        low, high = exp["note_hits"]
        value = stats["note_hits"]
        out.append((low <= value <= high, "命中由注文成立 %d 段；宣告 %d–%d 段" % (value, low, high)))
    return out


# ---------------------------------------------------------------------------
# 主流程


def run(out_dir, wanted):
    paras, chapter_len, batch_chapters, source_bad = read_batches()
    spec = parse_spec()
    core_ok = (
        spec["empty_ch"]
        and spec["empty"]
        and spec["hit"]
        and len(spec["a_clauses"]) == 11
        and spec["domains"]
        and spec["modes"]
    )
    if not core_ok:
        print("!! SPEC 錨點／A 類／值域未完整解析，請先跑 --check-spec")
        return 2

    known_batches = set(batch_chapters)
    rows, raw_by_batch, batches, duplicates, load_errors = load_out(
        out_dir, wanted, known_batches
    )
    print(
        "回收批次：%s，共 %d 個可定位段 key（來源 %s）"
        % (" ".join(batches) or "(無)", len(rows), os.path.relpath(out_dir, BASE))
    )

    fails = ["A1 批次檔：" + item for item in source_bad]
    fails += a1_shape(
        rows,
        raw_by_batch,
        batches,
        duplicates,
        load_errors,
        chapter_len,
        batch_chapters,
        spec,
    )
    fails += a2_empty_chapters(rows, batches, spec, paras)
    fails += a3_empty_anchors(rows, batches, spec, paras)
    fails += a4_hit_anchors(rows, batches, spec, paras)
    fails += a5_forbidden_domains(rows, batches, spec, paras)
    fails += a6_narrative_formula(rows, batches, spec, paras)
    fails += a7_group_stigma_split(rows, batches, spec, paras)
    fails += a8_allegory_split(rows, batches, spec, paras)
    fails += a9_virtue_split(rows, batches, spec, paras)
    fails += a10_zero_modes(rows, spec)
    fails += a11_commentary_reasons(rows, spec, paras)

    stats = compute_stats(rows, spec, paras)
    empty_rate = 100.0 * stats["empty"] / stats["total"] if stats["total"] else 0.0
    print("判空：%d/%d（%.1f%%）" % (stats["empty"], stats["total"], empty_rate))
    print("modes：" + "  ".join("%s=%d" % (x, stats["modes"][x]) for x in spec["modes"]))
    print("domains：" + "  ".join("%s=%d" % (x, stats["domains"][x]) for x in spec["domains"]))
    print("零命中領域：" + ("、".join(stats["zero_domains"]) or "（無）"))
    print("命中由注文成立：%d 段" % stats["note_hits"])

    rule7 = hard_rule_7_warnings(rows, paras)
    print("--- 硬規則 7 機械版 WARN：%d（不擋收）---" % len(rule7))
    if rule7:
        examples = "、".join("%s[%d]" % key for key in rule7[:5])
        print("WARN 命中段 reason 沒有任何一個「」引句是該段原文子字串；前五例：" + examples)

    full_book = set(batches) == known_batches and len(batches) == len(known_batches)
    comparisons = b_comparisons(spec, stats) if full_book else []
    if not full_book:
        print("（未全批回收，B 類帶寬對照略過）")
    warn_count = sum(not ok for ok, _text in comparisons)
    print("--- B 類 WARN：%d（不擋收）---" % warn_count)
    for ok, text in comparisons:
        print("B %s %s" % ("符合" if ok else "WARN", text))

    selected = set(batches)
    all_anchor_keys = set(empty_anchor_map(spec)) | set(hit_anchor_map(spec))
    skipped = sum(1 for key in all_anchor_keys if paras.get(key, (None,))[0] not in selected)
    skipped += sum(
        item["count"] for item in spec["empty_ch"] if item["batch"] not in selected
    )
    print("跳過（該批未回收）：%d 個錨點段" % skipped)
    print("--- A 類 FAIL：%d ---" % len(fails))
    for item in fails:
        print(item)
    return 0 if not fails else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="戰國策標註驗收（A 類硬條件＋B 類 WARN）")
    parser.add_argument("batches", nargs="*", help="只檢查指定批次，如 b01 b27；預設讀取現有全部")
    parser.add_argument(
        "--check-spec",
        action="store_true",
        help="發包前自檢：只拿 SPEC.md 對 65 個批次檔，不讀 out/",
    )
    parser.add_argument(
        "--out-dir",
        default=os.path.join(BASE, "out"),
        help="回收 JSON 目錄；預設 delegation/zhanguoce/out",
    )
    args = parser.parse_args(argv)
    if args.check_spec:
        return check_spec()
    return run(resolve_out_dir(args.out_dir), args.batches)


if __name__ == "__main__":
    sys.exit(main())
