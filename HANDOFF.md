# HANDOFF — chinese-classics-corpus

> 狀態快照。行為規範見 [`CLAUDE.md`](./CLAUDE.md)，結構導航見 [`MAP.md`](./MAP.md)，資料契約見 [`SCHEMA.md`](./SCHEMA.md)。
> 最後更新：2026-07-28

## 現在在哪

**第一批 68 部全文已入庫並通過驗證。標註一個字都還沒開始。**

`verify.py`：68 部、10,660,493 bytes、**0 errors、6 warnings**。索引已由 `build-index.py` 生成。
`psych_survey` 全部是 `null`——依 SCHEMA §5，`null` 是「未通讀」不是「沒有」。

下一件事是標註管線，不是再擴收書目。

## 已完成

| 項目 | 檔案 | 說明 |
|---|---|---|
| 方法論試點 | `pilots/2026-07-28-sunzi-jiuzhang.md` | 孫子兵法 13 領域命中 8；九章算術 13 領域命中 1。雙本對照逼出 `discourse_mode` 維度 |
| 資料契約 | `SCHEMA.md` | 三層標註模型、`discourse_mode` 七值、`text_role: reference`、`annotations.json` 格式、負面結果欄位、跨庫對齊。§1.1 補了段落級的白話說明 |
| 行為規範 | `CLAUDE.md` | 與 religions-history 的分界、六條工作守則、七條 anti-pattern |
| 書目 catalog | `scripts/catalog/chinese-classics-ws.json` | **73 部**（phase 1 共 68、phase 2 共 5）。全部走 Wikisource |
| 下載器 | `scripts/download-wikisource.py` | 含 `--survey` 預檢模式（1 請求／部）先掃結構再花內容請求 |
| 驗證 | `scripts/verify.py` | SHA-256／CRLF／過小檔／章標籤唯一性／同文章節／`psych_survey` 欄位存在 |
| 索引 | `scripts/build-index.py` → `00-overview/INDEX.{json,md}` | 由資料生成，**不得手改** |
| 全文 | `translations/`（68 部） | 已 commit |

### 使用者已定案的三項

1. `discourse_mode` 七值 —— 通過
2. 標註粒度下放段落級 —— 通過（說明已寫進 SCHEMA §1.1）
3. 小學 5 部 —— **改排 phase 2，不是排除**。理由寫進 SCHEMA §3：排除＝憑書名判定無價值，那正是本庫要修正的錯誤
4. **ctext 路線整條移除** —— 使用者指示「取得簡單一點」。`chinese-classics-ctext.json` 已刪，申不害不收

## 抓取過程修掉的四類真問題（都會毀掉段落級錨點，別再退回去）

| 問題 | 症狀 | 修法 |
|---|---|---|
| 篇名標題被丟棄 | 孫子兵法抓回來只有 1 章 | `extract_main_text` 補收 h2/h3/h4，前綴 `## ` |
| 平行上傳整卷重複 | 韓非子 864,988 bytes／80 章（實際重了三套） | catalog `subpage_drop_pattern` + 內容雜湊去重 |
| 卷級子頁沒往下切到篇 | 鹽鐵論只有 10 個「卷N」，60 篇全埋在裡面 | 子頁本文再切一層標題；竹書紀年以 `no_subpage_split` opt-out（698 條逐年紀事切下去全是「元年」互撞） |
| 重定向對切分後才撞成同文 | 外儲說右上／右上 只差一行標題，前置雜湊擋不住 | 切分**之後**再依本文雜湊去重，保留較具體的標籤 |

另外處理過：6 部抓到消歧義／目錄頁（用 `action=parse&prop=links` 查真正目標後改 catalog 標題）、3 部同頁內標題重複（自動補全形序號）。

## 目前剩下的 6 個警告（**不是 bug，是來源限制**）

`dengxizi 2/2`、`gongsun-longzi 6/7`、`kongcongzi 19/19`、`shenjian 5/9`、`fengsu-tongyi 4/85`、`shuijingzhu 18/137` 的章標籤是純數字。
原因：那些 Wikisource 子頁本身就叫「1」「2」「3」，頁內也沒有篇名標題可切。要修只能人工補篇名對照表——標註那幾部時再處理，不必現在做。

## 下一步

1. **標註管線**：以 human-questions-corpus 400 題當反向探針逐部跑。先做試點過的 2 部（孫子兵法、九章算術）當 ground truth
2. 產出 `annotations.json`，同時回填書級 `psych_survey`（`domains_hit` **與** `domains_null` 都要寫）
3. 每完成一批重跑 `build-index.py` 再 commit
4. phase 2 小學 5 部：等第一批標註管線跑順、有現成探針後，用同一套探針跑一次證否，成本極低
5. GitHub remote 尚未建立（`Hangsau/chinese-classics-corpus`），目前只有本地 commit

## 已知風險

- **ctext.org 是紅線**：明文禁自動批量下載。本庫現在完全不碰它
- **`expected_chapter_count` 已從粗估改成驗證後凍結的觀測值**，用途變成回歸護欄。之後若下載器行為改變導致章數變動，verify 會叫——那時要判斷是修好還是弄壞，**不要反射性再同步一次數字**
- **焦氏易林上游殘缺**：全書 64 卦，Wikisource 只有 4 個。已寫進 catalog `coverage_note`。expected=4 是「來源有多少」不是「全書多大」
- **`古三墳`、`竹書紀年（今本）`標 `contested`**：偽託／存疑，標註時要記版本立場
- **未涵蓋的第二批候選**：藝文類聚、太平廣記、太平御覽、通典、康熙字典、墨子閒詁、墨經校釋

## 已明確排除（不要再問一次）

| 書 | 去向 | 理由 |
|---|---|---|
| 爾雅 | religions-history `er-ya` 已收 | 不重複收，用 cross-ref 指過去。《釋親》例外抽取見 SCHEMA §3 |
| 四書章句集注、論語注疏、孝經注疏 | religions-history | 經注，屬「被當成經典」那一半 |
| 列仙傳、高士傳 | religions-history | 神仙傳記＝道教敘事 |
| 詩說 | religions-history | 詩經注 |
| 小說、正史 | 兩庫都不收 | 使用者明確排除 |
| 申不害 | 不收 | ctext 路線整條移除 |
| 移轉宗教庫既有文本過來 | 不做 | 會破 SHA-256 鏈、143 部完整三軸標籤、GitHub 歷史，收益近零 |

## 尚未做、不可當結論的推測

pilots 檔 §5 記了兩條：說文解字 540 部首是否構成一套世界分類、釋名聲訓是否編碼民俗世界觀。**兩者均未讀原文**，且這 5 部現在排 phase 2 還沒抓。用第一批的探針跑一次即可證否。
