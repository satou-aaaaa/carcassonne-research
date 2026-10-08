"""AIが相手の特徴を「完成不能」にする（妨害する）機会と、実際に妨害した回数を数える。

同じ評価関数のAI同士で対局させ、各手番で次を調べる:
  - 機会: ミープルなしで置く合法配置のうち、相手だけが持つ未完成の都市・道・修道院を完成不能にする
    （隣の空きマスに合う残りタイルを0枚にする）配置があるか。
  - 妨害: AIが選んだ配置がそのような配置だったか。
完成不能の判定は `fast_eval.min_fit`（評価関数の dead_* 特徴量と同じ）。

    py scripts/measure_blocking.py --eval models/eval_v9_block.npy --games 20 --sims 2000
"""

from __future__ import annotations

import argparse
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carcassonne.fast import (
    NT,
    SC_CUR,
    SC_OVER,
    SC_PL,
    apply_move,
    copy_state,
    gen_placements,
    seed_rng,
)
from carcassonne.fast_eval import min_fit
from carcassonne.fast_mcts import FastMCTSAgent


def owned_dead(S, T, P, player) -> int:
    """player だけが最多の、完成不能な特徴の数。"""
    mf = np.empty(NT * P, np.int32)
    min_fit(S, T, P, mf)
    meep = S[9]
    n = 0
    for r in np.nonzero(mf == 0)[0]:
        m = meep[r * 2 + player]
        if m > meep[r * 2 + 1 - player]:
            n += 1
    return n


def play(args):
    eval_path, sims, depth, seed = args
    agent = FastMCTSAgent(sims, rollout_depth=depth, eval_path=eval_path)
    fast, sc = agent.fast, agent.fast.scratch
    T, P = fast.T, fast.P
    rng = random.Random(seed)
    seed_rng(seed)
    deck = [i for i, t in enumerate(fast.ts.types) for _ in range(t.count)]
    deck.remove(fast.ts.start)
    rng.shuffle(deck)
    S = fast.new_game(deck)
    chances = blocks = moves = 0
    while not S[10][SC_OVER]:
        me = int(S[10][SC_PL])
        opp = 1 - me
        before = owned_dead(S, T, P, opp)
        sc.stamp_box[0] += 1
        k = gen_placements(
            S, T, S[10][SC_CUR], sc.stamp, sc.stamp_box[0], sc.out_cell, sc.out_g, False
        )
        cand = [(int(sc.out_cell[j]), int(sc.out_g[j])) for j in range(k)]
        good = set()
        for cell, g in cand:
            X = copy_state(S)
            apply_move(X, T, P, cell, g, -1, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
            if owned_dead(X, T, P, opp) > before:
                good.add((cell, g))
        cell, g, piece = agent.choose(S)
        moves += 1
        if good and len(good) < len(cand):  # どれを選んでも塞がる局面は数えない
            chances += 1
            blocks += (cell, g) in good
        apply_move(S, T, P, cell, g, piece, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
    return moves, chances, blocks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", required=True)
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--sims", type=int, default=2000)
    ap.add_argument("--depth", type=int, default=10)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    jobs = [(a.eval, a.sims, a.depth, a.seed + i) for i in range(a.games)]
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(play, jobs))
    moves, chances, blocks = (sum(r[i] for r in res) for i in range(3))
    print(
        f"{a.eval}: {a.games}局 {moves}手、妨害の機会 {chances}回、妨害した {blocks}回"
        f"（{blocks / max(chances, 1):.1%}）"
    )


if __name__ == "__main__":
    main()
