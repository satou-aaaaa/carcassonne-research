#!/usr/bin/env bash
# R-013: 探索の根の値を教師に評価を学ぶ（Expert Iteration）を2回反復して、今のチャンピオンと比べる。
#   反復1: チャンピオン E0 の探索（2000回・depth=10）で自己対戦 GAMES 局 → 目標 root / mix / td（対照）で学ぶ
#          → それぞれ E0 と先後入れ替え 2×SEEDS 局
#   反復2: 反復1で勝率が一番良かった版 E1 で同じ数だけ自己対戦し直し、反復1と合わせたデータで学ぶ
#          （先生を固定しない）→ E0 と 2×SEEDS 局
# research-run.yml から: bash scripts/sweeps/r013_exit.sh（結果は $RESEARCH_OUT、無ければ runs/r013）
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT=${RESEARCH_OUT:-runs/r013}
mkdir -p "$OUT"
W=${WORKERS:-$(nproc 2>/dev/null || echo 4)}
PY=${PY:-python}
GAMES=${GAMES:-400}
SEEDS=${SEEDS:-100}
E0=models/eval_champion.npy
export PYTHONIOENCODING=utf-8
A=${AGENT:-fmcts:sims=2000,depth=10}

match() { # 名前 評価A 評価B 先頭シード
  $PY scripts/run_match.py "$A,eval=$2" "$A,eval=$3" --seeds "$SEEDS" --start "$4" --workers "$W" \
    --log "$OUT/$1.jsonl" | tee "$OUT/$1.txt"
}
rate() { $PY -c "import re,sys;print(re.search(r'勝率 ([0-9.]+)',open(sys.argv[1],encoding='utf-8').read()).group(1))" "$1"; }

[ -f "$OUT/d1.npz" ] || $PY scripts/exit_iter.py gen --sims "${GEN_SIMS:-2000}" --eval "$E0" --games "$GAMES" --seed 1 --workers "$W" --out "$OUT/d1.npz" | tee -a "$OUT/log.txt"
for t in root mix td; do
  $PY scripts/exit_iter.py fit --data "$OUT/d1.npz" --prior "$E0" --target "$t" --out "$OUT/w1_$t.npy" | tee -a "$OUT/log.txt"
  [ -f "$OUT/m1_$t.txt" ] || match "m1_$t" "$OUT/w1_$t.npy" "$E0" 9500
done
best=root
[ "$(rate "$OUT/m1_mix.txt")" \> "$(rate "$OUT/m1_root.txt")" ] && best=mix
echo "反復1の最良: $best" | tee -a "$OUT/log.txt"
E1="$OUT/w1_$best.npy"
[ -f "$OUT/d2.npz" ] || $PY scripts/exit_iter.py gen --sims "${GEN_SIMS:-2000}" --eval "$E1" --games "$GAMES" --seed 2 --workers "$W" --out "$OUT/d2.npz" | tee -a "$OUT/log.txt"
$PY scripts/exit_iter.py fit --data "$OUT/d1.npz" "$OUT/d2.npz" --prior "$E1" --target "$best" --out "$OUT/w2.npy" | tee -a "$OUT/log.txt"
[ -f "$OUT/m2.txt" ] || match m2 "$OUT/w2.npy" "$E0" 9600
[ -f "$OUT/m2_vs1.txt" ] || match m2_vs1 "$OUT/w2.npy" "$E1" 9700
