# (1) v6 の重みを固定し、追加7特徴の重みだけを残差で学習した v7_res と v6 の比較
# (2) 報酬スケール60（sweep4 で強い傾向）を depth=10 の最強設定で再確認
# 使い方: bash scripts/sweeps/sweep17.sh
cd "$(dirname "$0")/../.."  # どこから実行してもリポジトリ直下で動かす
PY=${PY:-python}
WORKERS=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
S="fmcts:sims=12000,depth=10"
B="$S,eval=models/eval_v6_lin.npy"
for A in "$S,eval=models/eval_v7_res.npy" "$S,scale=60,eval=models/eval_v6_lin.npy"; do
  PYTHONIOENCODING=utf-8 $PY scripts/run_match.py "$A" "$B" --seeds 30 --start ${START:-300} --workers "$WORKERS" --log runs/sweep17.jsonl
done
