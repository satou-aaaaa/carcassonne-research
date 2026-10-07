cd "$(dirname "$0")/../.."  # どこから実行してもリポジトリ直下で動かす
for spec in "mcts:sims=400,det=1,fact=0" "mcts:sims=400,det=1,fact=1" "mcts:sims=400,det=1,fact=1,depth=12" "mcts:sims=1000,det=1,fact=1"; do
  PYTHONIOENCODING=utf-8 "${PY:-python}" scripts/run_match.py "$spec" greedy --seeds 12 --workers 11
done
