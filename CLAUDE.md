# chinese-classics-corpus — AI 工作守則

> 給未來接手的 Claude / m3 / 其他 AI agent。狀態快照見 [`HANDOFF.md`](./HANDOFF.md)，結構導航見 [`MAP.md`](./MAP.md)，資料契約見 [`SCHEMA.md`](./SCHEMA.md)。

## 一句話

**漢籍世俗典籍庫**：收古典漢語中非宗教、非正史、非小說的典籍（諸子、兵家、算書、字書、雜史、志怪、權謀），做段落級的人生問題標註，與 religions-history 構成互補的兩半。

## 與 religions-history 的分界（**不可含糊**）

> **religions-history 收「被當成經典／信仰文本」者；本庫收「學術著述、技藝、謀略」。**

- 《孝經》《四書章句集注》《論語注疏》→ religions-history
- 《潛夫論》《風俗通義》《人物志》→ 本庫
- 《列仙傳》《高士傳》（神仙傳記，道教敘事）→ religions-history
- 《神異經》《洞冥記》（志怪）→ 本庫
- 已在宗教庫者**一律不重複收**，用 `religions-history:<slug>` cross-ref 指過去。已知：`er-ya`（爾雅注）、`huainanzi`、黃帝內經

判不出來的**不要自己決定**，寫進 HANDOFF 待辦問使用者。

## 工作守則

### 1. 收錄判準與標註判準嚴格分離

**收錄只看三條**：古典漢語、有乾淨全文、公有領域。**不看主題。**

這條是用血換來的：規劃階段憑書名判定「兵家與心理學關聯低」，實讀後孫子兵法 13 領域命中 8。詳見 [`pilots/2026-07-28-sunzi-jiuzhang.md`](./pilots/2026-07-28-sunzi-jiuzhang.md)。

**禁止**用書名、類別或既有印象決定一部書有沒有標註價值。

### 2. 標註一律讀全文，粒度是段落

- 書級只放 L1 結構欄位
- L2 `psych_domains` + L3 `discourse_mode` 一律段落級，寫 `annotations.json`
- **不動 `raw/original.txt`**（動了破 SHA-256）
- 判不出來留 `null`；`null` 是「未標」不是「沒有」

### 3. 負面結果必須寫入

書級 `meta.json` 的 `psych_survey` 要同時記 `domains_hit` 與 `domains_null`。九章算術 13 領域只中 1 個——這個結果本身是資料。不記，下次又有人憑書名猜著重跑。

### 4. 爬蟲倫理（**強制**，沿用 religions-history 標準）

- 用含 contact email + repo URL 的 User-Agent，禁預設 UA
- 睡眠必帶 jitter，每 100 請求長休
- 處理 429/403/503 指數退避
- 不繞 robots.txt、不偽裝、不用 proxy rotation
- **ctext.org 明文禁止自動批量下載，違者無預警封鎖**。ctext 只作目錄與校勘對照，批量一律走 Wikisource／GitHub。單部補漏走章級 URN 且總量須遠低於 200 請求／24h

### 5. commit + push 紀律

- 每完成一小批（5–30 部）即 commit + push
- push 前跑 verify 確保全綠
- 大階段完成後重生索引再 commit

### 6. 文件對齊

結構性改動後主動更新 `HANDOFF.md`、`MAP.md`、`SCHEMA.md`、`00-overview/INDEX.md`，不等使用者問。

## 環境

- Windows 11 + Git Bash + Python 3.12
- Console 是 cp950，所有 Python 一律 `PYTHONIOENCODING=utf-8 python ...`
- `.gitattributes` 強制 LF（防 CRLF 破壞 SHA-256）

## Anti-pattern（**禁止**）

- ❌ 憑書名判斷有無標註價值（本庫存在的原因就是這個錯誤）
- ❌ 只記命中、不記未命中
- ❌ 書級單一標籤打發內部異質性高的書
- ❌ 把 `reference` 類（字書韻書）丟進心理學標註管線
- ❌ 對 ctext.org 跑批量下載
- ❌ 把跨文本命題對撞塞進 metadata（那是內容產出，不是標籤）
- ❌ 直接覆寫 meta.json 不跑 verify
