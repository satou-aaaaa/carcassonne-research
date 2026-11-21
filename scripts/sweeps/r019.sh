#!/usr/bin/env bash
# R-019: 選び直し（rr=2）の設定と、4手目まで読む版（rr=3）を今の設定と比べる。
# A・B に run_match.py のエージェント指定（fmcts:... の後ろに足す部分）を渡す。BASE は探索の共通部分。
#   BASE=strong A="rsel=0.8,rk=6,rr=2,rb=3" B="rsel=0.5,rk=6,rr=2,rb=3" START=11000 SEEDS=50 bash scripts/sweeps/r019.sh
# 結果は $RESEARCH_OUT（無ければ runs/r019）。
set -euo pipefail
cd "$(dirname "$0")/../.."  # どこから実行してもリポジトリ直下で動かす
OUT=${RESEARCH_OUT:-runs/r019}
mkdir -p "$OUT"
W=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
case "${BASE:-strong}" in
  strong) P="fmcts:sims=12000,depth=10,eval=models/eval_champion.npy,eg=3" ;;   # 対戦ページの「最強」
  standard) P="fmcts:sims=2000,eval=models/eval_champion.npy,eg=3" ;;          # 対戦ページの「標準」
  screen) P="fmcts:sims=2000,depth=10,eval=models/eval_champion.npy" ;;
  *) echo "BASE は strong / standard / screen" >&2; exit 2 ;;
esac
PYTHONIOENCODING=utf-8 ${PY:-python} scripts/run_match.py "$P,$A" "$P,$B" \
  --seeds "${SEEDS:-50}" --start "${START:-11000}" --workers "$W" --log "$OUT/m.jsonl" | tee "$OUT/m.txt"
