"""ニューラルネット用の盤面表現（盤を中心で切り出した R×R の格子、手番側視点）。

各マスのチャンネル（`NC` 個）:
  0 タイルあり / 1..12 各辺(4)の地形(都市・道・草原) / 13 修道院 / 14 盾 /
  15..22 各辺の特徴の持ち主（辺sごとに 自分が多数・相手が多数） / 23,24 修道院の持ち主（自分・相手） /
  25..28 手持ちタイルを向き vi で置ける合法マス
盤全体の情報（`NG` 個）: 評価関数の特徴量（`fast_eval.features`、NF個）と手持ちタイル種別の one-hot。
方策の添字は `vi*R*R + x*R + y`（x, y は切り出し内の座標、vi は手持ちタイルの向き番号）。
"""

from __future__ import annotations

from numba import njit

from .fast import SC_CUR, SC_N, SC_PL, G, find, gen_placements
from .fast_eval import NF, features

R = 25  # 切り出しの一辺（盤の中心から±12マス）
NC = 29
NTYPES = 24
NG = NF + NTYPES
NPOL = 4 * R * R


@njit(cache=True)
def crop_origin(S):
    """置かれたタイルの座標の平均を中心にした、切り出しの左上（グリッド座標）。"""
    tcell = S[2]
    n = S[10][SC_N]
    sx = 0.0
    sy = 0.0
    for t in range(n):
        sx += tcell[t] // G
        sy += tcell[t] % G
    cx = round(sx / n)
    cy = round(sy / n)
    return cx - R // 2, cy - R // 2


@njit(cache=True)
def encode(S, T, P, stamp, stamp_box, out_cell, out_g, planes, glob, fbuf):
    """手番側視点で planes[NC,R,R] と glob[NG] を書き、(x0, y0, 合法配置数) を返す。

    合法配置は out_cell/out_g の先頭に残る（`policy_index` で方策の添字に直せる）。
    """
    sc = S[10]
    me = sc[SC_PL]
    grid, tg, parent, meep = S[0], S[1], S[3], S[9]
    edge, ppen, sidepc, mpiece, vbase = T[0], T[5], T[8], T[10], T[11]
    planes[:] = 0.0
    x0, y0 = crop_origin(S)
    for x in range(R):
        for y in range(R):
            cell = (x0 + x) * G + (y0 + y)
            t = grid[cell] - 1
            if t < 0:
                continue
            g = tg[t]
            planes[0, x, y] = 1.0
            pen = 0
            for s in range(4):
                planes[1 + s * 3 + edge[g, s], x, y] = 1.0
                pc = sidepc[g, s]
                if pc >= 0:
                    r = find(parent, t * P + pc)
                    mine = meep[r * 2 + me]
                    theirs = meep[r * 2 + 1 - me]
                    if mine > 0 and mine >= theirs:
                        planes[15 + 2 * s, x, y] = 1.0
                    if theirs > 0 and theirs >= mine:
                        planes[16 + 2 * s, x, y] = 1.0
                    pen |= ppen[g, pc]
            planes[14, x, y] = pen
            mp = mpiece[g]
            if mp >= 0:
                planes[13, x, y] = 1.0
                n = t * P + mp
                if meep[n * 2 + me] > 0:
                    planes[23, x, y] = 1.0
                if meep[n * 2 + 1 - me] > 0:
                    planes[24, x, y] = 1.0
    ti = sc[SC_CUR]
    stamp_box[0] += 1
    k = gen_placements(S, T, ti, stamp, stamp_box[0], out_cell, out_g, False)
    for j in range(k):
        x = out_cell[j] // G - x0
        y = out_cell[j] % G - y0
        if 0 <= x < R and 0 <= y < R:
            planes[25 + out_g[j] - vbase[ti], x, y] = 1.0
    features(S, T, P, me, fbuf)
    glob[:] = 0.0
    glob[:NF] = fbuf
    glob[NF + ti] = 1.0
    return x0, y0, k


@njit(cache=True)
def policy_index(cell, g, ti, x0, y0, vbase):
    """配置 (マス, 向きID) の方策の添字。切り出しの外なら -1。"""
    x = cell // G - x0
    y = cell % G - y0
    if x < 0 or x >= R or y < 0 or y >= R:
        return -1
    return (g - vbase[ti]) * R * R + x * R + y
