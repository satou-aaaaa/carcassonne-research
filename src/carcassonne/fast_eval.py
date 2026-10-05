"""学習型の評価関数（線形）の特徴量抽出とデータ生成・学習。

局面を手作りの特徴量ベクトルにし、線形モデルで「終局時の得点差（手番側視点）」を予測する。
探索の葉でランダムロールアウトの代わり（または打ち切り後の補正）に使う。
Ameneyro et al. (2020) が今後の課題として挙げた「評価関数による打ち切り」の試み。
"""

from __future__ import annotations

import numpy as np
from numba import njit

from .fast import (
    NT,
    SC_DRAW,
    SC_N,
    SC_OVER,
    SC_PL,
    SC_S0,
    SC_S1,
    SC_SUP0,
    Fast,
    apply_move,
    end_points,
    find,
    random_move,
)

NF = 14
FEATURE_NAMES = (
    "score_diff",
    "proj_diff",
    "proj_city",
    "proj_road",
    "proj_field",
    "proj_monastery",
    "meeples_city",
    "meeples_road",
    "meeples_field",
    "meeples_monastery",
    "supply_diff",
    "remaining",
    "proj_x_remaining",
    "bias",
)


@njit(cache=True)
def features(S, T, P, me, out):
    """局面の特徴量を `out[:NF]` に書く（`me` 視点。正が me に有利）。"""
    sc = S[10]
    out[:] = 0.0
    sign0 = 1.0 if me == 0 else -1.0
    out[0] = sign0 * (sc[SC_S0] - sc[SC_S1])
    NN = NT * P
    pts = np.zeros(NN, np.int32)
    end_points(S, T, P, pts)
    parent, meep, tg, npc = S[3], S[9], S[1], T[1]
    for t in range(sc[SC_N]):
        for i in range(npc[tg[t]]):
            n = t * P + i
            r = find(parent, n)
            if r != n:
                continue
            m0 = meep[r * 2]
            m1 = meep[r * 2 + 1]
            if m0 + m1 == 0:
                continue
            k = S[4][r]  # 0 都市 1 道 2 草原 3 修道院
            top = max(m0, m1)
            v = float(pts[r])
            mine = m0 if me == 0 else m1
            theirs = m1 if me == 0 else m0
            if mine == top:
                out[1] += v
                out[2 + k] += v
            if theirs == top:
                out[1] -= v
                out[2 + k] -= v
            out[6 + k] += mine - theirs
    mysup = sc[SC_SUP0 + me]
    thsup = sc[SC_SUP0 + 1 - me]
    out[10] = mysup - thsup
    rem = (NT - 1 - sc[SC_DRAW]) / 71.0
    out[11] = rem
    out[13] = 1.0
    out[1] += out[0]  # 予測得点差は確定得点も含める
    out[12] = out[1] * rem


class LinearEval:
    """線形評価関数 V(s)=w·f(s)（終局得点差の予測）。"""

    def __init__(self, w: np.ndarray | None = None) -> None:
        self.w = np.zeros(NF) if w is None else np.asarray(w, np.float64)

    def save(self, path: str) -> None:
        np.save(path, self.w)

    @classmethod
    def load(cls, path: str) -> LinearEval:
        return cls(np.load(path))


def collect(fast: Fast, n_games: int, stride: int = 3, meeple_prob: float = 0.3, seed: int = 0):
    """ランダム方策で n_games 局を指し、局面の (特徴量, 終局得点差) を集める。

    各局面は手番側（次に指す側）の視点。Pythonループだが、ゲーム進行はNumba関数で行う。
    """
    import random as _random

    from .fast import seed_rng

    rng = _random.Random(seed)
    xs, ys = [], []
    f = np.zeros(NF)
    seed_rng(seed)
    sc = fast.scratch
    ts = fast.ts
    base_deck = [i for i, t in enumerate(ts.types) for _ in range(t.count)]
    base_deck.remove(ts.start)
    for _ in range(n_games):
        deck = base_deck[:]
        rng.shuffle(deck)
        S = fast.new_game(deck)
        rows, players = [], []
        ply = 0
        while not S[10][SC_OVER]:
            if ply % stride == 0:
                me = int(S[10][SC_PL])
                features(S, fast.T, fast.P, me, f)
                rows.append(f.copy())
                players.append(me)
            cell, g, piece = random_move(
                S,
                fast.T,
                fast.P,
                meeple_prob,
                sc.stamp,
                sc.stamp_box,
                sc.out_cell,
                sc.out_g,
                sc.free,
            )
            apply_move(
                S, fast.T, fast.P, cell, g, piece, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g
            )
            ply += 1
        d = int(S[10][SC_S0]) - int(S[10][SC_S1])
        for r, me in zip(rows, players):
            xs.append(r)
            ys.append(d if me == 0 else -d)
    return np.array(xs), np.array(ys, np.float64)


def fit_ridge(X: np.ndarray, y: np.ndarray, lam: float = 1.0) -> LinearEval:
    """リッジ回帰（バイアス項は正則化しない）。"""
    reg = lam * np.eye(X.shape[1])
    reg[-1, -1] = 0.0  # bias
    w = np.linalg.solve(X.T @ X + reg, X.T @ y)
    return LinearEval(w)
