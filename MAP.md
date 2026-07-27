# 導航地圖

> 冷啟動先讀本檔 §決策索引 + §踩雷點，別窮舉讀檔。狀態見 `HANDOFF.md`。

## 決策索引

| 要做什麼 | 先讀 |
|---|---|
| 判斷一部書該進本庫還是 religions-history | `CLAUDE.md` §與 religions-history 的分界 |
| 決定要不要收某部書 | `CLAUDE.md` §1（收錄只看三條：古典漢語／有乾淨全文／公有領域，**不看主題**） |
| 改標註欄位、加 `discourse_mode` 值 | `SCHEMA.md` §1–§2，改動前先在 `pilots/` 驗證 |
| 理解為什麼標註要下放到段落級 | `pilots/2026-07-28-sunzi-jiuzhang.md` §3–§4 |
| 寫 downloader | `CLAUDE.md` §4 爬蟲倫理 + `../religions-history/scripts/download-wikisource.py` |
| 決定書目、查某部書在不在清單 | `scripts/catalog/chinese-classics-ws.json`（73）、`chinese-classics-ctext.json`（1） |
| 跑心理學標註 | 先讀 `SCHEMA.md` §3 分流 `text_role`，`reference` 類不進管線 |
| 記錄「這部書沒東西」 | `SCHEMA.md` §5 `psych_survey`（`domains_hit` + `domains_null` 都要寫） |
| 接到 knowledge-hub | `SCHEMA.md` §6 + `../knowledge-hub/CLAUDE.md` |

## 結構

```
CLAUDE.md          行為規範（少改）
HANDOFF.md         狀態快照（每次工作後改）
MAP.md             本檔
SCHEMA.md          資料契約——動 downloader 或標註管線前必讀
pilots/            方法論驗證紀錄。新增 schema 維度前必須先在這裡驗過
scripts/catalog/   書目 canonical。抓取來源分檔：*-ws.json / *-ctext.json
translations/<slug>/
  ├── meta.json         書級 L1 + psych_survey
  ├── raw/original.txt  原文，唯讀（動了破 SHA-256）
  ├── raw/checksums.sha256
  └── annotations.json  段落級 L2 psych_domains + L3 discourse_mode
00-overview/       生成物（INDEX.json / INDEX.md），不手改
```

`translations/` 與 `00-overview/` 目前是空的——設計期尚未下載，見 HANDOFF。

## 與其他專案的關係

| 專案 | 關係 |
|---|---|
| `religions-history` | **互補的兩半**，非上下游。收錄邊界見 CLAUDE.md。共用 13 人生問題領域與 `discourse_mode` 詞彙；`semantic_tags` 各自獨立 |
| `knowledge-hub` | 下游控制平面。跨庫引用一律 `專案:slug`，關係預設 `proposed` |
| `human-questions-corpus`（400 題） | 反向探針來源：由問題反問文本，不由文本猜標籤 |

## 踩雷點

- **不憑書名判斷有無標註價值**。本庫存在的原因就是這個錯誤（兵家 8/13）。
- **不只記命中**。九章 13 領域只中 1，這個「幾乎全空」本身是資料，不記半年後有人又憑書名重跑。
- **不對 ctext.org 跑批量下載**。明文禁止，違者無預警封鎖；religions-history 已踩過 200/24h。ctext 只作目錄與校勘對照，本庫僅 1 部走它。
- **不動 `raw/original.txt`**。動了破 SHA-256。
- **不把 `reference` 類（字書韻書）丟進心理學標註管線**。真價值在術語正規化。
- **不用書級單一標籤打發內部異質性高的書**。孫子〈用間〉的認識論與〈九地〉的恐懼悖論掛同一個 `psych_tags` 會互相稀釋。
- **不把跨文本命題對撞塞進 metadata**。同舟共濟 vs Robbers Cave 是內容產出，歸分析層。
- **`null` 是「未標」不是「沒有」**。兩者混淆會讓負面結果失效。
- **同名異書不合併**：徐幹《中論》≠ 龍樹《中論》（後者在宗教庫）。
- Windows console 是 cp950，所有 Python 一律 `PYTHONIOENCODING=utf-8 python ...`；`.gitattributes` 強制 LF。
