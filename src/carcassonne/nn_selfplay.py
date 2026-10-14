"""ニューラルネット学習用の自己対戦データ（盤面・MCTSの訪問分布・終局得点差）。

評価関数版MCTSの自己対戦で、各局面について
- `encode` の盤面（0/1 を `np.packbits` で圧縮）と盤全体の情報、
- 根の配置ごとの訪問数を正規化した方策の目標（切り出しの外の配置は捨てて正規化し直す）、
- 終局得点差（手番側視点）、
を記録する。多様性のため、確率 `eps` で合法手からランダムに指す。
"""

from __future__ import annotations

import random
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from .fast import SC_CUR, SC_OVER, SC_PL, SC_S0, SC_S1, apply_move, random_move, seed_rng
from .fast_eval import NF
from .fast_mcts import FastMCTSAgent, search_stats
from .nn_encode import NC, NG, NPOL, R, encode, policy_index


def _play_games(args):
    agent_kwargs, n_games, seed, eps = args
    agent = FastMCTSAgent(**agent_kwargs)
    fast = agent.fast
    T, P, sc = fast.T, fast.P, fast.scratch
    depth = agent.rollout_depth if agent.rollout_depth is not None else 0
    scale = -1.0 if agent.reward_scale is None else agent.reward_scale
    rng = random.Random(seed)
    seed_rng(seed)
    base = [i for i, t in enumerate(fast.ts.types) for _ in range(t.count)]
    base.remove(fast.ts.start)
    planes = np.zeros((NC, R, R), np.float32)
    glob = np.zeros(NG, np.float32)
    fbuf = np.zeros(NF)
    out = {"planes": [], "glob": [], "pol": [], "y": [], "game": [], "player": []}
    for gi in range(n_games):
        deck = base[:]
        rng.shuffle(deck)
        S = fast.new_game(deck)
        rows = []
        while not S[10][SC_OVER]:
            me = int(S[10][SC_PL])
            ti = int(S[10][SC_CUR])
            x0, y0, _ = encode(
                S, T, P, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, planes, glob, fbuf
            )
            cells, gs, agg1, _, agg2, _ = search_stats(
                S, T, P, agent.n_sims, 1, agent.c, scale, agent.meeple_prob,
                depth, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, sc.free, sc.rec,
                agent.eval_w, agent.eval_mode, agent.fbuf, 0, -1.0, 0, np.zeros(0, np.int64),
            )  # fmt: skip
            pol = np.zeros(NPOL, np.float32)
            for k in range(len(cells)):
                idx = policy_index(cells[k], gs[k], ti, x0, y0, T[11])
                if idx >= 0:
                    pol[idx] += agg1[k]
            if pol.sum() > 0:
                pol /= pol.sum()
                rows.append((np.packbits(planes.astype(np.uint8)), glob.copy(), pol, me))
            if rng.random() < eps:
                cell, g, piece = random_move(
                    S, T, P, 0.3, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, sc.free
                )
            else:
                top = agg1.max()
                cands = np.flatnonzero(agg1 == top)
                bk = cands[rng.randrange(len(cands))]
                cell, g = cells[bk], gs[bk]
                piece = int(np.argmax(agg2[bk])) - 1
            apply_move(S, T, P, cell, g, piece, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
        d = int(S[10][SC_S0]) - int(S[10][SC_S1])
        for pk, gl, pol, me in rows:
            out["planes"].append(pk)
            out["glob"].append(gl)
            out["pol"].append(pol.astype(np.float16))
            out["y"].append(d if me == 0 else -d)
            out["game"].append(gi)
            out["player"].append(me)
    return {k: np.array(v) for k, v in out.items()}


def generate(agent_kwargs: dict, n_games: int, workers: int = 1, seed: int = 0, eps: float = 0.05):
    """n_games 局の自己対戦から学習データ（辞書）を作る。対局番号はジョブ間で通し番号にする。"""
    per = [n_games // workers + (1 if i < n_games % workers else 0) for i in range(workers)]
    jobs = [(agent_kwargs, n, seed * 1000 + i, eps) for i, n in enumerate(per) if n > 0]
    if workers == 1:
        parts = [_play_games(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            parts = list(ex.map(_play_games, jobs))
    off = 0
    for p in parts:
        p["game"] = p["game"] + off
        off = int(p["game"].max()) + 1 if len(p["game"]) else off
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
