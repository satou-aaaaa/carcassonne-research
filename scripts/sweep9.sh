# 探索量のスケーリング: v6線形評価関数MCTSの 4倍(48000回) vs 12000回、12000回 vs 3000回
E=eval=models/eval_v6_lin.npy
PYTHONIOENCODING=utf-8 ${PY:-python} scripts/run_match.py "fmcts:sims=12000,$E" "fmcts:sims=3000,$E" --seeds 30 --workers "${WORKERS:-$(nproc 2>/dev/null || echo 4)}" --log runs/sweep9.jsonl
PYTHONIOENCODING=utf-8 ${PY:-python} scripts/run_match.py "fmcts:sims=48000,$E" "fmcts:sims=12000,$E" --seeds 30 --workers "${WORKERS:-$(nproc 2>/dev/null || echo 4)}" --log runs/sweep9.jsonl
