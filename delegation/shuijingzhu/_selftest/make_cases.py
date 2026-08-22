"""合成 accept.py 的反向驗證素材：一份完美輸出＋每種只注入一種錯誤的變異輸出。

驗收器沒被驗過就等於沒有驗收。完美輸出應得 0 FAIL；每份變異只改一處，
對準一條 A 類條款，用來確認那條條款真的有牙齒。
`--verify` 會把每份跑一次並對答案，不必人工比對輸出。

SPEC 層的變異（改 SPEC 自己的數字與引句，看 `--check-spec` 抓不抓得到）也在
`--verify` 裡跑，走 tempfile 複本，不動 `SPEC.md`。

  PYTHONIOENCODING=utf-8 python delegation/shuijingzhu/_selftest/make_cases.py --verify
"""
import copy
import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
sys.path.insert(0, BASE)
import accept  # noqa: E402


def _quote(text):
    return "「%s」" % text


def build_perfect():
    """照 SPEC 所有錨點標對的一份輸出：預設判空，錨點逐條覆寫。

    需求按 (章名, 段序) 合併而不是逐表覆寫——有 6 段同時掛在兩張表上，
    逐表覆寫會讓後一張表把前一張的答案蓋掉。
    """
    paras, batch_of, _cl, batch_chapters, problems = accept.read_batches()
    if problems:
        raise SystemExit("批次檔不一致，先修 read_batches：%s" % problems[:3])
    s = accept.parse_spec()

    need = {}      # key -> [domain, ...]
    quotes = {}    # key -> [逐字引句, ...]
    for a in s["anchors"]["hit"]:
        key = (a["chapter"], a["para_index"])
        need.setdefault(key, []).append(a["require"][0])
        quotes.setdefault(key, []).append(a["quote"])
    for code in ("xi", "xii", "guo"):
        for a in s["anchors"][code]:
            key = (a["chapter"], a["para_index"])
            want = "XI" if code == "xi" else "XII"
            if want not in need.get(key, []):
                need.setdefault(key, []).append(want)
                quotes.setdefault(key, []).append(a["quote"])
    for a in s["anchors"]["noxii"]:
        key = (a["chapter"], a["para_index"])
        quotes.setdefault(key, []).append(a["quote"])
        need.setdefault(key, [])

    rows = {}
    for key, text in paras.items():
        jing = "〈" not in text
        rows[key] = {
            "chapter": key[0],
            "para_index": key[1],
            "domains": list(need.get(key, [])),
            "modes": ["formalization"] if jing else ["observation"],
            "reason": ("《水經》本文，水道登錄，合成測試用" if jing
                       else "注文，僅登錄水道地望，合成測試用"),
        }
        if need.get(key):
            rows[key]["modes"] = ["proposition"]
            rows[key]["reason"] = "注文，" + "／".join(
                _quote(q) for q in quotes[key]) + "，合成測試用"
        elif key in quotes:
            rows[key]["reason"] = "注文，" + _quote(quotes[key][0]) + " 只是登錄，合成測試用"
    return rows, batch_of, batch_chapters, s


def write(dirname, rows, batch_of, batch_chapters, only=None):
    """逐段照 batch_of 歸批。

    不可按「章屬於哪一批」分派——本書有 14 章跨批續接，按章分派會把同一章的段
    同時寫進兩個批次檔，A1 立刻報一片重複與多出。
    """
    d = os.path.join(HERE, dirname)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    for batch, chs in batch_chapters.items():
        if only and batch not in only:
            continue
        order = [c for c, _n in chs]
        out = [r for key, r in sorted(
            rows.items(),
            key=lambda kv: (order.index(kv[0][0]) if kv[0][0] in order else 99, kv[0][1]))
            if batch_of.get(key) == batch]
        with open(os.path.join(d, "%s.json" % batch), "w",
                  encoding="utf-8", newline="\n") as f:
            json.dump({"batch": "%s.md" % batch, "rows": out},
                      f, ensure_ascii=False, indent=1)
            f.write("\n")
    return d


def _run(dirname, wanted):
    buf = io.StringIO()
    with redirect_stdout(buf):
        accept.run(os.path.join(HERE, dirname), set(wanted))
    return [ln.strip()[5:].strip() for ln in buf.getvalue().splitlines()
            if ln.strip().startswith("FAIL ")]


def main():
    verify = "--verify" in sys.argv
    rows, batch_of, batch_chapters, s = build_perfect()
    write("perfect", rows, batch_of, batch_chapters)
    print("perfect  %d 段／%d 批" % (len(rows), len(batch_chapters)))

    def anchor(code, i=0):
        a = s["anchors"][code][i]
        return (a["chapter"], a["para_index"]), a

    hit_key, hit_a = anchor("hit")
    hit2_key, hit2_a = anchor("hit", 1)
    xi_key, _ = anchor("xi")
    xii_key, _ = anchor("xii")
    guo_key, _ = anchor("guo")
    nox_key, nox_a = anchor("noxii")
    jing_key = next(k for k in sorted(rows)
                    if "〈" not in accept.read_batches()[0][k]
                    and k != s["jing"]["exception"])
    # 超長段裡挑一個必須命中的，用來驗 A12
    long_keys = [(x["chapter"], x["para_index"]) for x in s["superlong"]]
    long_key = next(k for k in long_keys if rows[k]["domains"])
    paras = accept.read_batches()[0]
    generic = next(g for g in ("又東", "其水", "東南", "水又", "又西")
                   if accept.occurrence_count(paras[long_key], g) > 1)

    cases = []
    hit_quote = _quote(hit_a["quote"])

    def mutate(name, key, expect, fn):
        """expect 是**完整**的預期 FAIL 碼集合，不是「至少含」。

        多出一個沒宣告的碼就算不符——條款之間的連鎖要寫出來才算被理解，
        不能靠「反正該抓的抓到了」放過去。
        """
        m = copy.deepcopy(rows)
        fn(m)
        batch = batch_of[key]
        write(name, m, batch_of, batch_chapters, only={batch})
        cases.append((name, batch, sorted(expect)))

    mutate("m01_a1_row_deleted", hit_key, {"A1"},
           lambda m: m.pop(hit_key))
    # 補一條引句，讓 A9 的格數對得上，才隔離得出 A2
    mutate("m02_a2_illegal_domain", hit_key, {"A2"},
           lambda m: m[hit_key].update(
               domains=m[hit_key]["domains"] + ["ZZ"],
               reason="注文，" + hit_quote + "／" + hit_quote))
    mutate("m03_a3_jing_hit", jing_key, {"A3"},
           lambda m: m[jing_key].update(
               domains=["V"],
               reason="《水經》本文，" + _quote(paras[jing_key][:6])))
    mutate("m04_a4_hit_cleared", hit_key, {"A4"},
           lambda m: m[hit_key].__setitem__("domains", []))
    mutate("m05_a5_xi_missing", xi_key, {"A5"},
           lambda m: m[xi_key].__setitem__("domains", ["VII"]))
    mutate("m06_a5_xi_with_xii", xi_key, {"A5"},
           lambda m: m[xi_key].update(
               domains=m[xi_key]["domains"] + ["XII"],
               reason=m[xi_key]["reason"] + "／" + _quote(s["anchors"]["xi"][0]["quote"])))
    mutate("m07_a6_xii_cleared", xii_key, {"A6"},
           lambda m: m[xii_key].__setitem__("domains", []))
    # 濁漳水[6] 是條文明列的跨表段（必須命中 VII ＋ 過度側 XII），清空必然兩條同響
    mutate("m08_a7_guo_cleared", guo_key, {"A4", "A7"},
           lambda m: m[guo_key].__setitem__("domains", []))
    mutate("m09_a8_noxii_filled", nox_key, {"A8"},
           lambda m: m[nox_key].update(domains=["XII"],
                                       reason="注文，" + _quote(nox_a["quote"])))
    mutate("m10_a9_domains_without_quotes", hit2_key, {"A9"},
           lambda m: m[hit2_key].__setitem__(
               "domains", [hit2_a["require"][0]] + [d for d in ("I", "III")
                                                    if d != hit2_a["require"][0]]))
    # reason 整個抹掉必然同時失去引句，A9／A11 是這一刀不可分割的後果
    mutate("m11_a10_reason_blank", hit_key, {"A9", "A10", "A11"},
           lambda m: m[hit_key].__setitem__("reason", "   "))
    mutate("m12_a11_no_quote", hit_key, {"A9", "A11"},
           lambda m: m[hit_key].__setitem__("reason", "注文，這一段在講人該怎麼活"))
    mutate("m13_a11_fabricated_quote", hit_key, {"A11"},
           lambda m: m[hit_key].__setitem__(
               "reason", "注文，" + _quote("此語本書所無，純屬捏造")))
    mutate("m14_a12_quote_not_unique", long_key, {"A12"},
           lambda m: m[long_key].__setitem__(
               "reason", "注文，" + "／".join(_quote(generic)
                                          for _ in m[long_key]["domains"])))
    mutate("m15_a13_worked_instance", hit_key, {"A13"},
           lambda m: m[hit_key].__setitem__("modes", ["worked_instance"]))

    for name, batch, expect in cases:
        print("%-30s (%s) 應觸發 %s" % (name, batch, "／".join(expect)))

    if not verify:
        print("\n加 --verify 可直接對答案")
        return 0

    bad = []
    fails = _run("perfect", sorted(batch_chapters))
    print("\nperfect  A 類 FAIL %d" % len(fails))
    if fails:
        bad.append(("perfect", fails[:5]))

    for name, batch, expect in cases:
        fails = _run(name, [batch])
        codes = sorted({f.split()[0] for f in fails})
        ok = codes == expect
        print("%-30s → %-12s %s" % (name, "／".join(codes) or "無", "ok" if ok else "不符"))
        if not ok:
            bad.append((name, fails[:3]))

    print()
    bad += _verify_spec_mutations()
    for name, detail in bad:
        print("  !! %s：%s" % (name, detail))
    print("反向驗證：%s" % ("全數命中" if not bad else "%d 項不符" % len(bad)))
    return 1 if bad else 0


def _anchor_line(text, a):
    """錨點列長這樣：`| 02 | [4] | b03 | 「…」 | V |`。"""
    head = "| %s | [%d] | %s |" % (a["chapter"], a["para_index"], a["batch"])
    for line in text.splitlines():
        if line.startswith(head) and a["quote"] in line:
            return line
    raise SystemExit("找不到錨點列，SPEC 表格格式已變：%s[%d]"
                     % (a["chapter"], a["para_index"]))


def _first_hit():
    return accept.parse_spec()["anchors"]["hit"][0]


def _quote_swap(text):
    """把必須命中表第一列的引句改一個字。"""
    q = _first_hit()["quote"]
    return text.replace(q, q[:-1] + "焉", 1)


def _batch_swap(text):
    a = _first_hit()
    line = _anchor_line(text, a)
    wrong = "b01" if a["batch"] != "b01" else "b02"
    return text.replace(line, line.replace("| %s |" % a["batch"], "| %s |" % wrong, 1), 1)


def _para_swap(text):
    a = _first_hit()
    line = _anchor_line(text, a)
    return text.replace(line, line.replace("| [%d] |" % a["para_index"], "| [997] |", 1), 1)


def _table_conflict(text):
    """把破除側的一段複製進技術側：一段不可能同時「必須含 XII」與「不得填 XII」。"""
    s = accept.parse_spec()
    xi = s["anchors"]["xi"][0]
    tail = _anchor_line(text, s["anchors"]["noxii"][-1])
    dup = "| %s | [%d] | %s | 「%s」 |  |" % (
        xi["chapter"], xi["para_index"], xi["batch"], xi["quote"])
    return text.replace(tail, tail + "\n" + dup, 1)


SPEC_MUTATIONS = [
    ("s2_declared_count", {"S2"},
     lambda t: t.replace("**必須命中的錨點 100 段**", "**必須命中的錨點 101 段**", 1)),
    ("s3_quote_altered", {"S3"}, _quote_swap),
    ("s3_batch_wrong", {"S3"}, _batch_swap),
    ("s3_para_missing", {"S3"}, _para_swap),
    ("s4_xi_vs_noxii", {"S2", "S4"}, _table_conflict),
    ("s5_jing_count", {"S5"},
     lambda t: t.replace("全書 301 段", "全書 300 段", 1)),
    ("s6_superlong_chars", {"S6"},
     lambda t: t.replace("`穀水`[5] 9118", "`穀水`[5] 9119", 1)),
    ("s7_numeric_chapter_dropped", {"S7"},
     lambda t: t.replace("`35`", "", 1)),
]


def _verify_spec_mutations():
    bad = []
    original = open(accept.SPEC_PATH, encoding="utf-8").read()
    real = accept.SPEC_PATH
    try:
        for name, expect, fn in SPEC_MUTATIONS:
            text = fn(original)
            if text == original:
                bad.append((name, "變異沒改到任何字，regex 已失效"))
                continue
            fd, tmp = tempfile.mkstemp(suffix=".md", text=True)
            os.close(fd)
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            accept.SPEC_PATH = tmp
            buf = io.StringIO()
            try:
                with redirect_stdout(buf):
                    accept.check_spec()
            finally:
                accept.SPEC_PATH = real
                os.unlink(tmp)
            codes = sorted({ln.strip()[5:].split()[0]
                            for ln in buf.getvalue().splitlines()
                            if ln.strip().startswith("FAIL ")})
            ok = codes == sorted(expect)
            print("%-30s → %-12s %s" % (name, "／".join(codes) or "無",
                                        "ok" if ok else "不符"))
            if not ok:
                bad.append((name, "應觸發 %s，實得 %s"
                            % ("／".join(sorted(expect)), codes or "無")))
    finally:
        accept.SPEC_PATH = real
    return bad


if __name__ == "__main__":
    sys.exit(main())
