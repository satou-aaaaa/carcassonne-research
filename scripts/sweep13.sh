# 評価前ロールアウトの深さ（depth=6 が有効だったのでさらに深い値を探る）。基準=v6線形・12000回・depth無し
# 使い方: bash scripts/sweep13.sh   （PY=python, WORKERS=CPU数 を環境変数で上書き可）
PY=${PY:-python}
WORKERS=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
E=eval=models/eval_v6_lin.npy
B="fmcts:sims=12000,$E"
for D in 20 40; do
  PYTHONIOENCODING=utf-8 $PY scripts/run_match.py "fmcts:sims=12000,depth=$D,$E" "$B" --seeds 30 --workers "$WORKERS" --log runs/sweep13.jsonl
done
