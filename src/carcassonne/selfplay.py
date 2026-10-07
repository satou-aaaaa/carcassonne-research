"""自己対戦による学習データ生成（方策反復用）。

エージェント（ロールアウト版またはその時点の評価関数版MCTS）同士の対戦で、各局面の
特徴量と、その対戦の終局得点差（手番側視点）を記録する。多様性のため、確率 `eps` で
合法配置からランダムに指す。並列実行はプロセス単位。`with_meta=True` なら、TD(λ) の目標を
作るための手番と対局番号も返す。
"""

from __future__ import annotations

import random
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from .fast import (
    SC_OVER,
    SC_PL,
    SC_S0,
    SC_S1,
    apply_move,
    random_move,
    seed_rng,
)
from .fast_eval import NF, features
from .fast_mcts import FastMCTSAgent


def _play_games(args) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    agent_kwargs, n_games, seed, eps = args
    agent = FastMCTSAgent(**agent_kwargs)
    fast = agent.fast
    sc = fast.scratch
    ts = fast.ts
    rng = random.Random(seed)
    seed_rng(seed)
    base = [i for i, t in enumerate(ts.types) for _ in range(t.count)]
    base.remove(ts.start)
    f = np.zeros(NF)
    xs, ys, ps, gs = [], [], [], []
    for gi in range(n_games):
        deck = base[:]
        rng.shuffle(deck)
        S = fast.new_game(deck)
        rows, players = [], []
        while not S[10][SC_OVER]:
            me = int(S[10][SC_PL])
            features(S, fast.T, fast.P, me, f)
            rows.append(f.copy())
            players.append(me)
            if rng.random() < eps:
                cell, g, piece = random_move(
                    S, fast.T, fast.P, 0.3, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, sc.free
                )
            else:
                cell, g, piece = agent.choose(S)
            apply_move(
                S, fast.T, fast.P, cell, g, piece, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g
            )
        d = int(S[10][SC_S0]) - int(S[10][SC_S1])
        xs.extend(rows)
        ys.extend(d if me == 0 else -d for me in players)
        ps.extend(players)
        gs.extend([gi] * len(players))
    return np.array(xs), np.array(ys, np.float64), np.array(ps, np.int64), np.array(gs, np.int64)


def generate(
    agent_kwargs: dict,
    n_games: int,
    workers: int = 1,
    seed: int = 0,
    eps: float = 0.05,
    with_meta: bool = False,
):
    """n_games 局の自己対戦から (X, y) を作る。with_meta なら (X, y, 手番, 対局番号)。"""
    per = [n_games // workers + (1 if i < n_games % workers else 0) for i in range(workers)]
    jobs = [(agent_kwargs, n, seed * 1000 + i, eps) for i, n in enumerate(per) if n > 0]
    if workers == 1:
        parts = [_play_games(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            parts = list(ex.map(_play_games, jobs))
    X = np.concatenate([p[0] for p in parts])
    y = np.concatenate([p[1] for p in parts])
    if not with_meta:
        return X, y
    players = np.concatenate([p[2] for p in parts])
    # 対局番号をジョブ間で通し番号にする
    offs = np.cumsum([0] + [int(p[3].max()) + 1 if len(p[3]) else 0 for p in parts])
    games = np.concatenate([p[3] + o for p, o in zip(parts, offs)])
    return X, y, players, games
