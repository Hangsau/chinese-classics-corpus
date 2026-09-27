#!/usr/bin/env python3
"""
句讀切分器：把上游「一章＝一段」的巨段切成可標註的段落，寫進覆蓋層
translations/<slug>/segmentation.json。raw/original.txt 一個位元組都不動。

兩條軌：
  --auto      標點軌。在正文（夾注〈〉與引號「」『』之外）的 。！？ 後找候選切點，
              緊跟在後的夾注一律黏回前一句；累積到 --min 字後，遇到下一句以
              論述起頭語（是故／夫／凡／昔…）開頭就切，超過 --max 字則在下一個
              候選點硬切。字數只算正文、不算夾注。
  --starts F  語意軌。F 每行一個「新段落的開頭字串」，依序在段內找第一個出現處切。
              用在條目本身有語意邊界的文本（墨經的定義條、說林的格言串）。

用法：
  python scripts/segment.py mozi --para 經上:1 --starts delegation/mozi/seg-jingshang.txt
  python scripts/segment.py guiguzi --over 600 --auto --min 120 --max 320
  python scripts/segment.py guiguzi --show            # 印出目前覆蓋層切出的段落

覆蓋層記錄每個被切段落的 sha256；原文若變動，corpus_text 會拒絕套用（verify 報錯），
不會讓錨點靜默漂移。已經有 annotations.json 的章，切之前要先撤掉該章的舊標註——
本工具會檢查並拒絕。
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_text import (SEGMENTATION_FILE, body_sha, load_segmentation,  # noqa: E402
                         read_paragraphs, split_paragraphs)

ROOT = Path(__file__).resolve().parent.parent
STOPS = "。！？"
OPEN_QUOTES, CLOSE_QUOTES = "「『", "」』"
# 論述換題的起頭語。單字「故」太常見於論證中段，只在累積已過半時才算。
STRONG_STARTS = ("是故", "故曰", "夫", "凡", "昔", "古者", "古之", "今夫", "若夫", "且夫",
                 "由此觀之", "何以知其然", "所謂", "傳曰", "詩云", "詩曰", "或曰", "或問",
                 "聖人", "天下", "此所謂", "○")
WEAK_STARTS = ("故", "是以", "然則", "今")


def sentence_ends(body: str) -> list[int]:
    """回傳正文句末的切點位置（切在該位置之前），夾注黏在前一句。"""
    ends, note, quote, i, n = [], 0, 0, 0, len(body)
    while i < n:
        c = body[i]
        if c == "〈":
            note += 1
        elif c == "〉":
            note = max(0, note - 1)
        elif note == 0 and c in OPEN_QUOTES:
            quote += 1
        elif note == 0 and c in CLOSE_QUOTES:
            quote = max(0, quote - 1)
            if quote == 0 and i > 0 and body[i - 1] in STOPS:
                ends.append(i + 1)
        elif note == 0 and quote == 0 and c in STOPS:
            ends.append(i + 1)
        i += 1
    out = []
    for e in ends:
        while e < n and body[e] == "〈":          # 夾注黏回前一句
            close = body.find("〉", e)
            if close < 0:
                break
            e = close + 1
        if 0 < e < n and (not out or out[-1] != e):
            out.append(e)
    return out


def main_len(s: str) -> int:
    depth, k = 0, 0
    for c in s:
        if c == "〈":
            depth += 1
        elif c == "〉":
            depth = max(0, depth - 1)
        elif depth == 0 and not c.isspace():
            k += 1
    return k


def auto_cuts(body: str, lo: int, hi: int) -> list[int]:
    cuts, start = [], 0
    for e in sentence_ends(body):
        cur = main_len(body[start:e])
        nxt = body[e:e + 8].lstrip()
        strong = nxt.startswith(STRONG_STARTS)
        weak = nxt.startswith(WEAK_STARTS) and cur >= (lo + hi) // 2
        if cur >= hi or (cur >= lo and (strong or weak)):
            cuts.append(e)
            start = e
    # 尾巴太短就併回前一段
    if cuts and main_len(body[cuts[-1]:]) < lo // 2:
        cuts.pop()
    return cuts


def starts_cuts(body: str, starts: list[str]) -> list[int]:
    cuts, pos = [], 0
    for s in starts:
        k = body.find(s, pos + 1)
        if k < 0:
            sys.exit(f"[error] 在位置 {pos} 之後找不到開頭字串：{s}")
        cuts.append(k)
        pos = k
    return cuts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--para", action="append", default=[], help="章名:原段序，可重複")
    ap.add_argument("--over", type=int, help="自動選取原長（含夾注）超過此字數的段落")
    ap.add_argument("--chapters", help="配合 --over，只在這些章（逗號分隔）裡選")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--min", type=int, default=120)
    ap.add_argument("--max", type=int, default=320)
    ap.add_argument("--starts", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    book = ROOT / "translations" / args.slug
    if args.show:
        seg = load_segmentation(book) or {}
        chs = {o["chapter"] for o in seg.get("overrides", [])}
        for _, ch, idx, t in read_paragraphs(book):
            if ch in chs:
                print(f"{ch}[{idx}] 正文{main_len(t)}字 全長{len(t)}：{t[:36]}…{t[-12:]}")
        return 0

    text = (book / "raw" / "original.txt").read_text(encoding="utf-8")
    source = {(ch, i): t for _, ch, i, t in split_paragraphs(text)}   # 不套覆蓋層的原段
    targets = []
    for p in args.para:
        ch, _, i = p.rpartition(":")
        targets.append((ch, int(i)))
    if args.over:
        only = set(args.chapters.split(",")) if args.chapters else None
        targets += [k for k, t in source.items()
                    if len(t) > args.over and (only is None or k[0] in only)]
    if not targets:
        sys.exit("[error] 沒有選到任何段落（用 --para 或 --over）")
    if bool(args.auto) == bool(args.starts):
        sys.exit("[error] --auto 與 --starts 二擇一")

    ann_p = book / "annotations.json"
    if ann_p.exists():
        tagged = {r["anchor"]["chapter"] for r in json.loads(ann_p.read_text(encoding="utf-8"))}
        clash = sorted({ch for ch, _ in targets} & tagged)
        if clash:
            sys.exit(f"[error] 這些章已有標註，先從 annotations.json 撤掉再切：{clash}")

    seg = load_segmentation(book) or {"overrides": []}
    kept = [o for o in seg["overrides"] if (o["chapter"], o["para_index"]) not in set(targets)]
    starts = ([l.rstrip("\n") for l in args.starts.read_text(encoding="utf-8").splitlines()
               if l.strip() and not l.startswith("#")] if args.starts else None)
    new = []
    for ch, i in targets:
        body = source.get((ch, i))
        if body is None:
            sys.exit(f"[error] 找不到 {ch}[{i}]")
        cuts = starts_cuts(body, starts) if starts else auto_cuts(body, args.min, args.max)
        method = (f"starts:{args.starts.as_posix()}" if starts
                  else f"auto(min={args.min},max={args.max})")
        new.append({"chapter": ch, "para_index": i, "sha256": body_sha(body),
                    "method": method, "cuts": cuts})
        pieces = [body[a:b] for a, b in zip([0, *cuts], [*cuts, len(body)])]
        print(f"{ch}[{i}] {len(body)} 字 → {len(pieces)} 段；正文字數 "
              f"{[main_len(x) for x in pieces]}")

    if args.dry_run:
        return 0
    order = {lab: n for n, lab in
             ((n, lab) for n, lab, _, _ in split_paragraphs(text))}
    seg["overrides"] = sorted(kept + new, key=lambda o: (order.get(o["chapter"], 0), o["para_index"]))
    seg["note"] = ("上游整章一個 block 的巨段切分覆蓋層；由 scripts/segment.py 產生，"
                   "原文不動。corpus_text.read_paragraphs 套用。")
    seg["updated"] = date.today().isoformat()
    (book / SEGMENTATION_FILE).write_bytes(
        (json.dumps(seg, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    read_paragraphs(book)   # 寫完立刻自驗能套用
    print(f"寫入 {book / SEGMENTATION_FILE}：{len(seg['overrides'])} 個覆蓋段")
    return 0


if __name__ == "__main__":
    sys.exit(main())
