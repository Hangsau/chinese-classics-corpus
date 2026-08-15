# 導航地圖

> 冷啟動先讀本檔 §決策索引 + §踩雷點，別窮舉讀檔。狀態見 `HANDOFF.md`。

## 決策索引

| 要做什麼 | 先讀 |
|---|---|
| 判斷一部書該進本庫還是 religions-history | `CLAUDE.md` §與 religions-history 的分界 |
| 決定要不要收某部書 | `CLAUDE.md` §1（收錄只看三條：古典漢語／有乾淨全文／公有領域，**不看主題**） |
| 改標註欄位、加 `discourse_mode` 值 | `SCHEMA.md` §1–§2，改動前先在 `pilots/` 驗證 |
| 理解為什麼標註要下放到段落級 | `pilots/2026-07-28-sunzi-jiuzhang.md` §3–§4 |
| 改 downloader | `CLAUDE.md` §4 爬蟲倫理 + 本檔 §下載器結構陷阱（**五類已修過的問題，別退回去**） |
| 查某部書在不在清單、為何某部結構特殊 | `scripts/catalog/chinese-classics-ws.json`（73 條、實收 72 部，特殊處置寫在該部的 `structure_note` / `coverage_note` / `excluded_reason`） |
| 抓完驗證 | `PYTHONIOENCODING=utf-8 python scripts/verify.py`；重生索引 `... scripts/build-index.py` |
| 跑心理學標註 | 先讀 `SCHEMA.md` §3 分流 `text_role`；`reference` 預設不排批次，但**不得憑此宣告沒內容**（§3.1 釋名已證否） |
| 標一部新書 | **預設走發包**，完整八步寫在 `HANDOFF.md` §下一步第 3 條：`make-delegation-input.py` 切批 → 寫 `delegation/<slug>/SPEC.md` → **先發 b01 試點、校準結果補回 spec 才放行其餘批** → `check-delegation-out.py` 檢查 → `apply-delegation.py` 回填。不發包時才用本檔 §標註工作流的手工五步。**一部書若跨視窗換了判讀者（配額耗盡改派另一個模型），回填一律加 `--tagged-by-batch bNN=<model>` 逐批分離歸屬**——兩個判讀者記在同一個 `tagged_by` 底下等於偽造校準資料（管子 b24 立下，2026-08-11） |
| 寫發包 spec | 抄 `delegation/yanshi-jiaxun/SPEC.md` 的骨架：**13 領域分流表（哪類內容歸哪格，逐格指定）** ＋ 該書特有的陷阱與例外體例 ＋ 硬規則 ＋ 輸出格式。分流表不寫，領域區辨不會自己發生——顏氏家訓的 IV 86 > V 47 就是這樣拿到的。**規訓一律帶數字**（「預設一到兩個領域，第三個要寫得出拿掉它少講什麼」）；只寫「不要濫用」不會生效，世說新語 b01 就是這樣疊出 6/8 段三領域 |
| 串行發包 codex | `bash scripts/run-delegation.sh <slug> b01 b02 ...`（吃 slug 參數，**已取代 `delegation/shishuo-xinyu/run-batches{,2}.sh` 兩支寫死 slug 的版本，不要再逐書複製**）。它的 prompt 內含三條反例：不准先問「確認後開始」、交付物是檔案本身要讀回確認、只准寫自己那一批的 out 檔——**三條都是實際踩過的靜默失效，別精簡掉**（見 `HANDOFF.md` §靜默失效）。**clobber 偵測器 2026-08-09 才真正修好**——在那之前它因 Git Bash 的 `sha256sum` 輸出 `<hash> *<path>` 而無條件誤報，等於沒有偵測器 |
| 查 13 領域怎麼分／`discourse_mode` 八值定義 | `vocab/psych-domains.json`、`vocab/discourse-modes.json`（v0.2）。**友誼在 V 不在 III**；`Z-wisdom` 等 crosscurrents 不得填進 `psych_domains` |
| 判斷一段該不該給領域 | 論說／算書走 `CLAUDE.md` §2.1 **中性物件替換測試**（2026-08-09 九章重判 28→1 立下）；**敘事體走 §2.2「刪掉這一則，讀者少知道了什麼」閘門**（替換測試在軼事上失效，世說新語 1,132 段立下）；**博物誌／志怪走 §2.3「除了登錄一件東西之外還說了關於人的什麼」閘門**（神異經 61 段、洞冥記 63 段立下）；**醫書走 §2.4「除了病長什麼樣／該怎麼治之外還說了關於人的什麼」閘門**（難經 243 段、傷寒論 728 段、金匱要略 796 段立下，1,767 段中 98.6% 判空）；**兵書走 §2.5「怎麼打之外」閘門**（兵家五部 299 段立下，2026-08-10）；**法家走 §2.6「怎麼治之外」閘門**（慎子 75、商君書 125、諫逐客書 4 共 204 段立下、韓非子 781 段複驗，2026-08-10；判準是「文本有沒有自己把人是什麼樣的當成依據說出來」，**與 §2.5 恰好相反**——兵書拿仁義當工具判空，法家拿人性當依據要命中。**已知灰區在術治條文篇**：形名參同／控權操作算不算，韓非子〈揚榷〉／〈揚權〉跨批複本量到二元一致率 7／10，爭議時對照它。**已知漏判型態在數字密集／問答體**：管子〈事語〉[2] 的「倉廩實則知禮節」被同段的歲藏公式與十勝清單蓋掉，判空前要逐句掃人性斷言句，2026-08-11 立下。**同日在管子 b20–b23 複驗，rider 寫進 spec 後有效**：103 段中 51 段判空逐句掃完零漏判，而同一句話第三次出現的〈輕重甲〉[14] 由一個看不到前兩批的 API call 判出 V＋VII，與〈牧民〉[1] 相同。**跨批一致率的第二筆基準也在此**：管子〈國准〉／〈國準〉可對齊 2 組，二元閘門 2／2、domain 集合 1／2 相同，明顯優於〈揚榷〉／〈揚權〉的 7／10——**一致率是「體裁 × 灰區密度」的函數，不是判讀者素質，兩筆要一起讀**。**分型句的分界在依不依賴政策槓桿**：六韜〈練士〉的分型不靠任何政策故命中，管子〈揆度〉[1]〈輕重甲〉[7][8] 三條都掛在槓桿後面講誘因反應強度，2026-08-11 一併裁定維持判空；同日〈輕重戊〉[4][5]「金幣者，人之所重也」依同一條判空——「重」在輕重諸篇是價格術語，同「術數語彙在兵書裡是技術術語」）。六者都優先於「這段看起來有社會味」的直覺 |
| 寫 spec 時決定哪些領域要事先寫死 | `CLAUDE.md` §2.1 末三段（**替換測試的鏡像陷阱**，公孫龍子 2026-08-11 立下）。**spec 事先寫死哪一格，那一格就判對；沒寫的那格會出事**——同一本書 II 寫死了判出 0（全書談名實而該格掛零），IX 沒寫就在〈堅白論〉10 段撈了 5 段（目與手是偵測通道不是身體處境），補寫後 IX 5→0 且其餘五列位元組不變。發包前把該書最可能被詞面聯想撈到的兩三格逐一套替換測試，**命中與判空兩面都寫進 spec** |
| 處理有注本的書 | 注文算數（世說新語劉孝標注立下），但**注本不是均質的一層文本，統計要分注家算**：公孫龍子 17 個命中裡 10 個純由謝希深注成立、逢注幾乎不出斷言。reason 一律指名正文或注文並引該注句，`psych_survey.verdict` 寫明命中來自哪一注家——**作為「這個本子」的紀錄為真，作為「作者思想」為假**。另有一條判讀者自己長出、spec 尚未明文的分界值得抄進下一部注本書：注文的比擬轉寫判空、注文的主張才命中 |
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
vocab/             13 人生問題領域（psych-domains.json）與 discourse_mode 八值（discourse-modes.json v0.2）
                   ——標註判準的真相源，與 religions-history 共用，改動要兩邊同步
scripts/catalog/   書目 canonical（只有 *-ws.json；ctext 路線已整條移除）
scripts/corpus_text.py           段落切分單一來源（make-scaffold 與 verify 共用）
scripts/download-wikisource.py   下載器，含 --survey 預檢模式；natural_sort_key 會先把「卷篇第部回」
                                 後的中文數字轉阿拉伯數字（否則章序按 codepoint 排成一七三九二）；
                                 會跳過 catalog 裡標 excluded 的條目
scripts/make-scaffold.py         由本文生成標註骨架（錨點自動產，人只填 null）
scripts/annotate.py              回填工具：put()／span() 寫對照表，apply() 雙向檢查後落盤；
                                 `annotate.py stats <slug>` 直接吐 psych_survey 要的數字
scripts/verify.py                驗證，push 前必須全綠。含錨點漂移偵測 ＋ 索引新鮮度對拍
scripts/build-index.py           由 meta.json + annotations.json 生成兩層索引
translations/<slug>/
  ├── meta.json         書級 L1 + psych_survey
  ├── raw/original.txt  原文，唯讀（動了破 SHA-256）
  ├── raw/checksums.sha256
  └── annotations.json  段落級 L2 psych_domains + L3 discourse_mode
00-overview/       全部是生成物，不手改
  ├── INDEX.{json,md}     內容索引（書級）
  ├── DOMAINS.md          標籤索引總表 ＋ 缺口報告
  └── domains/<id>.{md,json}  每個領域一頁，段級反向索引
```

`translations/` 已有 **72 部**（phase 1 共 68 ＋ phase 2 小學 4：`shuowen-jiezi`／`shiming`／`fangyan`／`jijiupian`；`guangyun` 上游殘缺已在 catalog 標 `excluded`），`00-overview/` 已生成。`annotations.json` 目前 **38 部**（`sunzi-bingfa` 91 段、`jiuzhang-suanshu` 720 段、`haidao-suanjing` 24 段、`renwuzhi` 229 段、`qianfulun` 268 段、`yantielun` 346 段、`yanshi-jiaxun` 255 段、`shishuo-xinyu` 1,132 段、`shenyijing` 61 段、`dongmingji` 63 段、`gu-sanfen` 78 段、`nanjing` 243 段、`shanghanlun` 728 段、`jinkui-yaolue` 796 段、`lienuzhuan` 208 段、`shuowen-jiezi` 6,070 段、`shiming` 945 段、`fangyan` 385 段、`jijiupian` 282 段、`liutao` 60 段、`sima-fa` 67 段、`san-lue` 65 段、`wuzi` 43 段、`weiliaozi` 84 段、`shenzi` 75 段、`shangjunshu` 125 段、`jian-zhu-ke-shu` 4 段、`hanfeizi` 781 段、`guanzi` 668 段、`gongsun-longzi` 36 段、`yinwenzi` 80 段、`dengxizi` 38 段、`yuzi` 28 段、`sushu` 6 段、`zhongjing` 18 段、`xinxu` 218 段、`kongcongzi` 159 段、`shenjian` 105 段），共 **15,584 段**；**phase 2 小學四部、兵家五部（299 段）、法家三小部（204 段）、韓非子（781 段）、管子（668 段）與名家黃老小部四部（182 段）已全數標完**，**儒家著述組五部（506 段）已全數標完**；其餘 34 部的 `psych_survey` 仍是 `null`＝未通讀。**這個數字是寫入當時的宣稱，據此行動前先跑本節下方的段數速查指令確認。**

**查一個領域在全庫的段落，看 `00-overview/domains/<id>.md`，不要自己 grep `annotations.json`。**每頁按書分節，欄位是篇名／段序／姿態／摘句／判讀，另附「已通讀但本領域零命中」的書單——命中與零命中放在同一頁，是為了讓零不會被讀成沒人看過（SCHEMA §5）。`DOMAINS.md` 是總表加缺口報告（未標註的 34 部）。三份都由 `build-index.py` 一次生成，不會各自漂移；`verify.py` 每跑一次就對拍一次，過期即 error，所以這頁的數字與 `annotations.json` 不會脫節。

`delegation/` 是發包工作區，依書分目錄，一部書一個 slug 目錄（清單以 `ls delegation/` 為準，不在此列舉——列舉必然過期）。每個目錄含 `SPEC.md`（判準）、`bNN.md`（切好的批次輸入）、`MANIFEST.json`（錨點清單，回填時雙向對照）、`out/bNN.json`（外部 agent 的判讀結果）。**這些是過程檔不是 canonical**，canonical 是回填後的 `translations/<slug>/annotations.json`。

## 標註工作流（標一部書就照這五步走）

```bash
# 1. 產骨架（錨點自動生成，全欄位 null）
PYTHONIOENCODING=utf-8 python scripts/make-scaffold.py --slug <slug>

# 2. 先把骨架的章／段索引範圍印出來，當作待標清單的骨幹
PYTHONIOENCODING=utf-8 python -c "import json,collections;rows=json.load(open('translations/<slug>/annotations.json',encoding='utf-8'));d=collections.Counter(r['anchor']['chapter'] for r in rows);print(len(rows));[print(k,v) for k,v in d.items()]"
```

3. **讀全文**（`translations/<slug>/raw/original.txt`，用 Read 工具分段讀並帶行號），邊讀邊在心裡對齊步驟 2 的索引，產出「每段 → domains ｜ modes」的完整清單。

4. 建一次性的 `scripts/tmp_ann_<slug>.py`，只放資料：

```python
from annotate import *

c = "本議第一"
put(c, 1, ["V"], [NA])
put(c, 11, ["V"], [FO, P], note="均輸平準的運作機制")
span(c, 2, 10, ["V"], [P])

apply("<slug>")
```

跑 `PYTHONIOENCODING=utf-8 python scripts/tmp_ann_<slug>.py`，**跑完把 tmp 檔刪掉**。

5. `PYTHONIOENCODING=utf-8 python scripts/annotate.py stats <slug>` 取數字 → 回填 `meta.json` 的 `psych_survey` → `verify.py` → `build-index.py` → 對齊 HANDOFF／MAP → commit + push。

### 這一步會踩到的環境限制（都踩過）

- **`annotate.py` 的雙向 assert 是唯一的安全網**，別為了讓它過而改對照表以外的東西。骨架有段沒對照＝漏標；對照表有多餘鍵＝章名或索引打錯，兩者都會靜默產生錯位錨點。
- 章名在 `r["anchor"]["chapter"]`，**不是** `r["chapter"]`。
- **一次 Write 寫不完三百多段的對照表**（超出單次輸出上限）。先 Write 前幾篇，再用 Edit 逐塊接在後面。
- **bash heredoc（`cat > x.py <<'EOF'`）在本機會失敗**，一律用 Write／Edit 工具建檔。
- Bash 輸出超過約 30KB 會被轉存成檔案而不顯示；讀原文用 Read 工具的 `offset`／`limit`，別用 cat。
- Console 是 cp950，所有 Python 一律 `PYTHONIOENCODING=utf-8 python ...`。
- **排一部書進標註批次前先量段長中位數**（`split_paragraphs` 跑一次）。五部因上游 HTML 把整章包在單一 block 元素裡而「一章＝一段」：`heguanzi` 19 段中位 989 字、`sanzijing` 1 段 1,411 字、`yandanzi` 5 段中位 742、`zhonglun` 35 段中位 534、`guiguzi` 72 段中位 127（最長 2,917）；論說書正常值約 91 字（尹文子）。**重抓救不了**，`extract_main_text()` 沒有 `
` 可切。這五部暫緩，見 HANDOFF §已知風險
- commit 時出現 `CRLF will be replaced by LF` 是 `.gitattributes` 正常運作，**不要據此去 `git rm --cached`**（踩過一次，差點誤刪已標檔）。

## 下載器結構陷阱（六類已修過，改 downloader 前先看）

段落級錨點靠篇名（SCHEMA §4），以下每一類都會把錨點毀掉：

| 陷阱 | 判別 | 現行對策 |
|---|---|---|
| 抽取時丟掉篇名標題 | 一部書只回 1 章 | `extract_main_text` 收 h2/h3/h4 並前綴 `## ` |
| Wikisource 平行上傳（編號頁＋篇名頁並存） | bytes 與章數同時異常膨脹 | catalog `subpage_drop_pattern` + 抓取時內容雜湊去重 |
| 卷級子頁沒往下切到篇 | 章標籤全是「卷N」 | 子頁本文再切一層；例外用 `no_subpage_split`（竹書紀年，698 條紀事切下去全是「元年」互撞） |
| 重定向對只差一行標題 | 切分後才出現同文章節 | 切分**之後**再依本文雜湊去重，保留較具體的標籤 |
| **獨篇子頁：一卷只含一篇時篇名整個丟掉** | 章標籤是「卷第N」這種只有卷序沒有篇名的字串 | `split_by_headings` 要 ≥2 個標題才肯切，獨篇子頁因此保留卷名。`adopt_sole_heading()`：只有一個內層標題時不切、改拿它當標籤（2026-08-09）。`verify.py` 已加序號型標籤警告，未重抓的 8 部見 HANDOFF |
| **中文數字卷名按 codepoint 排序，全書章序亂掉** | 章序長成「卷第一 卷第三 卷第二 卷第四」 | `natural_sort_key` 原本只認阿拉伯數字。加 `_cn_to_int()` ＋ `_CN_ORDINAL`（只轉「卷篇第部回」後緊接的中文數字，不碰三國志、六韜這種書名數字）。**這一類不會被任何既有檢查抓到**——錨點是 `(chapter, para_index)` 所以標註仍對得上，`verify.py` 也不驗章序。新抓一部書要用眼睛掃一次章標籤順序（2026-08-09，洞冥記等 5 部） |

其他 catalog 旗標：`force_single_page`（正文在根頁）、`wikisource_subpages_explicit`（正文只在通常被當導航排除的 `/全覽`）、`excluded` ＋ `excluded_reason`（上游殘缺到不符收錄判準第二條，如 `guangyun`。**條目留著不刪**，否則下一個人只會再抓一次同一份殘本）。

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
- **`domains_hit` 一定要配 `domain_para_counts` 讀**。人物志命中 10／13 看似覆蓋廣，實際上四個領域吃掉絕大部分，IV 與 X 各只 1 段。潛夫論命中 12／13 更廣，但 V 一個領域就吃掉本文的 65%。鹽鐵論更是 **13／13 全覆蓋而 V 佔 88%、I 只 1 段**——全覆蓋可以純粹是體裁效應（60 篇辯論把話題掃遍一輪），與思想廣度無關。只看命中數會系統性高估一部書的覆蓋面。
- **論政書的 V 會吃掉八成以上，這是預期不是發現**。潛夫論 65%、鹽鐵論 88%。V 內部至少混了財政／邊防／選官／刑獄風俗四種東西，13 領域只給一格。要細分析論政書需要的是 V 的子軸，不是新領域。
- **辯論體要用三分法，否則全書非空即滿**：辯論**技術**→`Z-wisdom` 不標；辯論**倫理**當規範→VII；**進言不被聽見／被誤解**→III。三者原文外觀相近（鹽鐵論〈相刺〉7 vs〈論誹〉6 vs〈箴石〉2）。
- **XIII 的有無取決於「有沒有人替自身處境說話」，不取決於書的體裁**。孫子、潛夫論皆缺，曾據此推測是世俗實務書通例；鹽鐵論命中 3 段推翻了——它的文學／賢良是在野一方，必須替自己的貧賤辯護，才會轉向「人可以如何與之相處」。
- **對話體會製造第四種空白：對話機制**。鹽鐵論 22 段空白幾乎全是轉場套語與敘事引導，不是 Z-wisdom、不是真的沒有、也不是體例摻雜。另注意同一種場面調度會因字數落在 `corpus_text` 12 字下限兩側而分裂成「佔段落」與「不佔段落」兩類，計數時要當心。
- **`formalization` 不綁數學，也不綁制度**。人物志〈材能〉的「某能→某材→某任→某政」對照表、潛夫論〈考績〉的貢士賞罰遞加、〈夢列〉的十類夢判讀口訣，加上鹽鐵論的財政機制（〈本議〉均輸平準）、禮制曆法（〈論菑〉月令行刑時序）、判案準則（〈刑德〉春秋論心定罪），已橫跨算術／人事／財政／曆法／司法五類。它是形式**特徵**不是題材類別。判準只有一條：規範被寫成可執行程序。
- **高判空不等於判準保守，這件事已經被兩端夾住**。九章 99% 判空與列女傳 4% 判空（96% 命中、12／13）出自同一道閘門、同一發包管道、同一模型。**看到連續幾部判空率高時，先問是不是體裁，別急著鬆判準。**
- **`discourse_mode` 分佈不承載領域訊息**。傷寒論 `observation` 51% ＋ 98% 判空、列女傳 `observation` 53% ＋ 4% 判空；金匱四個 mode 接近均勻卻是本庫最高判空。**mode 是體裁指紋，不是命中訊號。**
- **試點的驗收條件要事先寫成幾格，不是整體印象**。列女傳只發一批試點就全書放行，依據是事前指定的三格：III 落點逐段回查原文、XII 不得被感生神話觸發、零段疊三領域。「看起來判得不錯」不算驗收。
- **空白段有三種成因，別混為一談**。① 被 `Z-wisdom` 吸走（九章割圓術、人物志方法論外殼）；② 真的沒有（海島算經）；③ 體例摻雜——那些段根本不是同一種文本（潛夫論的姓氏譜系 18 段＋附錄版本層 42 段）。三者在 `psych_domains: []` 裡長得一模一樣。
- **附錄／序跋／著錄要從分母裡拿掉**。潛夫論 268 段有 52 段（19%）是本傳、清人序跋、歷代著錄、佚文。算領域密度用本文段數，處置寫在該部 `psych_survey.structure_notes`。
- **不對 ctext.org 跑批量下載**。明文禁止，違者無預警封鎖；religions-history 已踩過 200/24h。本庫現在完全不碰 ctext。
- **`expected_chapter_count` 是驗證後凍結的觀測值，不是估計值**。verify 報章數不符＝結構真的變了，要判斷是修好還是弄壞，**不要反射性再同步一次數字**。
- **索引不新鮮 = verify 紅燈，不是待辦**。`verify.py` 每次都把 `00-overview/` 重生到 tempdir 對拍（時間戳行剔除後比對），差一個字就報 error。所以標完一部書忘了跑 `build-index.py`，push 前的關卡會擋下來——**不要手改 `00-overview/` 底下任何檔案讓它「看起來對」**，改了下次對拍照樣紅。
- **不動 `raw/original.txt`**。動了破 SHA-256。
- **`reference` 不等於沒內容**。原規則是「字書韻書不進標註管線」，2026-08-09 探針把它打成兩半：說文 99.3% 判空、方言 98.7%，但**釋名 100 段命中、12／13 領域**。差別在方法——登錄式字書只說「這個字是什麼意思」，聲訓必須說「為什麼這樣叫」，而理由就是對人的判斷。可以預設不排批次，但要說「沒有」一樣得通讀。
- **不用書級單一標籤打發內部異質性高的書**。孫子〈用間〉的認識論與〈九地〉的恐懼悖論掛同一個 `psych_tags` 會互相稀釋。
- **不把跨文本命題對撞塞進 metadata**。同舟共濟 vs Robbers Cave 是內容產出，歸分析層。
- **`null` 是「未標」不是「沒有」**。兩者混淆會讓負面結果失效。
- **同名異書不合併**：徐幹《中論》≠ 龍樹《中論》（後者在宗教庫）。
- Windows console 是 cp950，所有 Python 一律 `PYTHONIOENCODING=utf-8 python ...`；`.gitattributes` 強制 LF。
