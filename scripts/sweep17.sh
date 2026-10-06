# 対戦数を増やした最終確認（各200局=100シード×先後、未使用のシード1000〜1099）。
# (1) 現在の最強（12000回・depth=10）vs 以前の最強（12000回・depth無し）
# (2) 現在の最強 vs 貪欲法
# 中断に備えて20シードずつ実行し、終わった塊は飛ばす（ログは runs/sweep17_{nodepth,greedy}.jsonl に追記）。
# 使い方: bash scripts/sweep17.sh
PY=${PY:-python}
WORKERS=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
E=eval=models/eval_v6_lin.npy
A="fmcts:sims=12000,depth=10,$E"
for B in "fmcts:sims=12000,$E" greedy; do
  tag=$([ "$B" = greedy ] && echo greedy || echo nodepth)
  for S in 1000 1020 1040 1060 1080; do
    out=runs/sweep17_${tag}_$S.out
    [ -s "$out" ] && continue
    PYTHONIOENCODING=utf-8 $PY scripts/run_match.py "$A" "$B" --seeds 20 --start $S --workers "$WORKERS" --log runs/sweep17_${tag}.jsonl > "$out.tmp" && mv "$out.tmp" "$out"
  done
done
