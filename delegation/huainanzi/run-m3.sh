#!/usr/bin/env bash
# 串行發包淮南子給 MiniMax-M3（claude-m3-lite，不吃 Claude 配額）。
# 每批上限 15 分鐘（timeout 900；2026-09-28 b05 曾無輸出卡 15 分鐘）。
# 每批：判讀 → accept.py 驗收 → 過了才 commit 並派下一批；失敗重試一次，再失敗就停。
#   bash delegation/huainanzi/run-m3.sh b01 b02 ...
set -u
REPO=/c/claudehome/projects/chinese-classics-corpus
cd "$REPO" || exit 1
D=delegation/huainanzi
export PYTHONIOENCODING=utf-8
for b in "$@"; do
  out="$D/out/$b.json"
  if [ -s "$out" ] && python $D/accept.py "$b" >/dev/null 2>&1; then
    echo "=== $b 已存在且驗收通過，跳過"; continue
  fi
  ok=0
  for try in 1 2; do
    rm -f "$out"
    echo "=== $b 第 $try 次 $(date +%H:%M:%S)"
    timeout 900 claude-m3-lite -p "$(cat <<PROMPT
你要替《淮南子》的一批段落做心理學領域標註。本次只處理 $b。工作目錄是 $REPO。

**立即執行，不要輸出計畫、不要等確認。這是非互動呼叫，沒有人會回你「開始」；沒寫出檔案就是失敗。**

步驟：
1. 用 Read 完整讀 $D/SPEC.md（判準唯一依據，特別是六個體例群的閘門、六條配套、硬規則第 7 條引句規則）。
2. 用 Read 讀 $D/$b.md，逐段判讀。
3. 用 Write 把結果寫成 $out，格式照 SPEC「輸出格式」。rows 必須涵蓋該批每一段，章名與 para_index 照抄。
4. 用 Bash 跑：PYTHONIOENCODING=utf-8 python $D/accept.py $b
   若印出 [FAIL] 或「引句不在本段」，照訊息修正 $out 後再跑一次，直到 0 FAIL。引句不符的修法是改成本段原文連續的原字，不要刪原文的引號。
5. 最後回報一行：accept.py 的最後一行輸出。

禁止：不要跑任何 git 指令；不要改 $out 以外的任何檔案（SPEC、批次檔、MANIFEST、translations/、別批輸出都不准碰）。
PROMPT
)" --max-turns 40 < /dev/null 2>&1 | tail -n 3
    if [ -s "$out" ] && python $D/accept.py "$b" | tail -1; then
      if python $D/accept.py "$b" >/dev/null 2>&1; then ok=1; break; fi
    fi
  done
  if [ $ok -ne 1 ]; then
    echo "!!! $b 兩次都沒通過驗收，停止發包"; python $D/accept.py "$b" | tail -8; exit 1
  fi
  if [ -n "$(git status --porcelain -- ':!'"$D"/out/"$b".json)" ]; then
    echo "!!! $b 執行期間動到了輸出檔以外的檔案，停止："; git status --porcelain -- ':!'"$D"/out/"$b".json; exit 1
  fi
  git add "$out" && git commit -q -m "huainanzi $b：minimax-m3 判讀回收（accept.py 0 FAIL）" && echo "=== $b commit 完成"
done
echo "=== 全部完成"
