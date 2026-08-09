#!/usr/bin/env bash
# run-batches.sh 的修正版。兩處差異：
#   1. prompt 明寫「不要先徵求確認」——b03 那次 codex 印出一份計畫就停下來問
#      「確認後可以說『開始』」，然後結束，磁碟上沒有檔案。
#   2. 覆寫偵測只比對「執行前就存在」的檔案。舊版對整個 out/ 取雜湊，別條鏈
#      同時新建的檔案會被誤報成覆寫，全是假警報。
set -u
cd /c/claudehome/projects/chinese-classics-corpus || exit 1
OUT=delegation/shishuo-xinyu/out

snapshot() {
  for f in "$OUT"/*.json; do [ -e "$f" ] && sha256sum "$f"; done
}

for b in "$@"; do
  out="$OUT/${b}.json"
  if [ -s "$out" ]; then
    echo "=== ${b} 已存在，跳過 ==="
    continue
  fi
  echo "=== ${b} 開始 $(date +%H:%M:%S) ==="
  before=$(snapshot)
  codex exec --sandbox danger-full-access --cd /c/claudehome/projects/chinese-classics-corpus "$(cat <<PROMPT
你要替《世說新語》做段落級的心理學領域標註。本次只處理一批：${b}。

**直接執行，不要先提出計畫徵求確認。**這是非互動式呼叫，沒有人會回你「開始」；
你回問就等於整批白做。曾經有一次執行印出一份步驟計畫、結尾寫「確認後可以說
『開始』直接執行」然後結束，磁碟上沒有任何檔案。

步驟：
1. 先完整讀 delegation/shishuo-xinyu/SPEC.md，那是判準的唯一依據。特別注意
   「唯一的通則性閘門（敘事體版本）」、「最大的風險：拿門類名當答案」、
   硬規則第 2 條（領域數預設一到兩個），以及末尾「試點校準後補的兩條」。
2. 讀 delegation/shishuo-xinyu/${b}.md，逐段判讀。
3. 把結果寫成檔案 delegation/shishuo-xinyu/out/${b}.json，格式見 SPEC「輸出格式」。
4. 寫完後把該檔讀回來，確認它真的存在、是合法 JSON、rows 數等於該批段數。

本次交付物就是那個 .json 檔本身。另有一次執行把所有段落都判完了，卻只在回覆
訊息裡說「我正在寫入輸出檔」就結束，磁碟上一樣沒有檔案。先寫檔，再回報。

**你唯一可以建立或修改的檔案是 delegation/shishuo-xinyu/out/${b}.json。**
out/ 底下其他批次的輸出是別的執行已經完成並驗收過的成果，即使你覺得判得不好
也不准改、不准重判、不准重新排版。曾經有一個實例把 out/b22.json 整份改寫，
那是靜默的資料污染。

其他禁止事項：不要跑任何 git 指令；不要改 translations/ 底下任何檔案；不要改
delegation/shishuo-xinyu/ 的輸入 .md 與 MANIFEST.json。
PROMPT
)" 2>&1 | tail -n 5
  clobber=""
  while read -r h f; do
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
    echo "=== ${b} 完成 $(date +%H:%M:%S) $(wc -c < "$out") bytes ==="
  else
    echo "=== ${b} 失敗：沒產出檔案 ==="
  fi
done
echo "=== 全部結束 $(date +%H:%M:%S) ==="
