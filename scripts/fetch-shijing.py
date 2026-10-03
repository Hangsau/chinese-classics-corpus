"""詩經重抓第一步：逐頁抓子頁原文與主頁分組，存 <快取目錄>/cache.json、groups.json（可中斷續抓）。

    python scripts/fetch-shijing.py <快取目錄>

第二步：python scripts/compose-shijing.py <快取目錄> --write
子頁清單＝catalog 的 wikisource_subpages_explicit（依詩經主頁 wikitext 的毛詩篇次，311 篇）。
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

C = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("dw", C / "scripts/download-wikisource.py")
dw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dw)
here = Path(sys.argv[1])
here.mkdir(parents=True, exist_ok=True)
cp = here / "cache.json"
cache = json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else {}
cat = json.loads((C / "scripts/catalog/chinese-classics-ws.json").read_text(encoding="utf-8"))
lst = cat if isinstance(cat, list) else next(v for v in cat.values() if isinstance(v, list))
seq = next(e for e in lst if e["slug"] == "book-of-poetry")["wikisource_subpages_explicit"]
for k, t in enumerate(seq):
    if t in cache:
        continue
    dw._polite_sleep_inline(dw.SLEEP_BETWEEN_REQUESTS)
    cache[t] = dw.get_page_text(t)
    if k % 20 == 0:
        cp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        print(k, flush=True)
cp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
print("pages", len(cache))

# 主頁 wikitext：==部== 之下以 '''組''' 起頭，接著 # [[/篇名|…]] 清單
w = dw.api_get({"action": "parse", "page": "詩經", "prop": "wikitext", "format": "json", "formatversion": "2"})["parse"]["wikitext"]
sec = grp = None
groups = {}
for line in w.splitlines():
    a = re.match(r"^==\s*([^=]+?)\s*==\s*$", line)
    if a:
        sec, grp = a.group(1), None
        continue
    b = re.search(r"'''([^']+)'''", line)
    if b and "[[" not in line:
        grp = b.group(1)
        continue
    for link in re.findall(r"\[\[(/[^\]|]+)", line):
        groups.setdefault("詩經" + link.replace("_", " "), (sec, grp))
(here / "groups.json").write_text(json.dumps(groups, ensure_ascii=False), encoding="utf-8")
print("groups", len(groups))
