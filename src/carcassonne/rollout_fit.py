"""評価関数を「探索の中で実際に使われる形」に合わせて学習するためのデータ作り。

最強設定（depth=10）の MCTS は、葉の局面をそのまま評価せず、ランダムに10手進めた先の局面を評価関数に通す
（10手の間に終局すれば実際の得点差）。ところが評価関数は、強いAIどうしの実戦の局面で学習している。
ランダムな10手のあとの局面（ミープルを適当に置いた盤面など）は実戦とは分布が違うので、評価値に偏りが出る。

線形の評価関数なら、葉の値の期待値は w・E[φ(10手先)] と書ける。そこで実戦の各局面 s について、
K 本のロールアウトで E[φ(10手先)] を見積もり、その平均特徴量から s の目標値（TD(λ) など）を当てるように w を
学習すれば、探索が葉で見ている値そのものを最適化できる（ロールアウトの途中で終局した分は、得点差を目標から引く）。

山札は探索と同じく、未公開部分をロールアウトごとにシャッフルする（手番側には未来のタイルは分からない）。
"""

from __future__ import annotations

import numpy as np
from numba import njit

from .fast import SC_OVER, SC_PL, SC_S0, SC_S1, Fast, copy_state, rollout
from .fast_eval import NF, features
from .fast_mcts import copy_into, shuffle_rest
from .records import replay


@njit(cache=True)
def leaf_stats(
    S, T, P, me, k, depth, meeple_prob, farm, W, stamp, stamp_box, out_cell, out_g, free, rec, fbuf,
    out_phi, out_fin,
):  # fmt: skip
    """局面 S から k 本ロールアウトし、me 視点の特徴量の和（終局しなかった分）を out_phi に、
    me 視点の得点差の和（終局した分）を out_fin[0] に、相手視点の特徴量の和を out_phi[NF:] に書く。"""
    for q in range(2 * NF):
        out_phi[q] = 0.0
    out_fin[0] = 0.0
    for _ in range(k):
        copy_into(W, S)
        shuffle_rest(W)
        rollout(W, T, P, meeple_prob, depth, stamp, stamp_box, out_cell, out_g, free, rec, farm)
        sc = W[10]
        if sc[SC_OVER] == 1:
            d = float(sc[SC_S0] - sc[SC_S1])
            out_fin[0] += d if me == 0 else -d
        else:
            features(W, T, P, me, fbuf)
            for q in range(NF):
                out_phi[q] += fbuf[q]
            features(W, T, P, 1 - me, fbuf)
            for q in range(NF):
                out_phi[NF + q] += fbuf[q]


def records_to_leaf_data(
    decks, moves, nmoves, k: int = 4, depth: int = 10, meeple_prob: float = 0.3, seed: int = 0
):
    """棋譜の各局面について、実局面の特徴量と、ロールアウト先の平均特徴量を作る。

    戻り値: X（実局面の特徴量, 手番側視点）, L（ロールアウト先の平均特徴量, 手番側視点）,
    Lo（同, 相手視点）, fin（終局したロールアウトの手番側視点の得点差の和 / k）, y（終局得点差, 手番側視点）,
    p（手番）, g（対局番号）。
    """
    from .fast import seed_rng

    seed_rng(seed)
    fast = Fast()
    sc = fast.scratch
    fbuf = np.zeros(NF)
    phi = np.zeros(2 * NF)
    fin = np.zeros(1)
    W = None
    xs, ls, los, fs, ys, ps, gs = [], [], [], [], [], [], []
    for gi in range(len(nmoves)):
        players = []
        for t, S in enumerate(replay(fast, decks[gi], moves[gi], int(nmoves[gi]))):
            if t == nmoves[gi]:
                d = int(S[10][SC_S0]) - int(S[10][SC_S1])
                break
            if W is None:
                W = copy_state(S)
            me = int(S[10][SC_PL])
            features(S, fast.T, fast.P, me, fbuf)
            xs.append(fbuf.copy())
            leaf_stats(
                S, fast.T, fast.P, me, k, depth, meeple_prob, True, W, sc.stamp, sc.stamp_box,
                sc.out_cell, sc.out_g, sc.free, sc.rec, fbuf, phi, fin,
            )  # fmt: skip
            ls.append(phi[:NF] / k)
            los.append(phi[NF:] / k)
            fs.append(fin[0] / k)
            players.append(me)
        ys.extend(d if me == 0 else -d for me in players)
        ps.extend(players)
        gs.extend([gi] * len(players))
    return (
        np.array(xs),
        np.array(ls),
        np.array(los),
        np.array(fs),
        np.array(ys, np.float64),
        np.array(ps, np.int64),
        np.array(gs, np.int64),
    )
