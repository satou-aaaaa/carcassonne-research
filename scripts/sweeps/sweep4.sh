# fmcts(sims=2000) の既定設定を基準に、1パラメータずつ変えた設定が基準に勝つかを自己対戦で調べる
cd "$(dirname "$0")/../.."  # どこから実行してもリポジトリ直下で動かす
BASE="fmcts:sims=2000"
for spec in "fmcts:sims=2000,c=0.2" "fmcts:sims=2000,c=0.3" "fmcts:sims=2000,c=0.8" "fmcts:sims=2000,scale=15" "fmcts:sims=2000,scale=60" "fmcts:sims=2000,mp=0.15" "fmcts:sims=2000,mp=0.5" "fmcts:sims=2000,det=2" "fmcts:sims=2000,depth=20"; do
  PYTHONIOENCODING=utf-8 "${PY:-python}" scripts/run_match.py "$spec" "$BASE" --seeds 30 --workers 11 --log runs/sweep4.jsonl
done
