"""自己対戦の棋譜（山札と指し手）の記録と、棋譜からの特徴量の作り直し。

`selfplay.generate` は特徴量だけを保存するので、特徴量を足すたびに対局をやり直す必要があった。
棋譜を残しておけば、新しい特徴量は再生するだけで計算できる（探索をやり直さない）。

保存形式（npz）: deck (N,71) int8、moves (N,M,3) int32（マス・向きID・断片。未使用は -1）、nmoves (N,)。
"""

from __future__ import annotations

import random
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from .fast import SC_OVER, SC_PL, SC_S0, SC_S1, Fast, apply_move, random_move, seed_rng
from .fast_eval import NF, features
from .fast_mcts import FastMCTSAgent

MAXM = 80  # 1局の手数の上限（71枚＋余裕）


def _play(args):
    agent_kwargs, n_games, seed, eps = args
    agent = FastMCTSAgent(**agent_kwargs)
    fast = agent.fast
    sc = fast.scratch
    rng = random.Random(seed)
    seed_rng(seed)
    base = [i for i, t in enumerate(fast.ts.types) for _ in range(t.count)]
    base.remove(fast.ts.start)
    decks = np.zeros((n_games, len(base)), np.int8)
    moves = np.full((n_games, MAXM, 3), -1, np.int32)
    nmoves = np.zeros(n_games, np.int32)
    for gi in range(n_games):
        deck = base[:]
        rng.shuffle(deck)
        decks[gi] = deck
        S = fast.new_game(deck)
        k = 0
        while not S[10][SC_OVER]:
            if rng.random() < eps:
                cell, g, piece = random_move(
                    S, fast.T, fast.P, 0.3, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, sc.free
                )
            else:
                cell, g, piece = agent.choose(S)
            moves[gi, k] = (cell, g, piece)
            k += 1
            apply_move(
                S, fast.T, fast.P, cell, g, piece, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g
            )
        nmoves[gi] = k
    return decks, moves, nmoves


def play_records(agent_kwargs: dict, n_games: int, workers: int = 1, seed: int = 0, eps=0.05):
    """n_games 局を指して棋譜 (deck, moves, nmoves) を返す。乱数の作り方は `selfplay.generate` と同じ。"""
    per = [n_games // workers + (1 if i < n_games % workers else 0) for i in range(workers)]
    jobs = [(agent_kwargs, n, seed * 1000 + i, eps) for i, n in enumerate(per) if n > 0]
    if workers == 1:
        parts = [_play(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            parts = list(ex.map(_play, jobs))
    return tuple(np.concatenate([p[i] for p in parts]) for i in range(3))


def replay(fast: Fast, deck, moves, nmoves: int):
    """棋譜を再生し、各手の直前の局面 S を順に返すジェネレータ（最後に終局局面を返す）。

    返す S は同じ配列を使い回すので、必要な値はその場で取り出すこと。
    """
    sc = fast.scratch
    S = fast.new_game([int(t) for t in deck])
    for k in range(nmoves):
        yield S
        cell, g, piece = (int(v) for v in moves[k])
        apply_move(S, fast.T, fast.P, cell, g, piece, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
    assert S[10][SC_OVER], "棋譜の最後で終局していない"
    yield S


def records_to_data(fast: Fast, decks, moves, nmoves, feat=features, nf: int = NF):
    """棋譜から (X, y, 手番, 対局番号) を作る（`selfplay.generate(with_meta=True)` と同じ並び）。"""
    xs, ys, ps, gs = [], [], [], []
    f = np.zeros(nf)
    for gi in range(len(nmoves)):
        rows, players = [], []
        for k, S in enumerate(replay(fast, decks[gi], moves[gi], int(nmoves[gi]))):
            if k == nmoves[gi]:
                d = int(S[10][SC_S0]) - int(S[10][SC_S1])
                break
            me = int(S[10][SC_PL])
            feat(S, fast.T, fast.P, me, f)
            rows.append(f.copy())
            players.append(me)
        xs.extend(rows)
        ys.extend(d if me == 0 else -d for me in players)
        ps.extend(players)
        gs.extend([gi] * len(players))
    return np.array(xs), np.array(ys, np.float64), np.array(ps, np.int64), np.array(gs, np.int64)
