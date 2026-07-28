# 導航地圖

> 冷啟動先讀本檔 §決策索引 + §踩雷點，別窮舉讀檔。狀態見 `HANDOFF.md`。

## 決策索引

| 要做什麼 | 先讀 |
|---|---|
| 判斷一部書該進本庫還是 religions-history | `CLAUDE.md` §與 religions-history 的分界 |
| 決定要不要收某部書 | `CLAUDE.md` §1（收錄只看三條：古典漢語／有乾淨全文／公有領域，**不看主題**） |
| 改標註欄位、加 `discourse_mode` 值 | `SCHEMA.md` §1–§2，改動前先在 `pilots/` 驗證 |
| 理解為什麼標註要下放到段落級 | `pilots/2026-07-28-sunzi-jiuzhang.md` §3–§4 |
| 改 downloader | `CLAUDE.md` §4 爬蟲倫理 + 本檔 §下載器結構陷阱（**四類已修過的問題，別退回去**） |
| 查某部書在不在清單、為何某部結構特殊 | `scripts/catalog/chinese-classics-ws.json`（73 部，特殊處置寫在該部的 `structure_note` / `coverage_note`） |
| 抓完驗證 | `PYTHONIOENCODING=utf-8 python scripts/verify.py`；重生索引 `... scripts/build-index.py` |
| 跑心理學標註 | 先讀 `SCHEMA.md` §3 分流 `text_role`，`reference` 類不進管線 |
| 標一部新書 | `scripts/make-scaffold.py --slug <slug>` 產骨架 → 讀**全文**填 null 欄位 → 回填 `meta.json` 的 `psych_survey`。**不要手寫 `annotations.json`**（壞錨點都是這樣進來的） |
| 改段落切分規則 | `scripts/corpus_text.py` 是唯一來源，make-scaffold 與 verify 共用。**動它等於動所有既有錨點** |
| 記錄「這部書沒東西」 | `SCHEMA.md` §5 `psych_survey`（`domains_hit` + `domains_null` 都要寫） |
| 接到 knowledge-hub | `SCHEMA.md` §6 + `../knowledge-hub/CLAUDE.md` |

## 結構

```
CLAUDE.md          行為規範（少改）
HANDOFF.md         狀態快照（每次工作後改）
MAP.md             本檔
SCHEMA.md          資料契約——動 downloader 或標註管線前必讀
pilots/            方法論驗證紀錄。新增 schema 維度前必須先在這裡驗過
scripts/catalog/   書目 canonical（只有 *-ws.json；ctext 路線已整條移除）
scripts/corpus_text.py           段落切分單一來源（make-scaffold 與 verify 共用）
scripts/download-wikisource.py   下載器，含 --survey 預檢模式
scripts/make-scaffold.py         由本文生成標註骨架（錨點自動產，人只填 null）
scripts/verify.py                驗證，push 前必須全綠。含錨點漂移偵測
scripts/build-index.py           由 meta.json 生成索引
translations/<slug>/
  ├── meta.json         書級 L1 + psych_survey
  ├── raw/original.txt  原文，唯讀（動了破 SHA-256）
  ├── raw/checksums.sha256
  └── annotations.json  段落級 L2 psych_domains + L3 discourse_mode
00-overview/       生成物（INDEX.json / INDEX.md），不手改
```

`translations/` 已有 68 部（phase 1 全數），`00-overview/` 已生成。`annotations.json` 目前 5 部（`sunzi-bingfa` 91 段、`jiuzhang-suanshu` 720 段、`haidao-suanjing` 24 段、`renwuzhi` 229 段、`qianfulun` 268 段），其餘 63 部的 `psych_survey` 仍是 `null`＝未通讀。

## 下載器結構陷阱（四類已修過，改 downloader 前先看）

段落級錨點靠篇名（SCHEMA §4），以下每一類都會把錨點毀掉：

| 陷阱 | 判別 | 現行對策 |
|---|---|---|
| 抽取時丟掉篇名標題 | 一部書只回 1 章 | `extract_main_text` 收 h2/h3/h4 並前綴 `## ` |
| Wikisource 平行上傳（編號頁＋篇名頁並存） | bytes 與章數同時異常膨脹 | catalog `subpage_drop_pattern` + 抓取時內容雜湊去重 |
| 卷級子頁沒往下切到篇 | 章標籤全是「卷N」 | 子頁本文再切一層；例外用 `no_subpage_split`（竹書紀年）。**殘留個案不重抓**：潛夫論 `卷九`／`卷十` 因篇名標題只有 10 字（低於 corpus_text 的 12 字下限）未切出，錨點仍唯一，改在 `psych_survey.structure_notes` 補對照表 |
| 重定向對只差一行標題 | 切分後才出現同文章節 | 切分**之後**再依本文雜湊去重，保留較具體的標籤 |

其他 catalog 旗標：`force_single_page`（正文在根頁）、`wikisource_subpages_explicit`（正文只在通常被當導航排除的 `/全覽`）。

## 與其他專案的關係

| 專案 | 關係 |
|---|---|
| `religions-history` | **互補的兩半**，非上下游。收錄邊界見 CLAUDE.md。共用 13 人生問題領域與 `discourse_mode` 詞彙；`semantic_tags` 各自獨立 |
| `knowledge-hub` | 下游控制平面。跨庫引用一律 `專案:slug`，關係預設 `proposed` |
| `human-questions-corpus`（400 題） | 反向探針來源：由問題反問文本，不由文本猜標籤 |

## 踩雷點

- **不憑書名判斷有無標註價值**。本庫存在的原因就是這個錯誤（兵家 8/13）。
- **不只記命中**。九章 720 段有 692 段全空、13 領域只中 3（其中 2 個還在劉徽自序），這個「幾乎全空」本身是資料，不記半年後有人又憑書名重跑。
- **零命中不等於沒思想**。九章思想密度最高的一段（割圓術）零命中，因為它屬 `Z-wisdom` 支流，而支流依 vocab 不得填進 `psych_domains`。下結論前先分清是「沒有」還是「被 13 領域刻意排除」。人物志 25 段空白同因（方法論外殼），所以這不是算書專屬情形，凡帶方法論自覺的書都會踩到。
- **`domains_hit` 一定要配 `domain_para_counts` 讀**。人物志命中 10／13 看似覆蓋廣，實際上四個領域吃掉絕大部分，IV 與 X 各只 1 段。潛夫論命中 12／13 更廣，但 V 一個領域就吃掉本文的 65%。只看命中數會系統性高估一部書的覆蓋面。
- **`formalization` 不綁數學，也不綁制度**。人物志〈材能〉的「某能→某材→某任→某政」對照表、潛夫論〈考績〉的貢士賞罰遞加、〈夢列〉的十類夢判讀口訣，三者都判 `formalization`。判準只有一條：規範被寫成可執行程序。
- **空白段有三種成因，別混為一談**。① 被 `Z-wisdom` 吸走（九章割圓術、人物志方法論外殼）；② 真的沒有（海島算經）；③ 體例摻雜——那些段根本不是同一種文本（潛夫論的姓氏譜系 18 段＋附錄版本層 42 段）。三者在 `psych_domains: []` 裡長得一模一樣。
- **附錄／序跋／著錄要從分母裡拿掉**。潛夫論 268 段有 52 段（19%）是本傳、清人序跋、歷代著錄、佚文。算領域密度用本文段數，處置寫在該部 `psych_survey.structure_notes`。
- **不對 ctext.org 跑批量下載**。明文禁止，違者無預警封鎖；religions-history 已踩過 200/24h。本庫現在完全不碰 ctext。
- **`expected_chapter_count` 是驗證後凍結的觀測值，不是估計值**。verify 報章數不符＝結構真的變了，要判斷是修好還是弄壞，**不要反射性再同步一次數字**。
- **不動 `raw/original.txt`**。動了破 SHA-256。
- **不把 `reference` 類（字書韻書）丟進心理學標註管線**。真價值在術語正規化。
- **不用書級單一標籤打發內部異質性高的書**。孫子〈用間〉的認識論與〈九地〉的恐懼悖論掛同一個 `psych_tags` 會互相稀釋。
- **不把跨文本命題對撞塞進 metadata**。同舟共濟 vs Robbers Cave 是內容產出，歸分析層。
- **`null` 是「未標」不是「沒有」**。兩者混淆會讓負面結果失效。
- **同名異書不合併**：徐幹《中論》≠ 龍樹《中論》（後者在宗教庫）。
- Windows console 是 cp950，所有 Python 一律 `PYTHONIOENCODING=utf-8 python ...`；`.gitattributes` 強制 LF。
