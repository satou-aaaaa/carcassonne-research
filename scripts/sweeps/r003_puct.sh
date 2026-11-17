#!/usr/bin/env bash
# R-003: 根の配置を PUCT（事前確率＝置いた直後の評価値の softmax）で選ぶ探索 vs 今の標準（2000回）。
# ふるい（シード7000〜7049×先後、各100局）で7通りを比べ、良かった設定を新しい山札（シード9000〜9199、400局）で確かめた。
# research-run.yml から: bash scripts/sweeps/r003_puct.sh（結果は $RESEARCH_OUT、無ければ runs/r003）
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT=${RESEARCH_OUT:-runs/r003}
mkdir -p "$OUT"
W=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
R=eval=models/eval_champion.npy,depth=0,rsel=0.5,rk=6,rr=1,eg=3
B="fmcts:sims=2000,$R"
for p in "puct=0.5" "puct=1" "puct=2" "puct=1,ptau=1" "puct=1,ptau=8" "puct=1,ptau=16" "puct=1,pply=2"; do
  n=$(echo "$p" | tr ',=' '__')
  PYTHONIOENCODING=utf-8 ${PY:-python} scripts/run_match.py "$B,$p" "$B" --seeds 50 --start 7000 \
    --workers "$W" --log "$OUT/screen_$n.jsonl" | tee "$OUT/screen_$n.txt"
done
PYTHONIOENCODING=utf-8 ${PY:-python} scripts/run_match.py "$B,puct=1,ptau=8" "$B" --seeds 200 --start 9000 \
  --workers "$W" --log "$OUT/confirm_ptau8.jsonl" | tee "$OUT/confirm_ptau8.txt"
