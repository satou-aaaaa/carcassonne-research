"""評価関数の特徴量の候補（2026-10-08 に試して不採用。再現と次の候補探しのために残す）。

`fast_eval.features`（36個）の後ろに足して効き目を調べる。結果は docs/EXPERIMENTS.md の
「合流・完成確率の特徴量（不採用）」。探索で使うには `fast_eval.features` に組み込む必要がある
（対戦に使った組み込み版は共有フォルダ carcassonne-runs/features2/nf47_integrated.patch）。
"""

from __future__ import annotations

import numpy as np
from numba import njit

from .fast import NT, SC_DRAW, SC_N, SC_SUP0, G, dircell, end_points, find
from .fast_eval import n_fit, remaining_counts

NX = 11
EXT_NAMES = (
    "p_city_bonus",
    "p_city_bonus_x_remaining",
    "exp_return_mine",
    "exp_return_theirs",
    "exp_return_x_remaining",
    "supply0_mine",
    "supply0_theirs",
    "last_tile_mine",
    "p_road_meeple_x_remaining",
    "merge_gain_mine",
    "merge_gain_theirs",
)


@njit(cache=True)
def p_cell(f, R, n):
    """合うタイルが f 枚ある空きマスに、持ち主が n 回の引きのうちに合うタイルを1枚以上引く確率。"""
    if f <= 0:
        return 0.0
    q = 1.0
    for i in range(n):
        if R - f - i <= 0:
            return 1.0
        q *= (R - f - i) / (R - i)
    return 1.0 - q


@njit(cache=True)
def completion_logp(S, T, P, out):
    """未完成の都市・道・修道院の根ごとに、完成確率の対数（空きマスごとの確率の積）を書く。"""
    grid, tg, tcell, parent, kind, meep = S[0], S[1], S[2], S[3], S[4], S[9]
    sidepc, mpiece = T[8], T[10]
    cnt = remaining_counts(S, T)
    R = int(cnt.sum())
    n = (R + 1) // 2
    req = np.empty(4, np.int8)
    out[:] = 0.0
    NN = NT * P
    # 同じ (根, マス) を二重に数えない
    seen_r = np.empty(NN * 4, np.int32)
    seen_c = np.empty(NN * 4, np.int32)
    ns = 0
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
            if kind[r] > 1:
                continue
            dup = False
            for q in range(ns):
                if seen_r[q] == r and seen_c[q] == c:
                    dup = True
                    break
            if dup:
                continue
            seen_r[ns] = r
            seen_c[ns] = c
            ns += 1
            p = p_cell(n_fit(S, T, c, cnt, req), R, n)
            out[r] += np.log(max(p, 1e-9))
        mp = mpiece[g]
        if mp >= 0:
            r = find(parent, t * P + mp)
            if meep[r * 2] + meep[r * 2 + 1] > 0:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        c = c0 + dx * G + dy
                        if grid[c] == 0:
                            p = p_cell(n_fit(S, T, c, cnt, req), R, n)
                            out[r] += np.log(max(p, 1e-9))


@njit(cache=True)
def features_ext(S, T, P, me, out):
    sc = S[10]
    out[:] = 0.0
    NN = NT * P
    pts = np.zeros(NN, np.int32)
    end_points(S, T, P, pts)
    lp = np.empty(NN)
    completion_logp(S, T, P, lp)
    parent, meep, tg, npc, opn = S[3], S[9], S[1], T[1], S[5]
    rem = (NT - 1 - sc[SC_DRAW]) / 71.0
    for t in range(sc[SC_N]):
        for i in range(npc[tg[t]]):
            nd = t * P + i
            r = find(parent, nd)
            if r != nd:
                continue
            m0 = meep[r * 2]
            m1 = meep[r * 2 + 1]
            if m0 + m1 == 0:
                continue
            k = S[4][r]
            if k == 2:
                continue
            top = max(m0, m1)
            mine = m0 if me == 0 else m1
            theirs = m1 if me == 0 else m0
            p = np.exp(lp[r])
            if k == 0 and opn[r] > 0:
                b = pts[r] * p
                if mine == top:
                    out[0] += b
                if theirs == top:
                    out[0] -= b
            if k == 3 or opn[r] > 0:
                out[2] += mine * p
                out[3] += theirs * p
                if k == 1:
                    out[8] += (mine - theirs) * p
    out[1] = out[0] * rem
    out[4] = (out[2] - out[3]) * rem
    out[8] *= rem
    merge_gain(S, T, P, me, pts, out)
    out[5] = 1.0 if sc[SC_SUP0 + me] == 0 else 0.0
    out[6] = 1.0 if sc[SC_SUP0 + 1 - me] == 0 else 0.0
    R = remaining_counts(S, T).sum()  # 手元の1枚を含む、これから置かれる枚数
    out[7] = 1.0 if R % 2 == 1 else -1.0


@njit(cache=True)
def merge_gain(S, T, P, me, pts, out):
    """1枚で2つ以上のミープル入りの都市・道がつながる空きマスについて、つながったときの自分の得点見込みの増減。

    増える分の合計を out[9]、減る分（相手の得になる分）の合計を out[10] に足す。合うタイルがないマスは数えない。
    """
    grid, parent, kind, meep = S[0], S[3], S[4], S[9]
    sidepc = T[8]
    cnt = remaining_counts(S, T)
    req = np.empty(4, np.int8)
    roots = np.empty(4, np.int32)
    seen = np.zeros(G * G * 2, np.bool_)
    for t in range(S[10][SC_N]):
        c0 = S[2][t]
        for s0 in range(4):
            c = c0 + dircell(s0)
            if grid[c] != 0:
                continue
            for k in range(2):
                nr = 0
                for s in range(4):
                    nc = c + dircell(s)
                    if grid[nc] == 0:
                        continue
                    tt = grid[nc] - 1
                    a = sidepc[S[1][tt], (s + 2) % 4]
                    if a < 0:
                        continue
                    r = find(parent, tt * P + a)
                    if kind[r] != k or meep[r * 2] + meep[r * 2 + 1] == 0:
                        continue
                    dup = False
                    for q in range(nr):
                        if roots[q] == r:
                            dup = True
                    if not dup:
                        roots[nr] = r
                        nr += 1
                if nr < 2:
                    continue
                # 同じマスを何度も数えない
                if seen[c * 2 + k]:
                    continue
                seen[c * 2 + k] = True
                cur = 0.0
                tot0 = 0
                tot1 = 0
                V = 0.0
                for q in range(nr):
                    r = roots[q]
                    m0 = meep[r * 2]
                    m1 = meep[r * 2 + 1]
                    tot0 += m0
                    tot1 += m1
                    V += pts[r]
                    mine = m0 if me == 0 else m1
                    theirs = m1 if me == 0 else m0
                    top = max(m0, m1)
                    if mine == top:
                        cur += pts[r]
                    if theirs == top:
                        cur -= pts[r]
                mine = tot0 if me == 0 else tot1
                theirs = tot1 if me == 0 else tot0
                top = max(tot0, tot1)
                aft = 0.0
                if mine == top:
                    aft += V
                if theirs == top:
                    aft -= V
                d = aft - cur
                if d == 0.0 or n_fit(S, T, c, cnt, req) == 0:
                    continue
                if d > 0:
                    out[9] += d
                else:
                    out[10] -= d
