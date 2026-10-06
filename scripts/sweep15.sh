# 特徴量を29個に増やした評価関数 v7 と、同じデータで22特徴のまま学習した対照 v7_lin22 を、v6 と比べる。
# いずれも最強設定（12000回・depth=10）。使い方: bash scripts/sweep15.sh
PY=${PY:-python}
WORKERS=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
S="fmcts:sims=12000,depth=10"
B="$S,eval=models/eval_v6_lin.npy"
for M in eval_v7_lin eval_v7_lin22; do
  PYTHONIOENCODING=utf-8 $PY scripts/run_match.py "$S,eval=models/$M.npy" "$B" --seeds 30 --start ${START:-200} --workers "$WORKERS" --log runs/sweep15.jsonl
done
