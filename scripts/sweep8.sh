# 現時点で最強の設定（v6線形評価関数、12000回/手）を貪欲法・ロールアウト版（5000回,c=0.3）と対戦
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/run_match.py "fmcts:sims=12000,eval=models/eval_v6_lin.npy" greedy --seeds 30 --workers 11 --log runs/sweep8.jsonl
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/run_match.py "fmcts:sims=12000,eval=models/eval_v6_lin.npy" "fmcts:sims=5000,c=0.3" --seeds 30 --workers 11 --log runs/sweep8.jsonl
