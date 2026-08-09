#!/usr/bin/env bash
# 串行發包 codex 判讀一部書的若干批次。
#
#   bash scripts/run-delegation.sh <slug> b01 b02 ...
#
# 取代 delegation/shishuo-xinyu/run-batches.sh 與 run-batches2.sh 這兩支寫死 slug 的版本
# （v1 另有 clobber 誤報的 bug，見 HANDOFF §靜默失效）。**那兩支已無用途，可刪；保留
# 只為留下事故現場對照。往後發包一律用本檔，不要再逐書複製。**
#
# prompt 裡的三段反例是 2026-08-09 世說新語 23 批實際踩到的三種 codex 靜默失效，
# 每一條都對應一次「exit 0 但磁碟上沒有正確資料」。不要精簡掉。
set -u
REPO=/c/claudehome/projects/chinese-classics-corpus
cd "$REPO" || exit 1

SLUG=${1:?用法: run-delegation.sh <slug> b01 b02 ...}
shift
DIR="delegation/${SLUG}"
OUT="${DIR}/out"
[ -f "${DIR}/SPEC.md" ] || { echo "找不到 ${DIR}/SPEC.md"; exit 1; }
mkdir -p "$OUT"

snapshot() {
  for f in "$OUT"/*.json; do [ -e "$f" ] && sha256sum "$f"; done
}

for b in "$@"; do
  out="${OUT}/${b}.json"
  if [ -s "$out" ]; then
    echo "=== ${SLUG}/${b} 已存在，跳過 ==="
    continue
  fi
  echo "=== ${SLUG}/${b} 開始 $(date +%H:%M:%S) ==="
  before=$(snapshot)
  codex exec --sandbox danger-full-access --cd "$REPO" "$(cat <<PROMPT
你要替一部古籍做段落級的心理學領域標註。本次只處理一批：${SLUG} 的 ${b}。

**直接執行，不要先提出計畫徵求確認。**這是非互動式呼叫，沒有人會回你「開始」；
你回問就等於整批白做。曾經有一次執行印出一份步驟計畫、結尾寫「確認後可以說
『開始』直接執行」然後結束，磁碟上沒有任何檔案。

步驟：
1. 先完整讀 ${DIR}/SPEC.md，那是判準的唯一依據。特別注意「唯一的通則性閘門」
   一節、該書特有的陷阱一節，以及硬規則裡關於領域數上限的那一條。
2. 讀 ${DIR}/${b}.md，逐段判讀。
3. 把結果寫成檔案 ${OUT}/${b}.json，格式見 SPEC「輸出格式」。
4. 寫完後把該檔讀回來，確認它真的存在、是合法 JSON、rows 數等於該批段數。

本次交付物就是那個 .json 檔本身。另有一次執行把所有段落都判完了，卻只在回覆
訊息裡說「我正在寫入輸出檔」就結束，磁碟上一樣沒有檔案。先寫檔，再回報。

**你唯一可以建立或修改的檔案是 ${OUT}/${b}.json。**
out/ 底下其他批次的輸出是別的執行已經完成並驗收過的成果，即使你覺得判得不好
也不准改、不准重判、不准重新排版。曾經有一個實例把別批的輸出整份改寫，那是
靜默的資料污染。

其他禁止事項：不要跑任何 git 指令；不要改 translations/ 底下任何檔案；不要改
${DIR}/ 的輸入 .md 與 MANIFEST.json。
PROMPT
)" 2>&1 | tail -n 5
  clobber=""
  while read -r h f; do
    # Git Bash 的 sha256sum 走 binary 模式，輸出是 `<hash> *<path>`。不剝掉那個星號，
    # 回查時就會找不到檔案、hash 取到空字串，於是每一個既存檔案都被判成被改動——
    # 偵測器無條件誤報等於沒有偵測器。2026-08-09 醫家三部發包時抓到。
    f=${f#\*}
    [ -z "$f" ] && continue
    [ "$f" = "$out" ] && continue
    now=$(sha256sum "$f" 2>/dev/null | cut -d' ' -f1)
    [ "$now" != "$h" ] && clobber="${clobber}${f}\n"
  done <<< "$before"
  if [ -n "$clobber" ]; then
    echo "!!! ${b} 執行期間改動了既有的別批輸出，請人工檢查："
    printf "%b" "$clobber"
  fi
  if [ -s "$out" ]; then
    echo "=== ${SLUG}/${b} 完成 $(date +%H:%M:%S) $(wc -c < "$out") bytes ==="
  else
    echo "=== ${SLUG}/${b} 失敗：沒產出檔案 ==="
  fi
done
echo "=== 全部結束 $(date +%H:%M:%S) ==="
