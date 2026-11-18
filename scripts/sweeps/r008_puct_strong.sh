#!/usr/bin/env bash
# R-008: R-003 で良かった PUCT（puct=1・温度8）を最強の探索（12000回・depth=10・選び直し・読み切り）に足して確かめる。
# 新しい山札（シード9200〜9399×先後、400局）。START・SEEDS で分けて並べて回せる（例 START=9300 SEEDS=100）。
# research-run.yml から: bash scripts/sweeps/r008_puct_strong.sh（結果は $RESEARCH_OUT、無ければ runs/r008）
set -euo pipefail
cd "$(dirname "$0")/../.."  # どこから実行してもリポジトリ直下で動かす
OUT=${RESEARCH_OUT:-runs/r008}
mkdir -p "$OUT"
W=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
B="fmcts:sims=12000,depth=10,eval=models/eval_champion.npy,rsel=0.5,rk=6,rr=1,eg=3"
PYTHONIOENCODING=utf-8 ${PY:-python} scripts/run_match.py "$B,puct=1,ptau=8" "$B" \
  --seeds "${SEEDS:-200}" --start "${START:-9200}" --workers "$W" --log "$OUT/confirm.jsonl" | tee "$OUT/confirm.txt"
