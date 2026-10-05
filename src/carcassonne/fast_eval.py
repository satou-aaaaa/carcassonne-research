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

NF = 22
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
    "open_city_mine",
    "open_city_theirs",
    "open_road_mine",
    "open_road_theirs",
    "n_features_mine",
    "n_features_theirs",
    "remaining_sq",
    "supply_mine",
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
            if k <= 1:  # 都市・道: 所有側の開放端数（完成までの距離）
                if mine == top:
                    out[14 + 2 * k] += S[5][r]
                if theirs == top:
                    out[15 + 2 * k] += S[5][r]
            if mine == top:
                out[18] += 1.0
            if theirs == top:
                out[19] += 1.0
    mysup = sc[SC_SUP0 + me]
    thsup = sc[SC_SUP0 + 1 - me]
    out[10] = mysup - thsup
    rem = (NT - 1 - sc[SC_DRAW]) / 71.0
    out[11] = rem
    out[13] = 1.0
    out[20] = rem * rem
    out[21] = mysup / 7.0
    out[1] += out[0]  # 予測得点差は確定得点も含める
    out[12] = out[1] * rem


@njit(cache=True)
def eval_value(p, mode, f):
    """評価関数の値（me視点の終局得点差の予測）。mode==1: 線形、mode>=2: 隠れ層 mode のMLP(ReLU)。

    MLPのパラメータ配置: mean(NF) std(NF) W1(NF*H) b1(H) W2(H) b2。
    """
    if mode == 1:
        v = 0.0
        for q in range(NF):
            v += p[q] * f[q]
        return v
    H = mode
    off = 2 * NF
    v = p[off + NF * H + 2 * H]
    for h in range(H):
        a = p[off + NF * H + h]
        for i in range(NF):
            a += (f[i] - p[i]) / p[NF + i] * p[off + i * H + h]
        if a > 0.0:
            v += a * p[off + NF * H + H + h]
    return v


def load_eval(path: str) -> tuple[np.ndarray, int]:
    """重みファイルを読み、(パラメータ, mode) を返す。長さ<=NFなら線形（不足分は0埋め）、それ以外はMLP。"""
    w = np.load(path).astype(np.float64)
    if len(w) <= NF:
        return np.concatenate([w, np.zeros(NF - len(w))]), 1
    H = (len(w) - 2 * NF - 1) // (NF + 2)
    assert 2 * NF + NF * H + 2 * H + 1 == len(w), "MLPパラメータ長が不正"
    return w, H


def fit_mlp(
    X: np.ndarray,
    y: np.ndarray,
    hidden: int = 32,
    epochs: int = 40,
    lr: float = 2e-3,
    wd: float = 1e-4,
    seed: int = 0,
    val_frac: float = 0.1,
) -> tuple[np.ndarray, float]:
    """1隠れ層MLP(ReLU)をAdamで回帰学習する。戻り値は (パラメータ, 検証R²)。"""
    rng = np.random.default_rng(seed)
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    bias_idx = FEATURE_NAMES.index("bias")
    mean[bias_idx], std[bias_idx] = 0.0, 1.0
    std[std < 1e-8] = 1.0
    Z = (X - mean) / std
    ysc = 30.0
    t = y / ysc
    n = len(Z)
    idx = rng.permutation(n)
    nv = int(n * val_frac)
    va, tr = idx[:nv], idx[nv:]
    nf, H = Z.shape[1], hidden
    W1 = rng.normal(0, np.sqrt(2.0 / nf), (nf, H))
    b1 = np.zeros(H)
    W2 = rng.normal(0, np.sqrt(1.0 / H), H)
    b2 = 0.0
    params = [W1, b1, W2, np.array([b2])]
    m = [np.zeros_like(p) for p in params]
    v = [np.zeros_like(p) for p in params]
    step = 0
    best, best_r2 = None, -1e9

    def forward(Zb):
        a = Zb @ params[0] + params[1]
        h = np.maximum(a, 0.0)
        return a, h, h @ params[2] + params[3][0]

    for _ in range(epochs):
        perm = rng.permutation(tr)
        for s in range(0, len(perm), 512):
            b = perm[s : s + 512]
            a, h, out = forward(Z[b])
            g = 2.0 * (out - t[b]) / len(b)
            gW2 = h.T @ g + wd * params[2]
            gb2 = np.array([g.sum()])
            gh = np.outer(g, params[2]) * (a > 0)
            gW1 = Z[b].T @ gh + wd * params[0]
            gb1 = gh.sum(axis=0)
            step += 1
            for i, gr in enumerate((gW1, gb1, gW2, gb2)):
                m[i] = 0.9 * m[i] + 0.1 * gr
                v[i] = 0.999 * v[i] + 0.001 * gr * gr
                mh = m[i] / (1 - 0.9**step)
                vh = v[i] / (1 - 0.999**step)
                params[i] -= lr * mh / (np.sqrt(vh) + 1e-8)
        pred = forward(Z[va])[2]
        r2 = 1 - ((t[va] - pred) ** 2).sum() / ((t[va] - t[va].mean()) ** 2).sum()
        if r2 > best_r2:
            best_r2 = r2
            best = [p.copy() for p in params]
    W1, b1, W2, b2 = best
    flat = np.concatenate([mean, std, W1.reshape(-1), b1, W2 * ysc, np.array([b2[0] * ysc])])
    return flat, float(best_r2)


class LinearEval:
    """線形評価関数 V(s)=w·f(s)（終局得点差の予測）。"""

    def __init__(self, w: np.ndarray | None = None) -> None:
        self.w = np.zeros(NF) if w is None else np.asarray(w, np.float64)

    def save(self, path: str) -> None:
        np.save(path, self.w)

    @classmethod
    def load(cls, path: str) -> LinearEval:
        return cls(load_eval(path)[0])


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
