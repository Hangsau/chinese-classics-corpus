"""
Shared paragraph splitting for original.txt.

make-scaffold.py generates anchors from this; verify.py checks anchors against it.
If the two ever computed paragraphs differently, para_index would drift silently and
every annotation would point at the wrong text — so there is exactly one copy.

Some upstream pages wrap a whole chapter in one block element, so original.txt has
no line break to split on (HANDOFF C 組). raw/ is checksummed and never edited;
instead scripts/segment.py writes <book>/segmentation.json, an overlay of cut offsets
inside named paragraphs. Every caller must go through read_paragraphs() (or pass the
overlay to split_paragraphs) so all tools see the same paragraph numbering.
"""

import hashlib
import json
import re
from pathlib import Path

CHAPTER_RE = re.compile(r"^=== (\d+) \| (.+) ===$")
MIN_CHARS_DEFAULT = 12
SEGMENTATION_FILE = "segmentation.json"
CHAPTER_TITLES_FILE = "chapter_titles.json"


class SegmentationError(ValueError):
    """segmentation.json no longer matches the paragraph it was cut from."""


def body_sha(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def load_segmentation(book_dir: Path) -> dict | None:
    p = Path(book_dir) / SEGMENTATION_FILE
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def split_paragraphs(text: str, min_chars: int = MIN_CHARS_DEFAULT,
                     segmentation: dict | None = None
                     ) -> list[tuple[int, str, int, str]]:
    """Yield (chapter_no, chapter_label, para_index, body) for each paragraph.

    Fragments shorter than min_chars are skipped and do not consume an index —
    they are headings and stray markers, not annotatable paragraphs.

    With a segmentation overlay, each listed source paragraph (chapter label +
    its original para_index) is emitted as several paragraphs cut at the recorded
    offsets; later paragraphs in that chapter are renumbered after them.
    """
    cuts_at: dict[tuple[str, int], dict] = {}
    for o in (segmentation or {}).get("overrides", []):
        cuts_at[(o["chapter"], o["para_index"])] = o

    out = []
    ch_no, ch_label, src_idx, idx = 0, None, 0, 0
    for line in text.split("\n"):
        m = CHAPTER_RE.match(line)
        if m:
            ch_no, ch_label, src_idx, idx = int(m.group(1)), m.group(2), 0, 0
            continue
        body = line.strip()
        if ch_label is None or len(body) < min_chars:
            continue
        src_idx += 1
        o = cuts_at.pop((ch_label, src_idx), None)
        if o is None:
            idx += 1
            out.append((ch_no, ch_label, idx, body))
            continue
        if o["sha256"] != body_sha(body):
            raise SegmentationError(
                f"{ch_label}[{src_idx}] 的正文與 segmentation.json 記錄的 sha256 不符")
        bounds = [0, *o["cuts"], len(body)]
        for a, b in zip(bounds, bounds[1:]):
            idx += 1
            out.append((ch_no, ch_label, idx, body[a:b].strip()))
    if cuts_at:
        missing = ", ".join(f"{c}[{i}]" for c, i in cuts_at)
        raise SegmentationError(f"segmentation.json 指到不存在的段落：{missing}")
    return out


def load_chapter_titles(book_dir: Path) -> dict[int, str]:
    """chapter_titles.json: display titles for chapters whose raw label is only an ordinal.

    {"<chapter_no>": {"label": <raw label>, "title": <real title>}}; raw/ stays untouched.
    verify.py checks each entry's label still matches raw, so a stale overlay cannot
    silently rename the wrong chapter.
    """
    p = Path(book_dir) / CHAPTER_TITLES_FILE
    if not p.exists():
        return {}
    return {int(k): v["title"] for k, v in json.loads(p.read_text(encoding="utf-8")).items()}


def read_paragraphs(book_dir: Path, min_chars: int = MIN_CHARS_DEFAULT
                    ) -> list[tuple[int, str, int, str]]:
    """split_paragraphs over <book_dir>/raw/original.txt with its overlay applied."""
    book_dir = Path(book_dir)
    text = (book_dir / "raw" / "original.txt").read_text(encoding="utf-8")
    return split_paragraphs(text, min_chars, load_segmentation(book_dir))
