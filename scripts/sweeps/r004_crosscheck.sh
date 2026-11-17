#!/usr/bin/env bash
# R-004: 独立した別実装（wingedsheep/carcassonne、MIT、版を固定）で同じ棋譜100局をたどり、得点を突き合わせる。
# 別実装のコードはリポジトリに取り込まず、実行のたびに一時フォルダへ clone する。
# research-run.yml から: bash scripts/sweeps/r004_crosscheck.sh（結果は $RESEARCH_OUT、無ければ runs/r004）。
# 別実装は1局が重い（1手ごとに盤全体を調べる）ので、START・GAMES で分けて並べて回せる（例 START=40025 GAMES=25）
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT=${RESEARCH_OUT:-runs/r004}
mkdir -p "$OUT"
REF=$(mktemp -d)
git clone --quiet https://github.com/wingedsheep/carcassonne.git "$REF"
git -C "$REF" checkout --quiet e80dbb429e0d74727d0df2038802a42188b6fc62
PYTHONIOENCODING=utf-8 ${PY:-python} scripts/crosscheck_wingedsheep.py --ref "$REF" \
  --games ${GAMES:-100} --start ${START:-40000} --out "$OUT/crosscheck.json" | tee "$OUT/summary.txt"
