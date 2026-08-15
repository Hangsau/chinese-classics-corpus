"""把一部書切成發包單位，輸出 delegation/<slug>/bNN.md。

段落文字與 para_index 一律取自 corpus_text.split_paragraphs——與 make-scaffold
和 verify 同一來源。手抄或另寫切分邏輯會讓錨點靜默漂移。

批次以「不拆章 + 累積字數上限」決定：一章若自己就超過上限，獨立成一批。
輸出檔名 bNN 與批次內容的對應寫在同目錄的 MANIFEST.json，回填時據此雙向檢查。
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_text import split_paragraphs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--max-chars", type=int, default=8000,
                    help="每批的字數軟上限；單章超過就自己一批")
    ap.add_argument("--exclude-dup-of", metavar="SLUG",
                    help="逐字相同的段落不發包（該書已獨立收錄，標註由 SLUG 沿用）")
    ap.add_argument("--exclude-chapter", metavar="CHAPTER", action="append", default=[],
                    help="整章不發包（重出但切段粒度／異體字不同，逐字比對咬不到）；可重複")
    args = ap.parse_args()

    raw = ROOT / "translations" / args.slug / "raw" / "original.txt"
    if not raw.exists():
        print(f"[error] {raw} 不存在")
        return 1

    rows = split_paragraphs(raw.read_text(encoding="utf-8"))

    if args.exclude_dup_of:
        other = ROOT / "translations" / args.exclude_dup_of / "raw" / "original.txt"
        if not other.exists():
            print(f"[error] {other} 不存在")
            return 1
        dup = {t.strip() for *_, t in split_paragraphs(other.read_text(encoding="utf-8"))}
        before = len(rows)
        rows = [r for r in rows if r[3].strip() not in dup]
        print(f"扣除與 {args.exclude_dup_of} 逐字相同的 {before - len(rows)} 段")

    for label in args.exclude_chapter:
        before = len(rows)
        rows = [r for r in rows if r[1] != label]
        if before == len(rows):
            print(f"[error] --exclude-chapter〈{label}〉在本書找不到")
            return 1
        print(f"扣除整章〈{label}〉{before - len(rows)} 段")

    chapters: list[tuple[str, list[tuple[int, str]]]] = []
    for _, label, para_index, text in rows:
        if not chapters or chapters[-1][0] != label:
            chapters.append((label, []))
        chapters[-1][1].append((para_index, text))

    batches: list[list[tuple[str, list[tuple[int, str]]]]] = []
    running = 0
    for label, paras in chapters:
        size = sum(len(t) for _, t in paras)
        if size > args.max_chars and len(paras) > 1:
            # 單章自己就超過上限：章內切塊，每塊自成一批。章名與 para_index 都不動，
            # 所以後續片段的 para_index 不從 1 起——批次抬頭會標出來。
            chunk: list[tuple[int, str]] = []
            running = 0
            for p in paras:
                if chunk and running + len(p[1]) > args.max_chars:
                    batches.append([(label, chunk)])
                    chunk, running = [], 0
                chunk.append(p)
                running += len(p[1])
            if chunk:
                batches.append([(label, chunk)])
            continue
        if batches and running + size <= args.max_chars:
            batches[-1].append((label, paras))
            running += size
        else:
            batches.append([(label, paras)])
            running = size

    out_dir = ROOT / "delegation" / args.slug
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for n, batch in enumerate(batches, 1):
        name = f"b{n:02d}"
        lines = [f"# {args.slug} 發包單位 {name}", ""]
        total = sum(len(paras) for _, paras in batch)
        lines.append(f"> 本批 {total} 段，含 {len(batch)} 章。"
                     f"para_index 在同一章內編號，回報時**章名與 para_index 兩者都要給**。")
        for label, paras in batch:
            if paras[0][0] != 1:
                lines.append(f">")
                lines.append(f"> 〈{label}〉是同一章切開後的後續片段，"
                             f"para_index 由 {paras[0][0]} 起算而非從 1 開始，"
                             f"**照抄不要重編**。")
        lines.append("")
        for label, paras in batch:
            lines.append(f"## {label}（{len(paras)} 段）")
            lines.append("")
            for para_index, text in paras:
                lines.append(f"[{para_index}] {text}")
            lines.append("")
        (out_dir / f"{name}.md").write_text("\n".join(lines) + "\n",
                                            encoding="utf-8", newline="\n")
        manifest.append({
            "file": f"{name}.md",
            "chapters": [
                {"chapter": label, "para_indexes": [p for p, _ in paras]}
                for label, paras in batch
            ],
            "paras": total,
            "chars": sum(len(t) for _, paras in batch for _, t in paras),
        })
        print(f"{name}.md  {total:3d} 段  {manifest[-1]['chars']:6d} 字  "
              f"{'／'.join(l for l, _ in batch)}")

    (out_dir / "MANIFEST.json").write_text(
        json.dumps({"slug": args.slug, "batches": manifest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print(f"\n{len(batches)} 批，共 {sum(b['paras'] for b in manifest)} 段 -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
