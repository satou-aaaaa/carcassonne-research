"""評価の特徴量の候補を、対局せずに「先生の手との一致率」で比べる（BACKLOG R-025）。

`scripts/rank_learn.py gen` が保存した局面（山札と手順）を作り直し、兄弟の手それぞれの着手後に候補の特徴を計算する。
今の特徴（C）だけで順位を学んだ評価と、候補を足して学んだ評価の、検証の一致率（先生の手を1手先の評価で選ぶ割合、
同点は割る）を比べる。R-024 で、今の特徴だけの上限は約0.67と分かっている。上がった候補だけを対局で確かめる。

  python scripts/feature_screen.py --data runs/r025/d*.npz --sets ext kind_rem field_margin
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from numba import njit

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import rank_learn as rl

from carcassonne.fast import NT, SC_DRAW, SC_END, SC_N, apply_move, copy_state, end_points, find
from carcassonne.fast_eval import NF, features
from carcassonne.fast_eval_ext import NX, features_ext


@njit(cache=True)
def field_margin(S, T, P, me, out):
    """草原の取り合い: 両者のミープルがいる草原で、最多の差が1以内のものの数（自分が勝っている・負けている・同数）。

    農民の得点は終局まで決まらず、差が1なら1人足すだけでひっくり返る（探索の10手先より遠いことが多い）。
    """
    out[:] = 0.0
    parent, meep, tg, npc = S[3], S[9], S[1], T[1]
    rem = (S[10][SC_END] - S[10][SC_DRAW]) / 71.0
    for t in range(S[10][SC_N]):
        for i in range(npc[tg[t]]):
            nd = t * P + i
            if find(parent, nd) != nd or S[4][nd] != 2:
                continue
            m0 = meep[nd * 2]
            m1 = meep[nd * 2 + 1]
            if m0 == 0 or m1 == 0:
                continue
            mine = m0 if me == 0 else m1
            theirs = m1 if me == 0 else m0
            if mine == theirs + 1:
                out[0] += 1.0
            elif theirs == mine + 1:
                out[1] += 1.0
            elif mine == theirs:
                out[2] += 1.0
    out[3] = (out[0] - out[1]) * rem


@njit(cache=True)
def city_road_margin(S, T, P, me, out):
    """未完成の都市・道の取り合い: 両者のミープルがいるもので、差1以内（勝ち・負け・同数）の得点見込みの和。

    相手が1人足せば取られる・同点に持ち込まれる特徴は、今の「最多の側の得点見込み」だけでは危うさが見えない。
    """
    out[:] = 0.0
    parent, meep, tg, npc = S[3], S[9], S[1], T[1]
    pts = np.zeros(NT * P, np.int32)
    end_points(S, T, P, pts)
    for t in range(S[10][SC_N]):
        for i in range(npc[tg[t]]):
            nd = t * P + i
            if find(parent, nd) != nd or S[4][nd] > 1 or S[5][nd] == 0:
                continue
            m0 = meep[nd * 2]
            m1 = meep[nd * 2 + 1]
            if m0 == 0 or m1 == 0:
                continue
            mine = m0 if me == 0 else m1
            theirs = m1 if me == 0 else m0
            v = float(pts[nd])
            if mine == theirs + 1:
                out[0] += v
            elif theirs == mine + 1:
                out[1] += v
            elif mine == theirs:
                out[2] += v


@njit(cache=True)
def kind_rem(S, T, P, me, out):
    """種類ごとの得点見込み・ミープル数に残り割合を掛けたもの（今の特徴は都市と草原だけ ×残り）。"""
    f = np.zeros(NF)
    features(S, T, P, me, f)
    rem = f[11]
    out[0] = f[3] * rem  # 道
    out[1] = f[5] * rem  # 修道院
    for k in range(4):
        out[2 + k] = f[6 + k] * rem


SETS = {
    # 名前: (列数, 計算する関数（S, T, P, me, out）か None, 説明)
    "ext": (
        NX,
        features_ext,
        "2026-10-08 の候補11個（完成確率・期待される戻り・合流など、fast_eval_ext）",
    ),
    "field_margin": (4, field_margin, "草原の取り合い（差1以内の草原の数）"),
    "city_road_margin": (3, city_road_margin, "都市・道の取り合い（差1以内の得点見込み）"),
    "kind_rem": (6, kind_rem, "道・修道院の見込みと種類ごとのミープル数 ×残り割合"),
}


def candidate_matrix(paths, names) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """全ファイルの兄弟について、候補の特徴（names の順に横に並べる）・今の特徴 C・兄弟の数 n。"""
    from carcassonne.fast_mcts import FastMCTSAgent

    fast = FastMCTSAgent(n_sims=10, eval_path="models/eval_champion.npy").fast
    T, P, sc = fast.T, fast.P, fast.scratch
    width = sum(SETS[k][0] for k in names)
    outs, Cs, ns = [], [], []
    for path in paths:
        # np.load の npz は d[名前] のたびに読み直す（展開する）ので、先に全部読む
        with np.load(path) as z:
            d = {k: z[k] for k in z.files}
        n = d["n"]
        st = np.concatenate([[0], np.cumsum(n)])
        Z = np.zeros((int(n.sum()), width))
        buf = [np.zeros(SETS[k][0]) for k in names]
        for i in range(len(n)):
            gi = int(d["pos_game"][i])
            S = rl.replay(fast, d["decks"][gi], d["hist"][gi], int(d["pos_ply"][i]))
            me = int(S[10][rl.SC_PL])
            X = copy_state(S)
            for r in range(st[i], st[i + 1]):
                for a, b in zip(X, S, strict=True):
                    a[...] = b
                cell, g, pc = (int(v) for v in d["cand"][r])
                apply_move(X, T, P, cell, g, pc, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
                o = 0
                for k, b in zip(names, buf, strict=True):
                    SETS[k][1](X, T, P, me, b)
                    Z[r, o : o + len(b)] = b
                    o += len(b)
        outs.append(Z)
        Cs.append(d["C"].astype(float))
        ns.append(n)
    return np.concatenate(outs), np.concatenate(Cs), np.concatenate(ns)


def agreement(w, C, n) -> float:
    """1手先の評価で選んだ手が先生の手と同じになる割合（同点は同点の数で割る）。"""
    start = np.concatenate([[0], np.cumsum(n)[:-1]])
    s = C @ w
    mx = np.maximum.reduceat(s, start)
    top = np.isclose(s, np.repeat(mx, n), atol=1e-6)
    return float(np.mean(top[start] / np.add.reduceat(top.astype(int), start)))


def fit_rank(C, n, w0, temp=0.5, l2=1e-4, iters=1500, lr=0.02) -> np.ndarray:
    """順位（先生の手の softmax 交差エントロピー）で線形の重みを学ぶ。特徴の尺度をそろえ、w0 へ L2 で引き戻す。"""
    sd = np.maximum(C.std(0), 1e-3)
    u = w0 * sd
    u0 = u.copy()
    m1 = np.zeros_like(u)
    m2 = np.zeros_like(u)
    for it in range(1, iters + 1):
        _, gw = rl.rank_loss(u / sd, C, n, temp)
        gu = gw / sd + l2 * (u - u0)
        m1 = 0.9 * m1 + 0.1 * gu
        m2 = 0.999 * m2 + 0.001 * gu**2
        u -= lr * (m1 / (1 - 0.9**it)) / (np.sqrt(m2 / (1 - 0.999**it)) + 1e-10)
    return u / sd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--sets", nargs="+", default=list(SETS), choices=list(SETS))
    ap.add_argument("--prior", default="models/eval_champion.npy")
    ap.add_argument("--iters", type=int, default=1500)
    a = ap.parse_args()
    from carcassonne.fast_eval import load_eval

    t0 = time.time()
    Z, C, n = candidate_matrix(sorted(a.data), a.sets)
    print(f"兄弟つき {len(n)}局面・{len(C)}手の候補を計算（{time.time() - t0:.0f}秒）", flush=True)
    champ, _ = load_eval(a.prior)
    w0 = np.zeros(NF)
    w0[: len(champ)] = champ[:NF]
    k = int(len(n) * 0.8)
    off = int(n[:k].sum())
    base = fit_rank(C[:off], n[:k], w0, iters=a.iters)
    b_val = agreement(base, C[off:], n[k:])
    print(f"チャンピオン {agreement(w0, C[off:], n[k:]):.4f} / 今の特徴だけで学び直し {b_val:.4f}")
    o = 0
    for name in a.sets:
        width = SETS[name][0]
        CZ = np.hstack([C, Z[:, o : o + width]])
        w = fit_rank(CZ[:off], n[:k], np.concatenate([base, np.zeros(width)]), iters=a.iters)
        v = agreement(w, CZ[off:], n[k:])
        print(f"{name}（{width}個）: {v:.4f}（{v - b_val:+.4f}） {SETS[name][2]}", flush=True)
        o += width
    if len(a.sets) > 1:
        CZ = np.hstack([C, Z])
        w = fit_rank(CZ[:off], n[:k], np.concatenate([base, np.zeros(Z.shape[1])]), iters=a.iters)
        v = agreement(w, CZ[off:], n[k:])
        print(f"全部: {v:.4f}（{v - b_val:+.4f}）")


if __name__ == "__main__":
    main()
