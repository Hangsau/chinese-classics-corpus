"""
Shared paragraph splitting for original.txt.

make-scaffold.py generates anchors from this; verify.py checks anchors against it.
If the two ever computed paragraphs differently, para_index would drift silently and
every annotation would point at the wrong text — so there is exactly one copy.
"""

import re

CHAPTER_RE = re.compile(r"^=== (\d+) \| (.+) ===$")
MIN_CHARS_DEFAULT = 12


def split_paragraphs(text: str, min_chars: int = MIN_CHARS_DEFAULT
                     ) -> list[tuple[int, str, int, str]]:
    """Yield (chapter_no, chapter_label, para_index, body) for each paragraph.

    Fragments shorter than min_chars are skipped and do not consume an index —
    they are headings and stray markers, not annotatable paragraphs.
    """
    out = []
    ch_no, ch_label, idx = 0, None, 0
    for line in text.split("\n"):
        m = CHAPTER_RE.match(line)
        if m:
            ch_no, ch_label, idx = int(m.group(1)), m.group(2), 0
            continue
        body = line.strip()
        if ch_label is None or len(body) < min_chars:
            continue
        idx += 1
        out.append((ch_no, ch_label, idx, body))
    return out
