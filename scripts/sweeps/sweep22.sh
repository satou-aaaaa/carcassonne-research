# 方策ネット（models/nn_v1.npz）で探索の根を上位 topk 手に絞った最強設定を、絞らない最強設定（12000回・depth=10・v6）と比べる。
# topk=1 は「配置はネットだけで決め、ミープルだけ探索で決める」。各20局（シード700〜709）でふるい、良ければシードを足す。
# 中断に備えて10シードずつ実行し、終わった塊は飛ばす（ログは runs/sweep22_<設定>.jsonl に追記）。
# 使い方: bash scripts/sweeps/sweep22.sh "topk=1 topk=4 topk=8" "700"
cd "$(dirname "$0")/../.."  # どこから実行してもリポジトリ直下で動かす
PY=${PY:-python}
WORKERS=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
NN=${NN:-models/nn_v1.npz}
E=eval=models/eval_v6_lin.npy
B=${B:-"fmcts:sims=12000,depth=10,$E"}
for X in ${1:-topk=1 topk=4 topk=8}; do
  A="fmcts:sims=12000,depth=10,$E,nn=$NN,$X"
  tag=$(basename "$NN" .npz)_$(echo "$X" | tr -d '=,')${SUFFIX:-}
  for S in ${2:-700}; do
    out=runs/sweep22_${tag}_$S.out
    [ -s "$out" ] && continue
    PYTHONIOENCODING=utf-8 $PY scripts/run_match.py "$A" "$B" --seeds 10 --start $S --workers "$WORKERS" --log runs/sweep22_$tag.jsonl > "$out.tmp" && mv "$out.tmp" "$out"
  done
done
