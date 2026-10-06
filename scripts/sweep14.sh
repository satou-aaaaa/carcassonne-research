# depth=10 を基準に探索定数 c を調整する。基準=v6線形・12000回・depth=10・c=0.5（既定）
# 使い方: bash scripts/sweep14.sh   （PY=python, WORKERS=CPU数 を環境変数で上書き可）
PY=${PY:-python}
WORKERS=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
E=eval=models/eval_v6_lin.npy
B="fmcts:sims=12000,depth=10,$E"
for C in 0.3 0.8; do
  PYTHONIOENCODING=utf-8 $PY scripts/run_match.py "fmcts:sims=12000,depth=10,c=$C,$E" "$B" --seeds 30 --workers "$WORKERS" --log runs/sweep14.jsonl
done
