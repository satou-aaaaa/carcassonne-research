"""終盤の厳密解（ゲーム理論上の最善＝GTO）を読み切るソルバー。

2人カルカソンヌは、盤面・手持ち・山札の残り（種類と枚数）が両者に全部見えていて、隠れているのは
「次に何が出るか」の運だけの「運のある完全情報ゲーム」。この種のゼロ和ゲームでは、混合戦略は要らず、
運の節点で期待値をとり手番の節点で最大／最小をとる期待ミニマックス（expectiminimax）の値が
ゲームの値で、それを実現する手が最善（GTO）になる（Russell & Norvig『AIMA』6章「確率的ゲーム」）。

ここでは残りの山札が `max_bag` 枚以下の局面を、終局まで全部の手と全部の引きで読み切る。
目的は2つ:

- ``OBJ_WIN``  : 勝つ確率（勝ち1・引き分け0.5・負け0）の期待値を最大にする。ゲーム本来の目的。
- ``OBJ_DIFF`` : 最終点差の期待値を最大にする。AIの探索（点差を tanh で丸めた報酬）に近い目的。

値はいつも先手（プレイヤー0）視点で返す。引いたタイルが置けないときは捨てて引き直す（ルールどおり）。
山札の並び（S[11] の未公開部分）は使わず、残りの種類と枚数だけから確率を出す。
"""

from __future__ import annotations

import numpy as np
from numba import njit

from .fast import (
    SC_CUR,
    SC_DISC,
    SC_DRAW,
    SC_END,
    SC_OVER,
    SC_PL,
    SC_S0,
    SC_S1,
    SC_SUP0,
    copy_state,
    find,
    finish,
    gen_placements,
    piece_free,
    place_tile,
    score_after_placement,
)

OBJ_WIN = 0
OBJ_DIFF = 1
BIG = 1e6  # 点差の目的での値の上下限（実際の点差よりずっと大きい）


@njit(cache=True)
def _terminal(S, obj):
    d = S[10][SC_S0] - S[10][SC_S1]
    if obj == OBJ_DIFF:
        return float(d)
    if d > 0:
        return 1.0
    if d == 0:
        return 0.5
    return 0.0


@njit(cache=True)
def _apply_nodraw(S, T, P, cell, g, piece):
    """`apply_move` から引き（draw）を除いたもの。手番は相手に移す。"""
    sc = S[10]
    player = sc[SC_PL]
    place_tile(S, T, P, cell, g)
    if piece >= 0:
        t = S[0][cell] - 1
        r = find(S[3], t * P + piece)
        S[9][r * 2 + player] += 1
        sc[SC_SUP0 + player] -= 1
    score_after_placement(S, T, P, cell, g)
    sc[SC_PL] = 1 - player


# 互いに呼び合う再帰なので、キャッシュは使わない（古いキャッシュが残ると落ちる）
@njit
def _chance(S, T, P, obj, alpha, beta, stamp, stamp_box, out_cell, out_g, cnt):
    """着手の直後（まだ引いていない）局面の値。残りの種類ごとに引いた場合の値を枚数で重み付け平均。

    窓 (alpha, beta) の外と分かった時点で打ち切り、その境界の値を返す（確率節点の αβ、Star1）。
    """
    sc = S[10]
    lo = sc[SC_DRAW]
    end = sc[SC_END]
    if lo >= end:
        X = copy_state(S)
        X[10][SC_CUR] = -1
        finish(X, T, P)
        return _terminal(X, obj)
    lb, ub = (0.0, 1.0) if obj == OBJ_WIN else (-BIG, BIG)
    n = end - lo
    seen = np.zeros(128, np.bool_)
    done = 0.0  # 読み終えた引きの 確率×値 の和
    rem = 1.0  # まだ読んでいない引きの確率
    for j in range(lo, end):
        t = S[11][j]
        if seen[t]:
            continue
        seen[t] = True
        c = 0
        for q in range(lo, end):
            if S[11][q] == t:
                c += 1
        p = c / n
        rem -= p
        a = max(lb, (alpha - done - rem * ub) / p)
        b = min(ub, (beta - done - rem * lb) / p)
        X = copy_state(S)
        X[11][j] = X[11][lo]
        X[11][lo] = t
        X[10][SC_DRAW] = lo + 1
        stamp_box[0] += 1
        if gen_placements(X, T, t, stamp, stamp_box[0], out_cell, out_g, True) > 0:
            X[10][SC_CUR] = t
            v, _ = _decide(X, T, P, obj, a, b, stamp, stamp_box, out_cell, out_g, cnt, False)
        else:
            X[10][SC_DISC] += 1  # 置けないタイルは捨てて引き直す
            v = _chance(X, T, P, obj, a, b, stamp, stamp_box, out_cell, out_g, cnt)
        done += p * v
        if done + rem * ub <= alpha:
            return done + rem * ub
        if done + rem * lb >= beta:
            return done + rem * lb
    return done


@njit
def _decide(S, T, P, obj, alpha, beta, stamp, stamp_box, out_cell, out_g, cnt, want_all):
    """手番の局面の値（先手視点。先手は最大、後手は最小を選ぶ）。

    窓 (alpha, beta) で αβ 枝刈りする。want_all なら全着手を窓なしで読み、
    着手ごとの正確な値 (マス, 向きID, 断片, 値) の行も返す（根の解析用）。
    着手は「置いた直後の点差」の良い順に読む（枝刈りが効きやすい）。
    """
    sc = S[10]
    me = sc[SC_PL]
    ti = sc[SC_CUR]
    stamp_box[0] += 1
    k = gen_placements(S, T, ti, stamp, stamp_box[0], out_cell, out_g, False)
    cells = out_cell[:k].copy()
    gs = out_g[:k].copy()
    m = k * (T[1].max() + 1)
    mc = np.empty(m, np.int32)
    mg = np.empty(m, np.int32)
    mp = np.empty(m, np.int32)
    key = np.empty(m)
    nm = 0
    # 後に引きが残る節点だけ、置いた直後の点差で並べる（最後の1枚は並べても得がない）
    order_moves = sc[SC_DRAW] < sc[SC_END]
    for q in range(k):
        npc = T[1][gs[q]] if sc[SC_SUP0 + me] > 0 else 0
        for pi in range(-1, npc):
            if pi >= 0 and not piece_free(S, T, P, cells[q], gs[q], pi):
                continue
            key[nm] = 0.0
            if order_moves:
                X = copy_state(S)
                _apply_nodraw(X, T, P, cells[q], gs[q], pi)
                d = X[10][SC_S0] - X[10][SC_S1]
                key[nm] = -d if me == 0 else d
            mc[nm] = cells[q]
            mg[nm] = gs[q]
            mp[nm] = pi
            nm += 1
    order = np.argsort(key[:nm], kind="mergesort")
    rows = np.zeros((nm, 4))
    lb, ub = (0.0, 1.0) if obj == OBJ_WIN else (-BIG, BIG)
    best = lb - 1.0 if me == 0 else ub + 1.0
    for r in range(nm):
        i = order[r]
        X = copy_state(S)
        _apply_nodraw(X, T, P, mc[i], mg[i], mp[i])
        cnt[0] += 1
        if want_all:
            v = _chance(X, T, P, obj, lb, ub, stamp, stamp_box, out_cell, out_g, cnt)
            rows[r, 0] = mc[i]
            rows[r, 1] = mg[i]
            rows[r, 2] = mp[i]
            rows[r, 3] = v
        elif me == 0:
            v = _chance(
                X, T, P, obj, max(alpha, best), beta, stamp, stamp_box, out_cell, out_g, cnt
            )
        else:
            v = _chance(
                X, T, P, obj, alpha, min(beta, best), stamp, stamp_box, out_cell, out_g, cnt
            )
        if me == 0:
            best = max(best, v)
            if not want_all and best >= beta:
                return best, rows[:0]
        else:
            best = min(best, v)
            if not want_all and best <= alpha:
                return best, rows[:0]
    return best, rows[: nm if want_all else 0]


def solve(fast, S, obj: int = OBJ_WIN):
    """手番の局面 S（`Fast` の状態）を読み切る。

    戻り値: (局面の値（先手視点）, 着手ごとの値の配列 [(マス, 向きID, 断片, 値)], 読んだ着手数)。
    """
    if S[10][SC_OVER]:
        raise ValueError("終局している")
    sc = fast.scratch
    cnt = np.zeros(1, np.int64)
    lb, ub = (0.0, 1.0) if obj == OBJ_WIN else (-BIG, BIG)
    v, rows = _decide(
        copy_state(S), fast.T, fast.P, obj, lb, ub,
        sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, cnt, True,
    )  # fmt: skip
    return float(v), rows, int(cnt[0])


@njit
def _child(S, T, P, obj, cell, g, piece, alpha, beta, stamp, stamp_box, out_cell, out_g, cnt):
    """根の1手 (cell, g, piece) を指した後の値（窓つき）。"""
    X = copy_state(S)
    _apply_nodraw(X, T, P, cell, g, piece)
    cnt[0] += 1
    return _chance(X, T, P, obj, alpha, beta, stamp, stamp_box, out_cell, out_g, cnt)


def best_move(fast, S, prefer=None, obj: int = OBJ_WIN, eps: float = 1e-9):
    """手番の局面 S の最善手 (マス, 向きID, 断片) と、その値（先手視点）を返す。

    全着手の正確な値は出さず、αβ で「今の最善より良いか」だけを調べるので `solve` より速い。
    prefer（例: 探索AIの手）を最初に読み、それより厳密に良い手が無ければ prefer を返す
    （同じ値の手が複数あるときは、ふだんのAIの好みを残す）。
    """
    if S[10][SC_OVER]:
        raise ValueError("終局している")
    sc = fast.scratch
    T, P = fast.T, fast.P
    cnt = np.zeros(1, np.int64)
    lb, ub = (0.0, 1.0) if obj == OBJ_WIN else (-BIG, BIG)
    me = int(S[10][SC_PL])
    moves = _root_moves(S, T, P, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
    if prefer is not None:
        moves = [tuple(prefer)] + [m for m in moves if m != tuple(prefer)]
    best, bm = None, None
    for m in moves:
        if best is None:
            a, b = lb, ub
        elif me == 0:
            a, b = best + eps, ub
        else:
            a, b = lb, best - eps
        if a > b:
            break  # もう上限（必勝・必敗）に届いている
        v = _child(S, T, P, obj, *m, a, b, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, cnt)
        if best is None or (me == 0 and v > best + eps) or (me == 1 and v < best - eps):
            best, bm = v, m
    return bm, float(best)


@njit
def _root_moves_nb(S, T, P, stamp, stamp_box, out_cell, out_g):
    sc = S[10]
    me = sc[SC_PL]
    stamp_box[0] += 1
    k = gen_placements(S, T, sc[SC_CUR], stamp, stamp_box[0], out_cell, out_g, False)
    cells = out_cell[:k].copy()
    gs = out_g[:k].copy()
    m = k * (T[1].max() + 1)
    out = np.empty((m, 3), np.int64)
    key = np.empty(m)
    nm = 0
    for q in range(k):
        npc = T[1][gs[q]] if sc[SC_SUP0 + me] > 0 else 0
        for pi in range(-1, npc):
            if pi >= 0 and not piece_free(S, T, P, cells[q], gs[q], pi):
                continue
            X = copy_state(S)
            _apply_nodraw(X, T, P, cells[q], gs[q], pi)
            d = X[10][SC_S0] - X[10][SC_S1]
            key[nm] = -d if me == 0 else d
            out[nm, 0] = cells[q]
            out[nm, 1] = gs[q]
            out[nm, 2] = pi
            nm += 1
    return out[:nm][np.argsort(key[:nm], kind="mergesort")]


def _root_moves(S, T, P, stamp, stamp_box, out_cell, out_g):
    """根の全着手（置いた直後の点差の良い順）を (マス, 向きID, 断片) のタプルで。"""
    arr = _root_moves_nb(S, T, P, stamp, stamp_box, out_cell, out_g)
    return [tuple(int(x) for x in r) for r in arr]


def bag_left(S) -> int:
    """手番のタイルを除いた、山札に残っている枚数。"""
    return int(S[10][SC_END] - S[10][SC_DRAW])
