# HANDOFF — chinese-classics-corpus

> 狀態快照。行為規範見 [`CLAUDE.md`](./CLAUDE.md)，結構導航見 [`MAP.md`](./MAP.md)，資料契約見 [`SCHEMA.md`](./SCHEMA.md)。
> 最後更新：2026-07-28

## 現在在哪

**第一批 68 部全文已入庫。標註管線已跑通，ground truth 兩部完成。**

`verify.py`：68 部、10,553,141 bytes、**0 errors、6 warnings**。

| 部 | 段數 | 已判讀 | 命中領域 |
|---|---|---|---|
| `sunzi-bingfa` | 91 | 91 | 11／13（未命中 I、XIII） |
| `jiuzhang-suanshu` | 720 | 720 | 3／13（V 26 段、VIII 1 段、XII 1 段） |

其餘 66 部 `psych_survey` 仍是 `null`——依 SCHEMA §5，`null` 是「未通讀」不是「沒有」。

**兩部 ground truth 的意義**：孫子證明方法找得到東西（連自己試點都漏標 3 個領域），九章證明方法說得出「沒有」（692/720 段為空）。方向不同但錯法一致——兩次全文讀都只往「補上漏標」修，沒有一次是試點標了而全文推翻。

下一件事是把探針推到第三部，不是再擴收書目。

## 已完成

| 項目 | 檔案 | 說明 |
|---|---|---|
| 方法論試點 | `pilots/2026-07-28-sunzi-jiuzhang.md` | §1–5 是試點，**§6／§7 是全文讀後的修訂，以修訂為準**。§7 另記兩個 vocab 層發現（見下方「待使用者決定」） |
| 段落切分單一來源 | `scripts/corpus_text.py` | `make-scaffold` 產錨點、`verify` 驗錨點都用它。**兩邊算法若分家，para_index 會靜默漂移、每條標註指向錯段** |
| 標註骨架 | `scripts/make-scaffold.py` | 由本文生成錨點，人只填 null 欄位。手寫 `annotations.json` 是壞錨點的來源 |
| 標註 | `translations/{sunzi-bingfa,jiuzhang-suanshu}/annotations.json` | 811 段全數判讀完 |
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

## 待使用者決定（兩條都是九章全文讀之後才浮出來的）

1. **`discourse_mode` 缺「題例／worked instance」值**：九章 491/720 段判不出姿態，全是「今有……問……荅曰……」。既非命題也非規範，而 `formalization` 的定義（連 vocab 舉的例子都是「衰分術、均輸術」）只涵蓋「術曰」那 214 段。vocab 明定「新增值必須先在 pilots/ 驗證過才進本表」，所以現在只記錄、沒動表。**要驗的話，第三部該挑海島算經或孫子算經**（同樣題例密集），一次就能判斷這是九章特有還是算書通例。
2. **`Z-wisdom` 排除是否照舊**：九章全書思想密度最高的一段（〈方田〉割圓術劉徽注，談極限論證與「學者踵古，習其謬失」）零領域命中，因為它屬 `Z-wisdom` 支流，而 vocab 明文「不是 domain，不得填進 psych_domains」。這條排除本身沒問題，但現在有了實例：**它足以讓一整部書的結論從「有思想但不在 13 領域」被讀成「沒思想」**。判斷要不要在 SCHEMA 補一句提醒，或讓書級 `psych_survey` 多一個 `crosscurrents_hit` 欄位。

## 下一步

1. **推到第三部**：以 human-questions-corpus 400 題當反向探針。優先海島算經／孫子算經——同時能結掉上面第 1 條 vocab 問題
2. 流程固定：`make-scaffold.py` 產骨架 → 讀全文逐段填 → 回填書級 `psych_survey`（`domains_hit` **與** `domains_null` 都要寫）→ `verify.py` → `build-index.py` → commit + push
3. phase 2 小學 5 部：探針已現成，用同一套跑一次證否，成本極低
4. 6 個純數字章標籤的警告，等標到那幾部再人工補篇名對照表

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
