#!/usr/bin/env bash
# 串行發包 codex 通讀一部書的若干批次，產出通讀報告的一個分段。
#
#   bash scripts/run-reading.sh <slug> <gNN> b01 b02 ...
#
# 產出 delegation/<slug>/reading/<gNN>.md。通讀報告只給位置與證據，不下最終判定；
# 判準與灰區裁定由規劃者寫進 SPEC.md。
#
# 三巨頭（zhanguoce 65 批、shuijingzhu、qunshu-zhiyao）單批太多，一次讀不完，
# 所以通讀本身也要切群。切群只影響報告分段，不影響後續發包的批次邊界。
#
# prompt 裡的靜默失效反例沿用 run-delegation.sh，不要精簡掉。
set -u
REPO=/c/claudehome/projects/chinese-classics-corpus
cd "$REPO" || exit 1

SLUG=${1:?用法: run-reading.sh <slug> <gNN> b01 b02 ...}
GROUP=${2:?缺群名}
shift 2
DIR="delegation/${SLUG}"
OUTDIR="${DIR}/reading"
OUT="${OUTDIR}/${GROUP}.md"
GATE_FILE="${DIR}/READING-GATE.md"
[ -f "$GATE_FILE" ] || { echo "找不到 ${GATE_FILE}（該書的通讀指引，由規劃者先寫）"; exit 1; }
mkdir -p "$OUTDIR"

if [ -s "$OUT" ]; then
  echo "=== ${SLUG}/${GROUP} 已存在，跳過 ==="
  exit 0
fi

FILES=""
for b in "$@"; do FILES="${FILES} ${DIR}/${b}.md"; done

echo "=== ${SLUG}/${GROUP} 開始 $(date +%H:%M:%S)：$* ==="
codex exec --sandbox danger-full-access --cd "$REPO" "$(cat <<PROMPT
你要替一部古籍做**通讀報告**（不是標註）。本次只處理一群：${SLUG} 的 ${GROUP}。

**直接執行，不要先提出計畫徵求確認。**這是非互動式呼叫，沒有人會回你「開始」；
你回問就等於整群白做。曾經有一次執行印出一份步驟計畫、結尾寫「確認後可以說
『開始』直接執行」然後結束，磁碟上沒有任何檔案。

步驟：
1. 先完整讀 ${GATE_FILE}。那份檔說明這部書要用哪一道閘門、有哪些已知陷阱、
   報告要長什麼樣。**它是本次交付的唯一格式與判準依據。**
2. 逐一完整讀這幾個批次檔（全讀，不抽樣）：
${FILES}
3. 按 ${GATE_FILE} 規定的章節結構，把報告寫成檔案 ${OUT}。
4. 寫完後自檢：把報告裡所有「」內的字串抽出來，逐條回上列批次檔做子字串比對，
   對不上的一律改掉或刪掉；章名也要逐條對拍。自檢結果寫進報告最後一節，
   自檢用的臨時腳本用畢刪除。
5. 再把 ${OUT} 讀回來，確認它真的存在、章節齊全、段數小計與批次檔一致。

本次交付物就是那個 .md 檔本身。另有一次執行把內容都想完了，卻只在回覆訊息裡
說「我正在寫入輸出檔」就結束，磁碟上一樣沒有檔案。先寫檔，再回報。

**你唯一可以建立或修改的檔案是 ${OUT}**（外加自己的臨時自檢腳本，用畢刪除）。
reading/ 底下其他群的報告是別的執行已經完成的成果，即使你覺得寫得不好也不准
改、不准重寫、不准重新排版。曾經有一個實例把別批的輸出整份改寫，那是靜默的
資料污染。

其他禁止事項：不要跑任何 git 指令；不要改 translations/ 底下任何檔案；不要改
${DIR}/ 的輸入 .md 與 MANIFEST.json；不要寫 SPEC.md 或任何 .json。
PROMPT
)" < /dev/null 2>&1 | tail -n 5

if [ -s "$OUT" ]; then
  echo "=== ${SLUG}/${GROUP} 完成 $(date +%H:%M:%S) $(wc -c < "$OUT") bytes ==="
else
  echo "=== ${SLUG}/${GROUP} 失敗：沒產出檔案 ==="
fi
