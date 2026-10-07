# 方策反復で学習した線形評価関数（v1〜v3）を使うMCTS vs ランダムロールアウトMCTS（時間をほぼ揃える）
cd "$(dirname "$0")/../.."  # どこから実行してもリポジトリ直下で動かす
BASE="fmcts:sims=2000"
for v in 1 3; do
  PYTHONIOENCODING=utf-8 "${PY:-python}" scripts/run_match.py "fmcts:sims=13000,eval=models/eval_v$v.npy" "$BASE" --seeds 30 --workers 11 --log runs/sweep6.jsonl
done
