# 学習型評価関数（線形）で葉を評価するMCTS vs ランダムロールアウトMCTS（時間をほぼ揃える）
BASE="fmcts:sims=2000"
for spec in "fmcts:sims=13000,eval=models/eval_v0.npy" "fmcts:sims=13000,eval=models/eval_v0.npy,c=0.2,scale=15"; do
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/run_match.py "$spec" "$BASE" --seeds 30 --workers 11 --log runs/sweep5.jsonl
done
