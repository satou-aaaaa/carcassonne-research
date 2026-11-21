#!/usr/bin/env bash
# R-018: 選び直しを1段深く（rr=2: 相手の返し手のあと自分の次の手まで、タイル種別で平均）を今の rr=1 と比べる。
# MODE=screen は 2000回・depth=10（rb=REPLY_BEAM）、MODE=strong は最強（12000回・depth=10・読み切り3枚）。
# 新しい山札（シード START から SEEDS 個×先後）。research-run.yml から:
#   MODE=strong START=10000 SEEDS=50 bash scripts/sweeps/r018_reply2.sh（結果は $RESEARCH_OUT、無ければ runs/r018）
set -euo pipefail
cd "$(dirname "$0")/../.."  # どこから実行してもリポジトリ直下で動かす
OUT=${RESEARCH_OUT:-runs/r018}
mkdir -p "$OUT"
W=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
RB=${REPLY_BEAM:-3}
if [ "${MODE:-strong}" = screen ]; then
  B="fmcts:sims=2000,depth=10,eval=models/eval_champion.npy,rsel=0.5,rk=6"
else
  B="fmcts:sims=12000,depth=10,eval=models/eval_champion.npy,rsel=0.5,rk=6,eg=3"
fi
PYTHONIOENCODING=utf-8 ${PY:-python} scripts/run_match.py "$B,rr=2,rb=$RB" "$B,rr=1" \
  --seeds "${SEEDS:-100}" --start "${START:-10000}" --workers "$W" --log "$OUT/m.jsonl" | tee "$OUT/m.txt"
