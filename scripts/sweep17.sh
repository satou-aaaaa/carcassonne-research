# 対戦数を増やした最終確認（各200局=100シード×先後、未使用のシード1000〜）。
# (1) 現在の最強（12000回・depth=10）vs 以前の最強（12000回・depth無し）
# (2) 現在の最強 vs 貪欲法
# 使い方: bash scripts/sweep17.sh
PY=${PY:-python}
WORKERS=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
E=eval=models/eval_v6_lin.npy
A="fmcts:sims=12000,depth=10,$E"
for B in "fmcts:sims=12000,$E" greedy; do
  PYTHONIOENCODING=utf-8 $PY scripts/run_match.py "$A" "$B" --seeds 100 --start 1000 --workers "$WORKERS" --log runs/sweep17.jsonl
done
