#!/usr/bin/env bash
# R-001: 終盤の厳密値で学んだ勝率型の評価（残り4枚以下だけ切り替え）vs 今のチャンピオン。探索は同じ。
# 標準（2000回）と最強（12000回・depth=10）で、各200局（シード9000〜9099×先後）。
# research-run.yml から: bash scripts/sweeps/r001_endgame_teacher.sh（結果は $RESEARCH_OUT、無ければ runs/r001）
set -euo pipefail
cd "$(dirname "$0")/../.."  # どこから実行してもリポジトリ直下で動かす
OUT=${RESEARCH_OUT:-runs/r001}
mkdir -p "$OUT"
W=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
R=rsel=0.5,rk=6,rr=1,eg=3
for lv in "standard sims=2000" "strong sims=12000,depth=10"; do
  set -- $lv
  PYTHONIOENCODING=utf-8 ${PY:-python} scripts/run_match.py \
    "fmcts:$2,eval=models/eval_eg_split.npy,$R" "fmcts:$2,eval=models/eval_eg_split_ctrl.npy,$R" \
    --seeds 100 --start 9000 --workers "$W" --log "$OUT/$1.jsonl" | tee "$OUT/$1.txt"
done
