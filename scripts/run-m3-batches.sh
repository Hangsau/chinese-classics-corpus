#!/usr/bin/env bash
# 通用串行發包：把 delegation/<slug>/ 的批次逐一派給 MiniMax-M3（claude-m3-lite，不吃 Claude 配額）。
# 由 delegation/huainanzi/run-m3.sh 抽出，判準與驗收改讀該書的 SPEC.md 與 scripts/accept-batch.py。
# 每批上限 M3_TIMEOUT 秒（預設 900；論語 b02 52 段兩次逾時，大批次設 2700）。
# 每批輪數上限 M3_MAX_TURNS（預設 40；莊子 b08 41 段兩次用滿 40 輪只寫出 15 段——M3 改用暫存腳本逐段 append，大批次設 80）。
# 每批：判讀 → 驗收 → 過了才 commit 並派下一批；失敗重試一次，再失敗就停（不跳過）。
#   bash scripts/run-m3-batches.sh <slug> [b01 b02 ...]   # 省略批次＝MANIFEST 全部
set -u
REPO=/c/claudehome/projects/chinese-classics-corpus
cd "$REPO" || exit 1
SLUG=$1; shift
D=delegation/$SLUG
export PYTHONIOENCODING=utf-8
NAME=$(python -c "import json;print(json.load(open('translations/$SLUG/meta.json',encoding='utf-8'))['name_zh'])")
if [ $# -eq 0 ]; then
  set -- $(python -c "import json;print(' '.join(b['file'][:-3] for b in json.load(open('$D/MANIFEST.json',encoding='utf-8'))['batches']))")
fi
mkdir -p "$D/out"
for b in "$@"; do
  out="$D/out/$b.json"
  if [ -s "$out" ] && python scripts/accept-batch.py "$SLUG" "$b" >/dev/null 2>&1; then
    echo "=== $SLUG $b 已存在且驗收通過，跳過"; continue
  fi
  ok=0
  for try in 1 2; do
    rm -f "$out"
    echo "=== $SLUG $b 第 $try 次 $(date +%H:%M:%S)"
    timeout "${M3_TIMEOUT:-900}" claude-m3-lite -p "$(cat <<PROMPT
你要替《$NAME》的一批段落做心理學領域標註。本次只處理 $b。工作目錄是 $REPO。

**立即執行，不要輸出計畫、不要等確認。這是非互動呼叫，沒有人會回你「開始」；沒寫出檔案就是失敗。**

步驟：
1. 用 Read 完整讀 $D/SPEC.md（判準唯一依據，特別是體例群的閘門、配套、硬規則的引句規則）。
2. 用 Read 讀 $D/$b.md，逐段判讀。
3. 用 Write 把結果寫成 $out，格式照 SPEC「輸出格式」。rows 必須涵蓋該批每一段，章名與 para_index 照抄。
4. 用 Bash 跑：PYTHONIOENCODING=utf-8 python scripts/accept-batch.py $SLUG $b
   若印出 [FAIL] 或「引句不在本段」，照訊息修正 $out 後再跑一次，直到 0 FAIL。引句不符的修法是改成本段原文連續的原字，不要刪原文的引號。
5. 最後回報一行：accept-batch.py 的最後一行輸出。

禁止：不要跑任何 git 指令；不要改 $out 以外的任何檔案（SPEC、批次檔、MANIFEST、translations/、scripts/、別批輸出都不准碰）；不要建立任何暫存腳本或資料夾，直接用 Write 一次寫出完整 $out。
PROMPT
)" --max-turns "${M3_MAX_TURNS:-40}" < /dev/null 2>&1 | tail -n 3
    if [ -s "$out" ] && python scripts/accept-batch.py "$SLUG" "$b" >/dev/null 2>&1; then ok=1; break; fi
  done
  if [ $ok -ne 1 ]; then
    echo "!!! $SLUG $b 兩次都沒通過驗收，停止發包"; python scripts/accept-batch.py "$SLUG" "$b" | tail -8; exit 1
  fi
  if [ -n "$(git status --porcelain -- ':!'"$out")" ]; then
    echo "!!! $SLUG $b 執行期間動到了輸出檔以外的檔案，停止："; git status --porcelain -- ':!'"$out"; exit 1
  fi
  python scripts/accept-batch.py "$SLUG" "$b" | tail -1
  git add "$out" && git commit -q -m "$SLUG $b：minimax-m3 判讀回收（accept-batch 0 FAIL）" && echo "=== $SLUG $b commit 完成"
done
echo "=== $SLUG 全部完成"
