#!/usr/bin/env bash
# 串行派發世說新語批次給 codex。已存在的輸出檔跳過，中途斷掉可直接重跑。
#
# 每次呼叫前後對 out/ 全目錄取雜湊：曾經有一個實例把別批已完成的輸出整份重判
# 覆寫（2026-08-09，b22）。多鏈並行時這種改寫是靜默的，所以在這裡擋一道。
set -u
cd /c/claudehome/projects/chinese-classics-corpus || exit 1
OUT=delegation/shishuo-xinyu/out

snapshot() { find "$OUT" -name '*.json' -print0 2>/dev/null | sort -z | xargs -0 sha256sum 2>/dev/null; }

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

步驟：
1. 先完整讀 delegation/shishuo-xinyu/SPEC.md，那是判準的唯一依據。特別注意
   「唯一的通則性閘門（敘事體版本）」、「最大的風險：拿門類名當答案」、
   硬規則第 2 條（領域數預設一到兩個），以及末尾「試點校準後補的兩條」。
2. 讀 delegation/shishuo-xinyu/${b}.md，逐段判讀。
3. 把結果寫成檔案 delegation/shishuo-xinyu/out/${b}.json，格式見 SPEC「輸出格式」。
4. 寫完後把該檔讀回來，確認它真的存在、是合法 JSON、rows 數等於該批段數。

本次交付物就是那個 .json 檔本身。曾經有一次執行把所有段落都判完了，卻只在
回覆訊息裡說「我正在寫入輸出檔」就結束，磁碟上沒有任何檔案，整批白做。
請不要重蹈：先寫檔，再回報。

**你唯一可以建立或修改的檔案是 delegation/shishuo-xinyu/out/${b}.json。**
out/ 底下其他批次的輸出是別的執行已經完成並驗收過的成果，即使你覺得判得不好
也不准改、不准重判、不准重新排版。曾經有一個實例把 out/b22.json 整份改寫，
那是靜默的資料污染。

其他禁止事項：不要跑任何 git 指令；不要改 translations/ 底下任何檔案；不要改
delegation/shishuo-xinyu/ 的輸入 .md 與 MANIFEST.json。
PROMPT
)" 2>&1 | tail -n 5
  after=$(snapshot)
  clobber=$(diff <(echo "$before") <(echo "$after") | grep '^[<>]' | grep -v "${b}.json")
  if [ -n "$clobber" ]; then
    echo "!!! ${b} 執行期間動到了別批的輸出，請人工檢查："
    echo "$clobber"
  fi
  if [ -s "$out" ]; then
    echo "=== ${b} 完成 $(date +%H:%M:%S) $(wc -c < "$out") bytes ==="
  else
    echo "=== ${b} 失敗：沒產出檔案 ==="
  fi
done
echo "=== 全部結束 $(date +%H:%M:%S) ==="
