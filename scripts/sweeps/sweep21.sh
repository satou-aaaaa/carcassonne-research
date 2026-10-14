# 評価値順の展開（pv）と first-play urgency（fpu）の組合せを、最強設定（12000回・depth=10・v6）と比べる。
# まず各20局（シード600〜609）でふるい、良さそうな組合せだけシードを足す。
# 中断に備えて10シードずつ実行し、終わった塊は飛ばす（ログは runs/sweep21_<設定>.jsonl に追記）。
# 使い方: bash scripts/sweeps/sweep21.sh "pv=50,fpu=0.3 pv=50,fpu=0.6" "600 610 620"
cd "$(dirname "$0")/../.."  # どこから実行してもリポジトリ直下で動かす
PY=${PY:-python}
WORKERS=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
E=eval=models/eval_v6_lin.npy
B="fmcts:sims=12000,depth=10,$E"
for X in ${1:-pv=50,fpu=0.3 pv=50,fpu=0.6 pv=200,fpu=0.6}; do
  A="fmcts:sims=12000,depth=10,$X,$E"
  tag=$(echo "$X" | tr -d '=,')
  for S in ${2:-600}; do
    out=runs/sweep21_${tag}_$S.out
    [ -s "$out" ] && continue
    PYTHONIOENCODING=utf-8 $PY scripts/run_match.py "$A" "$B" --seeds 10 --start $S --workers "$WORKERS" --log runs/sweep21_$tag.jsonl > "$out.tmp" && mv "$out.tmp" "$out"
  done
done
