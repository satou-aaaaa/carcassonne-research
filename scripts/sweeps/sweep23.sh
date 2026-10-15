# 2026-10-15「さらに強く」: 候補 A と基準 B を10シード（20局）ずつの塊で対戦させる（終わった塊は飛ばす）。
# 使い方: bash scripts/sweeps/sweep23.sh <タグ> "<A>" "<B>" "<先頭シードの並び>" [出力先]
# 例: bash scripts/sweeps/sweep23.sh rs1 "fmcts:sims=12000,depth=10,eval=models/eval_v9_block.npy,rs=1" \
#       "fmcts:sims=12000,depth=10,eval=models/eval_v9_block.npy" "7000 7010 7020"
cd "$(dirname "$0")/../.."  # どこから実行してもリポジトリ直下で動かす
PY=${PY:-python}
WORKERS=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
tag=$1
A=$2
B=$3
OUT=${5:-runs/sweep23}
mkdir -p "$OUT"
for S in $4; do
  out=$OUT/${tag}_$S.out
  [ -s "$out" ] && continue
  PYTHONIOENCODING=utf-8 $PY scripts/run_match.py "$A" "$B" --seeds 10 --start "$S" --workers "$WORKERS" --log "$OUT/$tag.jsonl" > "$out.tmp" && mv "$out.tmp" "$out"
done
