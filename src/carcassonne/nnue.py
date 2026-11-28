"""NNUE 風の評価（BACKLOG R-027）。

将棋・チェスの NNUE（Nasu 2018）と同じ形で、局面を「疎な二値の入力」の集まりにし、
その埋め込みの和（アキュムレータ）を小さな全結合の層に通して評価値を出す。

カルカソンヌの盤は形が決まっていない（どこにでも広がる）ので、チェスの「駒×マス」の代わりに
「未完成の特徴（都市・道・草原・修道院）ごとのトークン」を入力にする。トークンは

    種類(4) × 持ち主(6: なし・自分だけ最多・相手だけ最多・同数・自分が最多で相手もいる・相手が最多で自分もいる)
    × 得点の見込み(8段) × 開いた辺の数(4段) × 合う残りタイルの数(3段: 0・1〜3・4以上) × 山札の残り(4段)

の1つを指す番号。これに手持ちミープル（自分・相手 × 0〜7個 × 山札の残り）を足す。1手で変わるのは
置いたタイルにつながる特徴だけなので、アキュムレータは「消えたトークンを引き、増えたトークンを足す」で
差分更新できる（NNUE の要点）。ここでは毎回数え直しても、今の手作りの特徴の計算と同じくらいの速さで済む。

評価値 = チャンピオンの線形評価（今の38特徴）＋ 網の補正
網の補正 = g(a自分, a相手) − g(a相手, a自分)   （視点を入れ替えると符号が反転する）
g(x, y) = w2 · crelu(W1 · crelu([x, y]) + b1) + b2、 a = b0 + Σ E[トークン]、 crelu は 0〜1 で切る ReLU。

パラメータは1本の float64 配列（`pack`/`unpack`）。先頭の目印 TAG で `fast_eval.load_eval` が見分ける。
"""

from __future__ import annotations

import numpy as np
from numba import njit

from .fast import NT, SC_DRAW, SC_END, SC_N, SC_SUP0, end_points, find, popcnt
from .fast_eval import NF, eval_value, features, min_fit

TAG = -27027.0  # パラメータ配列の先頭の目印
MODE = -2  # `fast_eval.load_eval` が返す mode
HEAD = 4  # 先頭の欄: TAG, H, H2, NTOK

N_OWN = 6
N_VAL = 8
N_OPEN = 4
N_FIT = 3
N_PH = 4
N_STRUCT = 4 * N_OWN * N_VAL * N_OPEN * N_FIT * N_PH
N_SUP = 8
NTOK = N_STRUCT + 2 * N_SUP * N_PH
MAXTOK = 160  # 1局面のトークン数の上限（実際は多くても60ほど）


@njit(cache=True)
def _val_bucket(v):
    if v < 2:
        return 0
    if v < 4:
        return 1
    if v < 6:
        return 2
    if v < 9:
        return 3
    if v < 13:
        return 4
    if v < 18:
        return 5
    if v < 25:
        return 6
    return 7


@njit(cache=True)
def phase_of(S):
    left = S[10][SC_END] - S[10][SC_DRAW]
    if left >= 54:
        return 0
    if left >= 36:
        return 1
    if left >= 18:
        return 2
    return 3


@njit(cache=True)
def tokens(S, T, P, me, out):
    """me 視点のトークン番号を out に書き、個数を返す。"""
    NN = NT * P
    pts = np.zeros(NN, np.int32)
    end_points(S, T, P, pts)
    mf = np.empty(NN, np.int32)
    min_fit(S, T, P, mf)
    return tokens_with(S, T, P, me, out, pts, mf)


@njit(cache=True)
def tokens_with(S, T, P, me, out, pts, mf):
    """`tokens` の本体（各根の得点見込み pts と合う残りタイル数 mf を計算済みで受け取る）。"""
    sc = S[10]
    ph = phase_of(S)
    parent, kind, opn, meep, tg, npc = S[3], S[4], S[5], S[9], S[1], T[1]
    tlo, thi, pen = S[7], S[8], S[6]
    n = 0
    for t in range(sc[SC_N]):
        for i in range(npc[tg[t]]):
            nd = t * P + i
            if find(parent, nd) != nd:
                continue
            k = kind[nd]  # 0 都市 1 道 2 草原 3 修道院
            m0 = meep[nd * 2]
            m1 = meep[nd * 2 + 1]
            if k <= 1 and opn[nd] == 0:
                continue  # 完成済み（得点は確定得点に入っている）
            if m0 + m1 == 0:
                if k != 0:
                    continue  # 持ち主のいない道・草原・修道院は数が多く、ほぼ意味がないので省く
                own = 0
                v = popcnt(tlo[nd]) + popcnt(thi[nd]) + pen[nd]
            else:
                mine = m0 if me == 0 else m1
                theirs = m1 if me == 0 else m0
                v = pts[nd]
                if mine == theirs:
                    own = 3
                elif mine > theirs:
                    own = 1 if theirs == 0 else 4
                else:
                    own = 2 if mine == 0 else 5
            if k <= 1:
                ob = min(opn[nd], 4) - 1
            else:
                ob = 0
            if k == 2:
                fb = 2
            else:
                q = mf[nd]
                fb = 0 if q == 0 else (1 if q <= 3 else 2)
            idx = (
                (((k * N_OWN + own) * N_VAL + _val_bucket(v)) * N_OPEN + ob) * N_FIT + fb
            ) * N_PH + ph
            if n < MAXTOK - 2:
                out[n] = idx
                n += 1
    mys = min(sc[SC_SUP0 + me], N_SUP - 1)
    ths = min(sc[SC_SUP0 + 1 - me], N_SUP - 1)
    out[n] = N_STRUCT + mys * N_PH + ph
    out[n + 1] = N_STRUCT + N_SUP * N_PH + ths * N_PH + ph
    return n + 2


def pack(lin, E, b0, W1, b1, w2, b2) -> np.ndarray:
    H = E.shape[1]
    H2 = W1.shape[1]
    head = np.array([TAG, H, H2, E.shape[0]], float)
    parts = [head, lin, E.ravel(), b0, W1.ravel(), b1, w2, np.array([b2], float)]
    return np.concatenate([np.asarray(p, float).ravel() for p in parts])


def unpack(p: np.ndarray):
    H, H2, nt = int(p[1]), int(p[2]), int(p[3])
    o = HEAD
    lin = p[o : o + NF]
    o += NF
    E = p[o : o + nt * H].reshape(nt, H)
    o += nt * H
    b0 = p[o : o + H]
    o += H
    W1 = p[o : o + 2 * H * H2].reshape(2 * H, H2)
    o += 2 * H * H2
    b1 = p[o : o + H2]
    o += H2
    w2 = p[o : o + H2]
    o += H2
    return lin, E, b0, W1, b1, w2, float(p[o])


def is_nnue(p: np.ndarray) -> bool:
    return len(p) > HEAD and p[0] == TAG


@njit(cache=True)
def _head(p, H, H2, nt, ax, ay):
    """g(x, y): 2H → H2 → 1。"""
    oW1 = HEAD + NF + nt * H + H
    ob1 = oW1 + 2 * H * H2
    ow2 = ob1 + H2
    v = p[ow2 + H2]
    for j in range(H2):
        z = p[ob1 + j]
        for i in range(H):
            x = min(max(ax[i], 0.0), 1.0)
            if x != 0.0:
                z += x * p[oW1 + i * H2 + j]
            y = min(max(ay[i], 0.0), 1.0)
            if y != 0.0:
                z += y * p[oW1 + (H + i) * H2 + j]
        z = min(max(z, 0.0), 1.0)
        v += z * p[ow2 + j]
    return v


@njit(cache=True)
def _acc(p, H, nt, tok, n, a):
    oE = HEAD + NF
    ob0 = oE + nt * H
    for i in range(H):
        a[i] = p[ob0 + i]
    for q in range(n):
        base = oE + tok[q] * H
        for i in range(H):
            a[i] += p[base + i]


@njit(cache=True)
def nnue_value(S, T, P, me, f, p):
    """NNUE 風の評価値（me 視点の終局得点差の予測）。f には今の38特徴を書く（呼び出し側の作業用）。"""
    H, H2, nt = int(p[1]), int(p[2]), int(p[3])
    features(S, T, P, me, f)
    v = 0.0
    for q in range(NF):
        v += p[HEAD + q] * f[q]
    tok = np.empty(MAXTOK, np.int64)
    am = np.empty(H, np.float64)
    at = np.empty(H, np.float64)
    NN = NT * P
    pts = np.zeros(NN, np.int32)
    end_points(S, T, P, pts)
    mf = np.empty(NN, np.int32)
    min_fit(S, T, P, mf)
    n = tokens_with(S, T, P, me, tok, pts, mf)
    _acc(p, H, nt, tok, n, am)
    n = tokens_with(S, T, P, 1 - me, tok, pts, mf)
    _acc(p, H, nt, tok, n, at)
    return v + _head(p, H, H2, nt, am, at) - _head(p, H, H2, nt, at, am)


@njit(cache=True)
def evaluate(S, T, P, me, f, w, mode):
    """探索の葉の評価（me 視点）。mode == MODE なら NNUE 風、それ以外は今の特徴＋`eval_value`。"""
    if mode == MODE:
        return nnue_value(S, T, P, me, f, w)
    features(S, T, P, me, f)
    return eval_value(w, mode, f)


# ---- 学習（numpy） ----------------------------------------------------------------


def crelu(x):
    return np.clip(x, 0.0, 1.0)


class Net:
    """学習用。トークンは CSR（tok, off）で、視点ごとに2組（自分・相手）。"""

    def __init__(self, lin, H=32, H2=32, nt=NTOK, seed=0):
        rng = np.random.default_rng(seed)
        self.lin = np.asarray(lin, float).copy()
        self.E = rng.normal(0, 0.05, (nt, H))
        self.b0 = np.full(H, 0.3)
        self.W1 = rng.normal(0, 1 / np.sqrt(2 * H), (2 * H, H2))
        self.b1 = np.full(H2, 0.3)
        self.w2 = rng.normal(0, 0.1, H2)
        self.b2 = 0.0

    def params(self):
        return [self.E, self.b0, self.W1, self.b1, self.w2]

    def pack(self):
        return pack(self.lin, self.E, self.b0, self.W1, self.b1, self.w2, self.b2)

    @staticmethod
    def from_packed(p):
        lin, E, b0, W1, b1, w2, b2 = unpack(p)
        n = Net(lin, E.shape[1], W1.shape[1], E.shape[0])
        n.E, n.b0, n.W1, n.b1, n.w2, n.b2 = E.copy(), b0.copy(), W1.copy(), b1.copy(), w2.copy(), b2
        return n

    def _accum(self, tok, off, rows):
        """rows 番目の局面のアキュムレータ（len(rows), H）と、勾配を戻すための (行, トークン)。"""
        starts, ends = off[rows], off[rows + 1]
        lens = ends - starts
        idx = np.concatenate([np.arange(s, e) for s, e in zip(starts, ends, strict=True)])
        r = np.repeat(np.arange(len(rows)), lens)
        t = tok[idx]
        a = np.zeros((len(rows), self.E.shape[1]))
        np.add.at(a, r, self.E[t])
        return a + self.b0, r, t

    def forward(self, F, tm, om, tt, ot, rows):
        am, rm, km = self._accum(tm, om, rows)
        at, rt, kt = self._accum(tt, ot, rows)
        cache = []
        net = 0.0
        for sgn, (x, y) in ((1.0, (am, at)), (-1.0, (at, am))):
            h = np.concatenate([x, y], 1)
            hc = crelu(h)
            z = hc @ self.W1 + self.b1
            zc = crelu(z)
            out = zc @ self.w2
            net = net + sgn * out
            cache.append((sgn, h, hc, z, zc))
        v = F[rows] @ self.lin + net
        return v, (am, at, rm, km, rt, kt, cache)

    def backward(self, dv, c):
        """dv: dL/dv（len(rows)）。勾配の dict を返す。"""
        am, at, rm, km, rt, kt, cache = c
        H = self.E.shape[1]
        g = {
            "W1": np.zeros_like(self.W1),
            "b1": np.zeros_like(self.b1),
            "w2": np.zeros_like(self.w2),
        }
        dam = np.zeros_like(am)
        dat = np.zeros_like(at)
        for i, (sgn, h, hc, z, zc) in enumerate(cache):
            d = dv * sgn
            g["w2"] += zc.T @ d
            dz = np.outer(d, self.w2) * ((z > 0) & (z < 1))
            g["W1"] += hc.T @ dz
            g["b1"] += dz.sum(0)
            dh = (dz @ self.W1.T) * ((h > 0) & (h < 1))
            if i == 0:
                dam += dh[:, :H]
                dat += dh[:, H:]
            else:
                dat += dh[:, :H]
                dam += dh[:, H:]
        g["b0"] = dam.sum(0) + dat.sum(0)
        gE = np.zeros_like(self.E)
        np.add.at(gE, km, dam[rm])
        np.add.at(gE, kt, dat[rt])
        g["E"] = gE
        return g
