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
    SC_CUR,
    SC_DRAW,
    SC_N,
    SC_OVER,
    SC_PL,
    SC_S0,
    SC_S1,
    SC_SUP0,
    Fast,
    G,
    apply_move,
    dircell,
    end_points,
    find,
    random_move,
    req_at,
)

HARD = 3  # 「完成させにくい」とみなす、空きマスに合う残りタイルの枚数の上限


@njit(cache=True)
def remaining_counts(S, T):
    """まだ置かれていないタイル（未公開の山札＋手元の1枚）の種別ごとの枚数。"""
    sc, deck = S[10], S[11]
    cnt = np.zeros(len(T[11]), np.int32)
    for i in range(sc[SC_DRAW], NT - 1):
        cnt[deck[i]] += 1
    if sc[SC_CUR] >= 0 and sc[SC_OVER] == 0:
        cnt[sc[SC_CUR]] += 1
    return cnt


@njit(cache=True)
def n_fit(S, T, cell, cnt, req):
    """空きマス cell に（どれかの向きで）置ける残りタイルの枚数。0 ならこのマスは二度と埋まらない。"""
    edge, vbase, nvar = T[0], T[11], T[12]
    req_at(S, T, cell, req)
    n = 0
    for ti in range(len(cnt)):
        if cnt[ti] == 0:
            continue
        for vi in range(nvar[ti]):
            g = vbase[ti] + vi
            ok = True
            for d in range(4):
                if req[d] >= 0 and req[d] != edge[g, d]:
                    ok = False
                    break
            if ok:
                n += cnt[ti]
                break
    return n


@njit(cache=True)
def min_fit(S, T, P, out):
    """未完成の都市（ミープルの有無によらない）と、ミープルのいる未完成の道・修道院の根ごとに、
    隣の空きマスに合う残りタイル枚数の最小値を書く。

    0 なら完成不能（相手に塞がれた、または合うタイルを使い切った）。それ以外の根は大きな値のまま。
    """
    grid, tg, tcell, parent, kind, meep = S[0], S[1], S[2], S[3], S[4], S[9]
    sidepc, mpiece = T[8], T[10]
    cnt = remaining_counts(S, T)
    req = np.empty(4, np.int8)
    out[:] = 1 << 20
    for t in range(S[10][SC_N]):
        g = tg[t]
        c0 = tcell[t]
        for s in range(4):
            c = c0 + dircell(s)
            if grid[c] != 0:
                continue
            a = sidepc[g, s]
            if a < 0:
                continue
            r = find(parent, t * P + a)
            if kind[r] == 0 or meep[r * 2] + meep[r * 2 + 1] > 0:
                out[r] = min(out[r], n_fit(S, T, c, cnt, req))
        mp = mpiece[g]
        if mp >= 0:
            r = find(parent, t * P + mp)
            if meep[r * 2] + meep[r * 2 + 1] > 0:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        c = c0 + dx * G + dy
                        if grid[c] == 0:
                            out[r] = min(out[r], n_fit(S, T, c, cnt, req))


NF = 36
NF_V6 = 22  # v6 までの特徴量数（旧形式の重み・MLPの読み込み用）
NF_V7 = 29  # 妨害・農民の特徴量（29〜35）を足す前の数（旧形式のMLP・nn_v1 の入力用）
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
    "city_bonus",
    "supply_x_remaining",
    "stuck_mine",
    "stuck_theirs",
    "proj_field_x_remaining",
    "proj_city_x_remaining",
    "monastery_room_x_remaining",
    "dead_mine",
    "dead_theirs",
    "dead_city_bonus",
    "hard_city_bonus",
    "dead_x_remaining",
    "field_open_cities",
    "field_open_cities_x_remaining",
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
    mf = np.empty(NN, np.int32)
    min_fit(S, T, P, mf)
    out[34] = field_open_cities(S, T, P, me, mf)
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
            if k == 0 and S[5][r] > 0:
                # 完成すれば都市は2倍になる。開放端が少ないほど完成しやすいので、上乗せ分を開放端数で割る
                b = v / S[5][r]
                if mine == top:
                    out[22] += b
                if theirs == top:
                    out[22] -= b
                # 完成不能な都市には上乗せが来ない。合うタイルが少ない都市には来にくい
                q = 31 if mf[r] == 0 else (32 if mf[r] <= HARD else -1)
                if q >= 0:
                    if mine == top:
                        out[q] += b
                    if theirs == top:
                        out[q] -= b
            if k != 2:
                # 未完成の都市・道・修道院に置いたミープル（終盤ほど戻ってこない）
                out[24] += mine
                out[25] += theirs
                if mf[r] == 0:
                    # 完成不能な特徴に閉じ込められたミープル（終局まで戻らない）
                    out[29] += mine
                    out[30] += theirs
            if k == 3:
                room = 9.0 - v  # 修道院の周囲の空きマス（これから増える得点の上限）
                if mine == top:
                    out[28] += room
                if theirs == top:
                    out[28] -= room
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
    # 残りタイル数との交互作用（線形モデルでも「序盤と終盤で価値が違う」を表せるようにする）
    out[23] = out[10] * rem
    out[24] *= 1.0 - rem
    out[25] *= 1.0 - rem
    out[26] = out[4] * rem
    out[27] = out[2] * rem
    out[28] *= rem
    out[33] = (out[29] - out[30]) * rem
    out[35] = out[34] * rem


@njit(cache=True)
def field_open_cities(S, T, P, me, mf):
    """農民の取り分: 自分が最多の草原に隣接する、まだ完成していないが完成可能な都市の数×3（相手の分を引く）。

    終局時の草原の得点は「隣接する完成都市×3」なので、これから完成しうる都市は草原の伸びしろになる。
    """
    tg, parent, opn, meep = S[1], S[3], S[5], S[9]
    npc, pkind, cadj = T[1], T[2], T[7]
    NN = NT * P
    pc = np.empty(NN, np.int32)
    pf = np.empty(NN, np.int32)
    npairs = 0
    v = 0.0
    for t in range(S[10][SC_N]):
        g = tg[t]
        for i in range(npc[g]):
            if pkind[g, i] != 0:
                continue
            cr = find(parent, t * P + i)
            if opn[cr] == 0 or mf[cr] == 0:
                continue
            for j in range(npc[g]):
                if (cadj[g, i] >> j) & 1:
                    fr = find(parent, t * P + j)
                    m0 = meep[fr * 2]
                    m1 = meep[fr * 2 + 1]
                    if m0 + m1 == 0:
                        continue
                    dup = False
                    for q in range(npairs):
                        if pc[q] == cr and pf[q] == fr:
                            dup = True
                            break
                    if dup:
                        continue
                    pc[npairs] = cr
                    pf[npairs] = fr
                    npairs += 1
                    top = max(m0, m1)
                    mine = m0 if me == 0 else m1
                    theirs = m1 if me == 0 else m0
                    if mine == top:
                        v += 3.0
                    if theirs == top:
                        v -= 3.0
    return v


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
    for nf in (NF, NF_V7, NF_V6):
        H = (len(w) - 2 * nf - 1) // (nf + 2)
        # 長さだけでは形式が決まらないことがあるので、標準偏差の欄がすべて正であることも確かめる
        if H > 0 and 2 * nf + nf * H + 2 * H + 1 == len(w) and np.all(w[nf : 2 * nf] > 0):
            break
    else:
        raise AssertionError("MLPパラメータ長が不正")
    if nf == NF:
        return w, H
    # 旧形式（特徴量 nf 個）のMLP: 追加特徴量は 平均0・標準偏差1・重み0 として埋める
    pad = NF - nf
    mean = np.concatenate([w[:nf], np.zeros(pad)])
    std = np.concatenate([w[nf : 2 * nf], np.ones(pad)])
    off = 2 * nf
    W1 = np.vstack([w[off : off + nf * H].reshape(nf, H), np.zeros((pad, H))])
    rest = w[off + nf * H :]
    return np.concatenate([mean, std, W1.reshape(-1), rest]), H


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


def bias_index(nf: int) -> int:
    """バイアス特徴の位置。本物の特徴量（22個・29個）では13番目、それ以外（テスト用）は最後。"""
    return FEATURE_NAMES.index("bias") if nf >= NF_V6 else nf - 1


def ridge_solve(
    xtx: np.ndarray, xty: np.ndarray, lam: float, prior: np.ndarray | None = None
) -> np.ndarray:
    """(XᵀX+λI)w = Xᵀy + λ·prior を解く（バイアス項は正則化しない）。

    prior を与えると、0ではなく prior に向かって縮める（前の世代の重みを忘れにくくする）。
    """
    nf = xtx.shape[0]
    reg = lam * np.eye(nf)
    reg[bias_index(nf), bias_index(nf)] = 0.0
    rhs = xty if prior is None else xty + reg @ np.asarray(prior, np.float64)
    return np.linalg.solve(xtx + reg, rhs)


def fit_ridge(
    X: np.ndarray, y: np.ndarray, lam: float = 1.0, prior: np.ndarray | None = None
) -> LinearEval:
    """リッジ回帰（バイアス項は正則化しない）。prior は `ridge_solve` を参照。"""
    return LinearEval(ridge_solve(X.T @ X, X.T @ y, lam, prior))
