# HANDOFF — chinese-classics-corpus

> 狀態快照。行為規範見 [`CLAUDE.md`](./CLAUDE.md)，結構導航見 [`MAP.md`](./MAP.md)，資料契約見 [`SCHEMA.md`](./SCHEMA.md)。
> 最後更新：2026-07-28

## 現在在哪

**設計期。書目定稿，一個字都還沒抓。**

原因不是進度落後，是刻意的：試點證明既有單軸標籤撐不住（見下），若先抓 74 部再補維度等於全部重標。schema 三個待定案項目經使用者點頭後才開下載器。

## 已完成

| 項目 | 檔案 | 說明 |
|---|---|---|
| 方法論試點 | `pilots/2026-07-28-sunzi-jiuzhang.md` | 孫子兵法 13 領域命中 8；九章算術 13 領域命中 1。雙本對照逼出 `discourse_mode` 維度 |
| 資料契約 | `SCHEMA.md` | 三層標註模型、`discourse_mode` 七值、`text_role: reference`、`annotations.json` 格式、負面結果欄位、跨庫對齊 |
| 行為規範 | `CLAUDE.md` | 與 religions-history 的分界、六條工作守則、七條 anti-pattern |
| 書目 catalog | `scripts/catalog/chinese-classics-ws.json`（73 部）<br>`scripts/catalog/chinese-classics-ctext.json`（1 部） | 共 **74 部**。全部已打 zh.wikisource API 確認頁面存在（86 部候選逐一查證，只 3 部缺，其中 2 部歸宗教庫） |

catalog 已跑過三項驗證：slug 無重複、name_zh 無重複、與 religions-history 4683 部逐一比對無 slug 撞號。唯一同名是徐幹《中論》vs 龍樹《中論》，已在 catalog 內加註不得合併。

## 待使用者定案（**卡住下載，不是可選項**）

1. **`discourse_mode` 七個值**：`observation` / `proposition` / `prescription` / `formalization` / `narrative` / `ritual` / `expression`（定義見 SCHEMA §2）
2. **標註粒度下放到段落級**：書級只留 L1，L2/L3 全進 `annotations.json`
3. **`text_role` 新增 `reference`**：小學類 5 部排除在心理學標註管線外

三項點頭 → 寫 downloader → 開抓。

## 下一步（定案後照順序）

1. `scripts/download-wikisource.py`——直接抄 religions-history 同名腳本，改 catalog 路徑即可。爬蟲倫理常數沿用（UA 含 contact、sleep 帶 jitter、每 100 請求長休、429/403/503 指數退避）
2. 先抓 5 部小批驗格式（建議：孫子兵法、九章算術、人物志、說文解字、厚黑學——涵蓋 original / reference / 高低命中密度）
3. 驗證 SHA-256 + LF 無誤 → commit + push
4. 剩餘 68 部分批抓，每批 5–30 部即 commit
5. 申不害走 ctext 單部補漏：先用 gettext 列目錄拿 leaf URN 再抓，**不得瞎猜 URN**
6. 建 `00-overview/INDEX.json` 生成腳本
7. 標註管線：以 human-questions-corpus 400 題當反向探針逐部跑，先做試點過的 2 部做 ground truth

## 已知風險

- **ctext.org 是紅線**：明文禁自動批量下載，違者無預警封鎖。religions-history 已踩過 200 請求／24h 配額。本庫只留 1 部走 ctext，不得擴充成管線
- **74 部裡 5 部是 `reference`**：硬跑心理學標註只會產噪音。管線要先讀 `text_role` 分流
- **`古三墳`、`竹書紀年（今本）`標 `contested`**：偽託／存疑，標註時要記版本立場，不可當先秦原文用
- **群書治要、水經注、廣韻篇幅大**（40–50 卷），Wikisource 分頁結構可能不規則，第一批不要放
- **書目未涵蓋的第二批候選**（篇幅過大或需另評估）：藝文類聚、太平廣記、太平御覽、通典、康熙字典、墨子閒詁、墨經校釋

## 已明確排除（不要再問一次）

| 書 | 去向 | 理由 |
|---|---|---|
| 爾雅 | religions-history `er-ya` 已收 | 不重複收，用 cross-ref 指過去。《釋親》例外抽取見 SCHEMA §3 |
| 四書章句集注、論語注疏、孝經注疏 | religions-history | 經注，屬「被當成經典」那一半 |
| 列仙傳、高士傳 | religions-history | 神仙傳記＝道教敘事 |
| 詩說 | religions-history | 詩經注 |
| 小說、正史 | 兩庫都不收 | 使用者明確排除 |
| 移轉宗教庫既有文本過來 | 不做 | 會破 SHA-256 鏈、143 部完整三軸標籤、GitHub 歷史，收益近零 |

## 尚未做、不可當結論的推測

pilots 檔 §5 記了兩條：說文解字 540 部首是否構成一套世界分類、釋名聲訓是否編碼民俗世界觀。**兩者均未讀原文**。第一批進庫後用同一套探針跑一次即可證否。
