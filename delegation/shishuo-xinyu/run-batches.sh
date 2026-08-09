#!/usr/bin/env bash
# 串行派發世說新語剩餘批次給 codex。已存在的輸出檔跳過，中途斷掉可直接重跑。
set -u
cd /c/claudehome/projects/chinese-classics-corpus || exit 1

for b in "$@"; do
  out="delegation/shishuo-xinyu/out/${b}.json"
  if [ -s "$out" ]; then
    echo "=== ${b} 已存在，跳過 ==="
    continue
  fi
  echo "=== ${b} 開始 $(date +%H:%M:%S) ==="
  codex exec --sandbox danger-full-access --cd /c/claudehome/projects/chinese-classics-corpus "$(cat <<PROMPT
你要替《世說新語》做段落級的心理學領域標註。

步驟：
1. 先完整讀 delegation/shishuo-xinyu/SPEC.md，那是判準的唯一依據。特別注意
   「唯一的通則性閘門（敘事體版本）」、「最大的風險：拿門類名當答案」，
   以及末尾「試點（b22〈雅量〉）校準後補的兩條」。
2. 讀 delegation/shishuo-xinyu/${b}.md，逐段判讀。
3. 把結果寫成檔案 delegation/shishuo-xinyu/out/${b}.json，格式見 SPEC「輸出格式」。
4. 寫完後把該檔讀回來，確認它真的存在、是合法 JSON、rows 數等於該批段數。

本次交付物就是那個 .json 檔本身。曾經有一次執行把所有段落都判完了，卻只在
回覆訊息裡說「我正在寫入輸出檔」就結束，磁碟上沒有任何檔案，整批白做。
請不要重蹈：先寫檔，再回報。

參考已完成的 delegation/shishuo-xinyu/out/b22.json 可看實際輸出長相，但
**判準以 SPEC 為準，不要模仿 b22 的領域分佈**（b22 的 VI 偏高，SPEC 末尾那
兩條就是為了修正它）。

禁止事項：不要跑任何 git 指令；不要改 translations/ 底下任何檔案；不要改
delegation/shishuo-xinyu/ 的輸入 .md 與 MANIFEST.json；只寫 out/ 底下的輸出檔。
PROMPT
)" 2>&1 | tail -5
  if [ -s "$out" ]; then
    echo "=== ${b} 完成 $(date +%H:%M:%S) $(wc -c < "$out") bytes ==="
  else
    echo "=== ${b} 失敗：沒產出檔案 ==="
  fi
done
echo "=== 全部結束 $(date +%H:%M:%S) ==="
