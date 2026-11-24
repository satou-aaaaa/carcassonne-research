#!/usr/bin/env bash
# R-022: 選び直しの重み（標準の rsel、山札の残りで変える rsl）を今の設定と比べる。中身は r019.sh と同じ。
#   BASE=standard A="rsel=0.8,rk=6,rr=2,rb=1" B="rsel=0.5,rk=6,rr=2,rb=1" START=14000 SEEDS=100 bash scripts/sweeps/r022.sh
#   BASE=strong A="rsel=0.6,rsl=1.0,rk=6,rr=2,rb=3" B="rsel=0.8,rk=6,rr=2,rb=3" START=15000 SEEDS=25 bash scripts/sweeps/r022.sh
set -euo pipefail
RESEARCH_OUT=${RESEARCH_OUT:-runs/r022} exec bash "$(dirname "$0")/r019.sh"
