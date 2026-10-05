# 22特徴の線形/MLP評価関数（v6）と旧v3を、時間を揃えて（12000回≒0.66秒/手）ロールアウト版と対戦
BASE="fmcts:sims=2000"
for m in eval_v6_mlp eval_v6_lin eval_v5_mlp; do
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/run_match.py "fmcts:sims=12000,eval=models/$m.npy" "$BASE" --seeds 30 --workers 11 --log runs/sweep7.jsonl
done
