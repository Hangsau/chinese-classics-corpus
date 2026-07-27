# SCHEMA — 資料契約

> 本檔是本庫的資料真相定義。**動任何 downloader 或標註管線之前先讀這份。**
> 設計依據見 [`pilots/2026-07-28-sunzi-jiuzhang.md`](./pilots/2026-07-28-sunzi-jiuzhang.md)（孫子兵法 × 九章算術雙本試點）。

## 0. 為什麼先寫 schema 再收文本

claudehome 知識規範第 1 條：**先設計檢索，再擴寫內容**。本庫的直接教訓是——試點證明既有的「領域標籤」單軸不足以區分《孫子》與《九章》對同一問題的處理方式。若先抓 74 部再補維度，等於全部重標。

## 1. 三層標註模型

| 層 | 欄位 | 粒度 | 說明 |
|---|---|---|---|
| L1 結構 | `category`、`language`、`era`、`text_role` | 書級 | 客觀事實，收錄當下即可填 |
| L2 領域 | `psych_domains` | **段落級** | 這段在回應哪個人生問題（13 領域，共享詞彙） |
| L3 姿態 | `discourse_mode` | **段落級** | 這段**用什麼方式**處理它（本庫新增，共享詞彙） |

L2 與 L3 **正交**：任一領域可搭配任一姿態。驗證案例——《儀禮·喪服》把哀悼期限按親等算成可推導制度，是 `formalization` × `X 無常·老·死·失去`；《九章·均輸》是 `formalization` × `V 公義·權力`。同姿態、不同領域，成立。

## 2. `discourse_mode` 受控詞彙（v0.1）

| 值 | 定義 | 判準 | 樣例 |
|---|---|---|---|
| `observation` | 陳述人實際如何 | 可被事實否證的描述句 | 孫子〈行軍〉徵候清單 |
| `proposition` | 主張某個因果或原理 | 有 A 故 B 的結構 | 孫子〈兵勢〉論勇怯生於勢 |
| `prescription` | 規定應該如何 | 祈使或當為句 | 孫子〈行軍〉論文武並用之令 |
| `formalization` | 把規範化成可計算程序 | 有可執行的算法／制度 | 九章衰分術、均輸術；儀禮喪服 |
| `narrative` | 用故事承載 | 有人物與情節 | 列女傳、福音書 |
| `ritual` | 用儀節承載 | 規定動作、時序、器物 | 禮記、利未記 |
| `expression` | 第一人稱抒發而非第三人稱描述 | 說話者即當事人 | 楚辭、詩篇 |

**紀律**：
- 一個段落可多標（常見組合：`proposition` + `prescription`）
- 判不出來就留 `null`。**`null` 代表「未標」，不代表「沒有」**
- 新增值必須先在 pilot 驗證，經確認才進正式詞彙表（依 knowledge-hub 規則，未定案關係一律 `proposed`）

### 為什麼不叫 `stance`
`stance` 在 NLP 有既定意義（stance detection＝支持／反對的立場），會誤導。定名 `discourse_mode`。

## 3. `text_role` 擴充

沿用 religions-history 既有 enum，**新增一個值**：

| 值 | 說明 | 本庫處置 |
|---|---|---|
| `original` | 成書原典 | 進標註管線 |
| `translation` / `transliteration` / `contested` | 見 religions-history 定義 | 同左 |
| **`reference`**（新增） | 語言基礎設施而非內容：字書、韻書、類書 | **排除在心理學標註管線外**，改掛 tagger 的同義詞資源層 |

`reference` 適用：說文解字、釋名、方言、急就篇、廣韻。理由——這些是受控詞彙表本身，硬跑標註只會產出噪音；真價值在於替古典漢語標註做**術語正規化**。

**例外抽取**：`reference` 文本中若有整篇構成內容的，單獨抽出標註。已知案例：《爾雅·釋親》是完整親屬稱謂系統（宗族／母黨／妻黨／婚姻四類），屬 `formalization` × `IV 家庭與傳承`。（爾雅本身已收在 religions-history `er-ya`，本庫不重複收，用 cross-ref 指過去。）

## 4. 段落級標註的落地形式

不動 `raw/original.txt`（動了會破 SHA-256）。標註另存：

```
translations/<slug>/
├── meta.json              ← 書級 L1（沿用 religions-history meta_template schema）
├── raw/original.txt       ← 原文，唯讀
├── raw/checksums.sha256
└── annotations.json       ← 段落級 L2 + L3
```

`annotations.json` 每筆：

```json
{
  "para_id": "sunzi-bingfa#07-p06",
  "anchor": {"chapter": "軍爭第七", "para_index": 6},
  "psych_domains": ["VI"],
  "discourse_mode": ["proposition", "prescription"],
  "confidence": "high",
  "note": "士氣的時間曲線與四治（氣心力變）",
  "tagged_by": "model-id",
  "tagged_at": "2026-07-28T00:00:00+08:00"
}
```

`anchor` 用章名 + 段序，**不用字元 offset**（原文若換版本，offset 全失效）。

## 5. 負面結果必須入庫

書級 `meta.json` 增列：

```json
"psych_survey": {
  "surveyed_at": "2026-07-28",
  "domains_hit": ["V"],
  "domains_null": ["I","II","III","IV","VI","VII","VIII","IX","X","XI","XII","XIII"],
  "verdict": "低密度：全書無任何人物內在狀態描寫；命中僅來自分配規範的形式化"
}
```

**理由**：九章算術 13 領域只命中 1 個。這個「幾乎全空」的結果本身是資料——不記錄，半年後又會有人憑書名猜「算書應該有吧」而重跑一次。方法能說「沒有」，才證明它不是在幻覺。

## 6. 跨庫對齊

| 項目 | 位置 | 規則 |
|---|---|---|
| 13 人生問題領域 | 共享層（不放任一庫內） | 兩庫引用同一份 |
| `discourse_mode` 詞彙 | 共享層 | 同上 |
| `semantic_tags` | **各庫自有** | 比較宗教學 14 類不適用本庫；本庫另立（治理／謀略／名辯／術數／醫理／語言…） |
| 跨庫引用 | `專案:slug`，如 `religions-history:tao-te-ching` | 依 knowledge-hub 規則，跨庫關係預設 `proposed`，不因名稱相似即合併 |

**回填策略（重要）**：religions-history 現況為 4683 部中僅 143 部有完整三軸標籤，全庫回填 `discourse_mode` 不可行也不必要。做法是——本庫從第一天標；宗教庫隨日常標註自然長出，不另開回填工程；缺欄位以 `null` 表示且不算驗收失敗（hub export 走 `schema_version` minor bump + 相容策略）。
