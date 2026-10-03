"""詩經重抓第二步：python scripts/compose-shijing.py <快取目錄> [--write]

由 cache.json 組出詩經 raw/original.txt：每篇一章、章名＝詩經主頁的部‧組‧篇（如「國風‧邶風‧柏舟」），只留毛詩序與詩文。

維基文庫子頁格式不一：有的分「毛詩序／詩文／註解」小節，有的把三家詩說（魯詩說、齊詩說、韓詩說）與現代註解併在同頁。
download-wikisource.py 的按標題切分會把它們切成「魯詩說（1）」「註解（1）」這類章並丟掉篇名，故改由本腳本組裝：
- 丟棄小節：註解、注釋、註釋、解䆁、解釋、譯文、白話、賞析、魯詩說、齊詩說、韓詩說、參考、校勘
- 毛詩序小節改寫成「毛詩序：「……」」一行（與未分節頁面同形）
- 詩文中的小字異文校記（「一作「仇」」，共 112 處）包成〈〉夾注，引句時剔除
- 笙詩 6 篇（南陔、白華、華黍、由庚、崇丘、由儀）只有序與「有其義而亡其辭」，照留
"""
import hashlib, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

C = Path(r"C:/claudehome/projects/chinese-classics-corpus")
here = Path(sys.argv[1])  # fetch-shijing.py 的快取目錄
cache = json.loads((here / "cache.json").read_text(encoding="utf-8"))
cat = json.loads((C / "scripts/catalog/chinese-classics-ws.json").read_text(encoding="utf-8"))
lst = cat if isinstance(cat, list) else next(v for v in cat.values() if isinstance(v, list))
seq = next(e for e in lst if e["slug"] == "book-of-poetry")["wikisource_subpages_explicit"]
groups = json.loads((here / "groups.json").read_text(encoding="utf-8"))  # 主頁 wikitext 的 ==部== 與 '''組'''
DROP = re.compile(r"^(註解|注解|注釋|註釋|註|注|解䆁|解釋|譯文|白話|賞析|魯詩說|齊詩說|韓詩說|參考|校勘|延伸閱讀|相關)")
PATH = re.compile(r"^(詩[·‧])?(國風|小雅|大雅|周頌|魯頌|商頌|頌)")

chapters, problems = [], []
for t in seq:
    raw = cache[t]
    secs, head, cur = [], None, []
    for line in raw.splitlines():
        m = re.match(r"^#+\s*(.+?)\s*$", line)
        if m:
            secs.append((head, cur)); head, cur = m.group(1), []
        else:
            cur.append(line)
    secs.append((head, cur))
    path, body = None, []
    for h, lines in secs:
        txt = "\n".join(l for l in lines if l.strip()).strip()
        if h and PATH.match(h) and path is None:
            path = h
            if txt: body.append(txt)
            continue
        if h and DROP.match(h):
            continue
        if not txt:
            continue
        if h == "毛詩序" and not txt.startswith("毛詩序"):
            txt = f"毛詩序：「{txt}」"
        body.append(txt)
    name = re.sub(r"\s*\(.*\)$", "", t.split("/", 1)[1])
    sec, grp = groups[t]
    label = "‧".join(x for x in (sec, grp, name) if x)
    text = re.sub(r"一作「[^」]*」", lambda x: f"〈{x.group(0)}〉", "\n".join(body).strip())  # 維基文庫小字異文校記，照語料慣例標夾注
    if "毛詩序" not in text: problems.append(f"{t} 無毛詩序")
    if len(text) < 30: problems.append(f"{t} 正文過短 {len(text)}：{text[:40]}")
    chapters.append((label, text))

labels = [l for l, _ in chapters]
dup = {l for l in labels if labels.count(l) > 1}
print("篇數", len(chapters), "重名", dup)
for p in problems: print("  ", p)
if "--write" in sys.argv:
    assert not dup
    out = C / "translations/book-of-poetry/raw"
    lines = []
    for i, (l, t) in enumerate(chapters, 1):
        lines += [f"=== {i} | {l} ===", t, ""]
    b = ("\n".join(lines).rstrip() + "\n").encode("utf-8")
    (out / "original.txt").write_bytes(b)
    h = hashlib.sha256(b).hexdigest()
    (out / "checksums.sha256").write_bytes(f"{h}  original.txt\n".encode("utf-8"))
    mp = C / "translations/book-of-poetry/meta.json"
    m = json.loads(mp.read_text(encoding="utf-8"))
    m.update({"size_bytes": len(b), "checksum_sha256": h, "chapter_count": len(chapters), "expected_chapter_count": 311,
              "verified": True, "version": "Wikisource 毛詩本",
              "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "notes": "2026-10-04 自 Wikisource 重抓（取代 2026-10-02 自 religions-history 複製的 301 首碼位序版）。311 篇＝305 首＋笙詩 6 篇（有目無辭，只存毛詩序），依毛詩篇次；章名＝詩經主頁的部‧組‧篇（國風‧邶風‧柏舟、商頌‧那）。子頁格式不一，三家詩說與現代註解小節已剔除，只留毛詩序與詩文；詩文中 112 處「一作「X」」異文校記包成〈〉夾注（組裝：scripts/compose-shijing.py）。〈有女同車〉〈載驅〉維基文庫本無毛詩序，照實不補。"})
    mp.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("寫入", len(b), "bytes")
