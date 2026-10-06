# 終盤のみフルロールアウト（残りタイルが late 枚以下）。基準=v6線形・12000回
# 使い方: bash scripts/sweep11.sh   （PY=python, WORKERS=CPU数 を環境変数で上書き可）
PY=${PY:-python}
WORKERS=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
E=eval=models/eval_v6_lin.npy
B="fmcts:sims=12000,$E"
for L in 12 24 36; do
  PYTHONIOENCODING=utf-8 $PY scripts/run_match.py "fmcts:sims=12000,late=$L,$E" "$B" --seeds 30 --workers "$WORKERS" --log runs/sweep11.jsonl
done
