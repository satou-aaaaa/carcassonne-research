cd "$(dirname "$0")/../.."  # どこから実行してもリポジトリ直下で動かす
for spec in "fmcts:sims=1000" "fmcts:sims=5000" "fmcts:sims=5000,c=0.3" "fmcts:sims=5000,c=1.0"; do
  PYTHONIOENCODING=utf-8 "${PY:-python}" scripts/run_match.py "$spec" greedy --seeds 20 --workers 11
done
