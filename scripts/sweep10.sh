# 探索の構造: 決定化の本数と、評価前の短いロールアウト（いずれも基準=v6線形・12000回・決定化1本）
# 使い方: bash scripts/sweep10.sh   （PY=python, WORKERS=CPU数 を環境変数で上書き可）
PY=${PY:-python}
WORKERS=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
E=eval=models/eval_v6_lin.npy
B="fmcts:sims=12000,$E"
for A in "fmcts:sims=12000,det=8,$E" "fmcts:sims=12000,det=24,$E" "fmcts:sims=12000,depth=6,$E"; do
  PYTHONIOENCODING=utf-8 $PY scripts/run_match.py "$A" "$B" --seeds 30 --workers "$WORKERS" --log runs/sweep10.jsonl
done
