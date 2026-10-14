# first-play urgency（fpu、未展開の手の見込み値）を最強設定（12000回・depth=10・v6）と比べる。
# まず各20局（シード500〜509）でふるい、良さそうな値だけ 510〜529 を足して60局にする。
# 中断に備えて10シードずつ実行し、終わった塊は飛ばす（ログは runs/sweep20_fpu<値>.jsonl に追記）。
# 使い方: bash scripts/sweeps/sweep20.sh "0.3 0.6 1.0" "500"   # 値の一覧と開始シードの一覧
cd "$(dirname "$0")/../.."  # どこから実行してもリポジトリ直下で動かす
PY=${PY:-python}
WORKERS=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
E=eval=models/eval_v6_lin.npy
B="fmcts:sims=12000,depth=10,$E"
for F in ${1:-0.3 0.6 1.0}; do
  A="fmcts:sims=12000,depth=10,fpu=$F,$E"
  for S in ${2:-500}; do
    out=runs/sweep20_fpu${F}_$S.out
    [ -s "$out" ] && continue
    PYTHONIOENCODING=utf-8 $PY scripts/run_match.py "$A" "$B" --seeds 10 --start $S --workers "$WORKERS" --log runs/sweep20_fpu$F.jsonl > "$out.tmp" && mv "$out.tmp" "$out"
  done
done
