# TD(λ) で学び直した評価関数 v8 を、最強設定（12000回・depth=10）で v6 と比べる（各60局、シード400〜429）。
# 候補は scripts/train_td.py fit で作る（docs/EXPERIMENTS.md の「TD(λ)」の節）。
# 中断に備えて10シードずつ実行し、終わった塊は飛ばす（ログは runs/sweep19_<候補>.jsonl に追記）。
# 使い方: bash scripts/sweeps/sweep19.sh [候補名...]（既定: v8_td v8_tdpast）
cd "$(dirname "$0")/../.."  # どこから実行してもリポジトリ直下で動かす
PY=${PY:-python}
WORKERS=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
B="fmcts:sims=12000,depth=10,eval=models/eval_v6_lin.npy"
for C in ${@:-v8_td v8_tdpast}; do
  A="fmcts:sims=12000,depth=10,eval=models/eval_${C}.npy"
  for S in 400 410 420; do
    out=runs/sweep19_${C}_$S.out
    [ -s "$out" ] && continue
    PYTHONIOENCODING=utf-8 $PY scripts/run_match.py "$A" "$B" --seeds 10 --start $S --workers "$WORKERS" --log runs/sweep19_${C}.jsonl > "$out.tmp" && mv "$out.tmp" "$out"
  done
done
