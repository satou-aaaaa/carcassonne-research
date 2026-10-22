"""gen386 の自己対戦の棋譜（山札・指し手）と、根の探索統計（訪問数・平均報酬）を保存する。"""

import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from carcassonne.fast import SC_OVER, SC_S0, SC_S1, apply_move, random_move, seed_rng
from carcassonne.fast_mcts import FastMCTSAgent, search_stats

MAXM = 80


def play(args):
    kw, n, seed, eps = args
    ag = FastMCTSAgent(**kw)
    f = ag.fast
    T, P, sc = f.T, f.P, f.scratch
    rng = random.Random(seed)
    seed_rng(seed)
    base = [i for i, t in enumerate(f.ts.types) for _ in range(t.count)]
    base.remove(f.ts.start)
    decks = np.zeros((n, len(base)), np.int8)
    moves = np.full((n, MAXM, 3), -1, np.int32)
    nm = np.zeros(n, np.int32)
    q = np.full((n, MAXM), np.nan, np.float32)
    score = np.zeros((n, 2), np.int32)
    pc, pg, pv, pm = [], [], [], []  # 方策（根の配置ごとの訪問数）: 対局×手番ごと
    for gi in range(n):
        deck = base[:]
        rng.shuffle(deck)
        decks[gi] = deck
        S = f.new_game(deck)
        k = 0
        while not S[10][SC_OVER]:
            cells, gs, a1, w1, a2, _w2 = search_stats(
                S,
                T,
                P,
                ag.n_sims,
                1,
                ag.c,
                ag.reward_scale,
                ag.meeple_prob,
                ag.rollout_depth,
                sc.stamp,
                sc.stamp_box,
                sc.out_cell,
                sc.out_g,
                sc.free,
                sc.rec,
                ag.eval_w,
                ag.eval_mode,
                ag.fbuf,
                0,
                -1.0,
                0,
                np.zeros(0, np.int64),
            )
            bk = int(np.argmax(a1))
            q[gi, k] = w1[bk] / max(a1[bk], 1)
            pc.append(cells.astype(np.int32))
            pg.append(gs.astype(np.int16))
            pv.append(a1.astype(np.int32))
            pm.append((gi, k))
            if rng.random() < eps:
                cell, g, piece = random_move(
                    S, T, P, 0.3, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, sc.free
                )
            else:
                top = a1.max()
                cands = np.flatnonzero(a1 == top)
                bk = cands[rng.randrange(len(cands))]
                cell, g = cells[bk], gs[bk]
                piece = int(np.argmax(a2[bk])) - 1
            moves[gi, k] = (cell, g, piece)
            k += 1
            apply_move(S, T, P, cell, g, piece, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
        nm[gi] = k
        score[gi] = (S[10][SC_S0], S[10][SC_S1])
    lens = np.array([len(c) for c in pc], np.int32)
    return {
        "deck": decks,
        "moves": moves,
        "nmoves": nm,
        "q": q,
        "score": score,
        "pol_len": lens,
        "pol_cell": np.concatenate(pc),
        "pol_g": np.concatenate(pg),
        "pol_v": np.concatenate(pv),
        "pol_key": np.array(pm, np.int32),
    }


def main():
    sims, start, nchunks, per, workers = (int(a) for a in sys.argv[1:6])
    kw = {"n_sims": sims, "rollout_depth": 10, "eval_path": "runs/az/gen386.npy"}
    jobs = [
        (kw, per, s, 0.05)
        for s in range(start, start + nchunks)
        if not Path(f"runs/az/rec/r{s}.npz").exists()
    ]
    with ProcessPoolExecutor(workers) as ex:
        t = time.time()
        for j, d in zip(jobs, ex.map(play, jobs)):
            np.savez_compressed(f"runs/az/rec/r{j[2]}.npz", **d)
            print(f"seed {j[2]} done {time.time() - t:.0f}s", flush=True)


main()
