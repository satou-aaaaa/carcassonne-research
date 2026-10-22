"""棋譜を再生して、価値ネット用の盤面（手番側視点）を作る。8通りの回転・反転で水増しできる形にする。

planes（NCV=26層、R×R）: 0 タイル / 1..12 各辺の地形 / 13 修道院 / 14 盾 / 15..22 各辺の持ち主（自分・相手）/
23,24 修道院の持ち主 / 25 手持ちタイルをどれかの向きで置けるマス。
glob（NGV 個）: 評価関数の特徴量36個、手持ちタイル種別の one-hot(24)、未公開タイルの種別ごとの枚数/4(24)。
"""

import glob as globmod
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from carcassonne.fast import NT, SC_CUR, SC_DRAW, SC_OVER, SC_PL, Fast, apply_move
from carcassonne.fast_eval import NF, features
from carcassonne.nn_encode import NC, NTYPES, R, encode

NCV = 26
NGV = NF + 2 * NTYPES
C = R // 2
# 辺 s の向き（x, y）: 0=+y, 1=+x, 2=-y, 3=-x（fast.dircell）
DIRS = [(0, 1), (1, 0), (0, -1), (-1, 0)]
MATS = [
    np.array(m)
    for m in (
        [[1, 0], [0, 1]],
        [[0, -1], [1, 0]],
        [[-1, 0], [0, -1]],
        [[0, 1], [-1, 0]],
        [[-1, 0], [0, 1]],
        [[1, 0], [0, -1]],
        [[0, 1], [1, 0]],
        [[0, -1], [-1, 0]],
    )
]


def _tables():
    idx, chans = [], []
    xs, ys = np.meshgrid(np.arange(R), np.arange(R), indexing="ij")
    for M in MATS:
        # new[x', y'] = old[x, y], (x'-C, y'-C) = M (x-C, y-C) → old = M^-1 new
        Mi = np.round(np.linalg.inv(M)).astype(int)
        ox = Mi[0, 0] * (xs - C) + Mi[0, 1] * (ys - C) + C
        oy = Mi[1, 0] * (xs - C) + Mi[1, 1] * (ys - C) + C
        idx.append((ox, oy))
        perm = [DIRS.index(tuple(M @ np.array(d))) for d in DIRS]
        ch = list(range(NCV))  # new channel j takes old channel ch[j]
        for s in range(4):
            for k in range(3):
                ch[1 + 3 * perm[s] + k] = 1 + 3 * s + k
            for o in range(2):
                ch[15 + 2 * perm[s] + o] = 15 + 2 * s + o
        chans.append(np.array(ch))
    return idx, chans


IDX, CHANS = _tables()


def transform(planes, t):
    """planes[..., NCV, R, R] に変換 t（0..7）を掛ける。"""
    ox, oy = IDX[t]
    return planes[..., CHANS[t], :, :][..., ox, oy]


_BUF = {}


def encode_state(S, f):
    """手番側視点の (planes uint8[NCV,R,R], glob float32[NGV])。"""
    from carcassonne.nn_encode import NG

    T, P, sc = f.T, f.P, f.scratch
    if "pl" not in _BUF:
        _BUF.update(
            pl=np.zeros((NC, R, R), np.float32), gl=np.zeros(NG, np.float32), fb=np.zeros(NF)
        )
    pl, gl, fb = _BUF["pl"], _BUF["gl"], _BUF["fb"]
    me = int(S[10][SC_PL])
    ti = int(S[10][SC_CUR])
    encode(S, T, P, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, pl, gl, fb)
    v = np.zeros((NCV, R, R), np.uint8)
    v[:25] = pl[:25]
    v[25] = pl[25:29].max(0)
    features(S, T, P, me, fb)
    g = np.zeros(NGV, np.float32)
    g[:NF] = fb
    g[NF + ti] = 1
    np.add.at(g, NF + NTYPES + S[11][S[10][SC_DRAW] : NT - 1].astype(np.int64), 0.25)
    return v, g


def replay(path):
    d = np.load(path)
    f = Fast()
    T, P, sc = f.T, f.P, f.scratch
    out = {"planes": [], "glob": [], "y": [], "q": [], "game": [], "turn": []}
    for gi in range(len(d["nmoves"])):
        S = f.new_game(list(d["deck"][gi]))
        n = int(d["nmoves"][gi])
        sc0, sc1 = d["score"][gi]
        for k in range(n):
            me = int(S[10][SC_PL])
            v, g = encode_state(S, f)
            out["planes"].append(np.packbits(v.reshape(-1)))
            out["glob"].append(g)
            out["y"].append((sc0 - sc1) * (1 if me == 0 else -1))
            out["q"].append(d["q"][gi, k])
            out["game"].append(gi)
            out["turn"].append(k)
            c, gg, p = d["moves"][gi, k]
            apply_move(S, T, P, c, gg, p, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
        assert S[10][SC_OVER] == 1
    return {k: np.array(v) for k, v in out.items()}


def unpack(pk):
    return np.unpackbits(pk, axis=1)[:, : NCV * R * R].reshape(-1, NCV, R, R)


if __name__ == "__main__":
    for p in sorted(globmod.glob(sys.argv[1])):
        o = Path(p).with_name("e_" + Path(p).name)
        if not o.exists():
            np.savez_compressed(o, **replay(p))
            print(o, flush=True)
