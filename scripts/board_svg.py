"""盤面の一部をSVGで描く（解説ページの図版用）。描き方は web/play.html のタイル描画に合わせている。"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carcassonne.state import Move, State

PCOL = ["#d64541", "#2f6fd6"]
EM = [(0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5)]
HP = [(0.25, 0), (0.75, 0), (1, 0.25), (1, 0.75), (0.75, 1), (0.25, 1), (0, 0.75), (0, 0.25)]
CORNER = [(0, 0), (1, 0), (1, 1), (0, 1)]


# 都市・道の形は web/tile_art.js と同じ計算（tests/test_tile_art.py が一致を確かめる）
def _bend(P, Q, h, n):
    d = (Q[0] - P[0], Q[1] - P[1])
    c1 = (P[0] + d[0] * 0.445 + n[0] * h, P[1] + d[1] * 0.445 + n[1] * h)
    c2 = (P[0] + d[0] * 0.555 + n[0] * h, P[1] + d[1] * 0.555 + n[1] * h)
    pts = []
    for i in range(17):
        t = i / 16
        u = 1 - t
        a, b, c, e = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
        pts.append(
            (
                a * P[0] + b * c1[0] + c * c2[0] + e * Q[0],
                a * P[1] + b * c1[1] + c * c2[1] + e * Q[1],
            )
        )
    return pts


def city_shape(sides):
    """都市1つの輪郭（点の並び）と、草原との境の線（城壁を描く所）の一覧。"""
    S, n = set(sides), len(sides)
    if n >= 4:
        return list(CORNER), []
    start = next(s for s in sides if (s + 3) % 4 not in S)
    poly, walls = [CORNER[start]], []
    s, done = start, 0
    while done < 4:
        if s in S:
            poly.append(CORNER[(s + 1) % 4])
            s = (s + 1) % 4
            done += 1
            continue
        e, gap = s, 0
        while e not in S:
            e = (e + 1) % 4
            gap += 1
        P, Q = CORNER[s], CORNER[e]
        if gap == 2:  # 隣り合う2辺: 草原の側へふくらませて大きく
            k = CORNER[(e + 1) % 4]
            v, h = (k[0] - 0.5, k[1] - 0.5), -0.13
        else:
            v = (0.5 - (P[0] + Q[0]) / 2, 0.5 - (P[1] + Q[1]) / 2)
            h = 0.373 if gap == 3 else (0.33 if n == 3 else 0.27)
        L = (v[0] ** 2 + v[1] ** 2) ** 0.5
        w = _bend(P, Q, h, (v[0] / L, v[1] / L))
        walls.append(w)
        poly.extend(w[1:])
        s, done = e, done + gap
    poly.pop()
    return poly, walls


def city_anchor(sides):
    n = len(sides)
    if n == 1:
        return [(0.5, 0.13), (0.87, 0.5), (0.5, 0.87), (0.13, 0.5)][sides[0]]
    if n >= 4 or (n == 2 and abs(sides[0] - sides[1]) == 2):
        return (0.5, 0.5)
    if n == 2:
        k = next(c for c in range(4) if c in sides and (c + 3) % 4 in sides)
        return (0.5 + (CORNER[k][0] - 0.5) * 0.5, 0.5 + (CORNER[k][1] - 0.5) * 0.5)
    miss = next(c for c in range(4) if c not in sides)
    e = EM[miss]
    return (0.5 - (e[0] - 0.5) * 0.2, 0.5 - (e[1] - 0.5) * 0.2)


def road_line(sides, nroads):
    """道の線（点の並び）。曲がり道はなめらかな弧、行き止まり（3本以上）は中心の手前で止める。"""
    a = EM[sides[0]]
    if len(sides) >= 2:
        b = EM[sides[1]]
        if (sides[0] + sides[1]) % 2 == 0:
            return [a, (0.5, 0.5), b]
        return [
            (
                (1 - t) ** 2 * a[0] + 2 * (1 - t) * t * 0.5 + t * t * b[0],
                (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * 0.5 + t * t * b[1],
            )
            for t in (i / 12 for i in range(13))
        ]
    f = 0.78 if nroads >= 3 else 1
    return [a, (a[0] + (0.5 - a[0]) * f, a[1] + (0.5 - a[1]) * f)]


def _anchor(p):
    if p.kind == "M":
        return (0.5, 0.5)
    if p.kind == "C":
        return city_anchor(list(p.sides))
    if p.kind == "R":
        if len(p.sides) >= 2:
            pts = [EM[s] for s in p.sides]
            m = (sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts))
            return (m[0] * 0.5 + 0.25, m[1] * 0.5 + 0.25)
        e = EM[p.sides[0]]
        return (e[0] + (0.5 - e[0]) * 0.6, e[1] + (0.5 - e[1]) * 0.6)
    pts = [HP[h] for h in p.halves]
    c = (sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts))
    return (c[0] + (0.5 - c[0]) * 0.3, c[1] + (0.5 - c[1]) * 0.3)


def anchors(v):
    res = [_anchor(p) for p in v.pieces]

    def dist(a, b):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    for i, p in enumerate(v.pieces):
        if p.kind != "F":
            continue
        others = [r for j, r in enumerate(res) if j != i]
        if all(dist(o, res[i]) > 0.2 for o in others):
            continue
        best, bs = res[i], -1.0
        for h in p.halves:
            c = (HP[h][0] + (0.5 - HP[h][0]) * 0.2, HP[h][1] + (0.5 - HP[h][1]) * 0.2)
            sc = min(dist(o, c) for o in others)
            if sc > bs:
                bs, best = sc, c
        res[i] = best
    return res


# タイルの色（web/tile_art.js の COL と同じ値にそろえる）
COL = {
    "fieldHi": "#9fcf78",
    "fieldLo": "#78ad5a",
    "roadEdge": "#5e4a2e",
    "road": "#fbf0d0",
    "hub": "#c9b07a",
    "wall": "#5a3a22",
    "wallStone": "#c9b9a0",
    "cityHi": "#f3cf8e",
    "cityLo": "#e2a865",
    "shade": "rgba(95,55,25,.16)",
    "shield": "#2f5fb5",
    "shieldMark": "#ffd75e",
    "garden": "#b4dd8f",
    "chapel": "#f3ead6",
    "roof": "#b8463a",
    "border": "rgba(30,25,10,.3)",
}
_ids = itertools.count()


def _shield(ax, ay, r):
    d = (
        f"M{ax - r:.1f},{ay - r * 1.1:.1f} L{ax + r:.1f},{ay - r * 1.1:.1f} L{ax + r:.1f},{ay + 0.2 * r:.1f} "
        f"Q{ax + r:.1f},{ay + r * 0.9:.1f} {ax:.1f},{ay + r * 1.35:.1f} "
        f"Q{ax - r:.1f},{ay + r * 0.9:.1f} {ax - r:.1f},{ay + 0.2 * r:.1f} Z"
    )
    mark = (
        f"M{ax:.1f},{ay - r * 0.75:.1f} L{ax:.1f},{ay + r * 0.95:.1f} "
        f"M{ax - r * 0.65:.1f},{ay - r * 0.15:.1f} L{ax + r * 0.65:.1f},{ay - r * 0.15:.1f}"
    )
    return (
        f'<path d="{d}" fill="{COL["shield"]}" stroke="#fff" stroke-width="{r * 0.22:.1f}"/>'
        f'<path d="{mark}" stroke="{COL["shieldMark"]}" stroke-width="{r * 0.32:.1f}" fill="none"/>'
    )


_unit_cache: dict = {}


def tile_svg(v, x0, y0, S):
    """左上 (x0,y0)・一辺 S のタイル1枚。絵柄は web/tile_art.js（対戦ページ）に合わせている。
    一辺100の絵を作って拡大縮小する（ページが重くならないよう、座標を短く・同じ向きは使い回す）。"""
    if v not in _unit_cache:
        _unit_cache[v] = _tile_unit(v)
    body = _unit_cache[v].replace("@ID@", str(next(_ids)))
    k = S / 100
    return f'<g transform="translate({x0:g},{y0:g}) scale({k:g})">{body}</g>'


def _tile_unit(v):
    """web/tile_art.js の paint と同じ絵（一辺100）。"""
    S = 100
    uid = "@ID@"

    def P(q):
        return f"{q[0] * S:.1f},{q[1] * S:.1f}"

    def path(pts, close=False):
        return "M" + " L".join(P(q) for q in pts) + (" Z" if close else "")

    out = [
        (
            f'<defs><radialGradient id="tf{uid}" cx="0.4" cy="0.35" r="0.8" fx="0.4" fy="0.35">'
            f'<stop offset="0.12" stop-color="{COL["fieldHi"]}"/><stop offset="1" stop-color="{COL["fieldLo"]}"/></radialGradient>'
            f'<linearGradient id="tc{uid}" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{COL["cityHi"]}"/><stop offset="1" stop-color="{COL["cityLo"]}"/></linearGradient></defs>'
        ),
        f'<rect width="{S}" height="{S}" fill="url(#tf{uid})"/>',
    ]
    roads = [p for p in v.pieces if p.kind == "R"]
    for w, col in ((0.23, COL["roadEdge"]), (0.16, COL["road"])):
        for r in roads:
            d = path(road_line(list(r.sides), len(roads)))
            out.append(
                f'<path d="{d}" stroke="{col}" stroke-width="{S * w:.1f}" fill="none" stroke-linejoin="round"/>'
            )
    if len(roads) >= 3:
        out.append(f'<circle cx="50" cy="50" r="{S * 0.1:.1f}" fill="{COL["roadEdge"]}"/>')
        out.append(f'<circle cx="50" cy="50" r="{S * 0.066:.1f}" fill="{COL["hub"]}"/>')
    for i, c in enumerate(p for p in v.pieces if p.kind == "C"):
        poly, walls = city_shape(list(c.sides))
        out.append(f'<clipPath id="tk{uid}_{i}"><path d="{path(poly, True)}"/></clipPath>')
        out.append(f'<path d="{path(poly, True)}" fill="url(#tc{uid})"/>')
        wd = " ".join(path(w) for w in walls)
        if wd:
            out.append(
                f'<g clip-path="url(#tk{uid}_{i})" fill="none" stroke="{COL["shade"]}" stroke-linejoin="round">'
                f'<path d="{wd}" stroke-width="{S * 0.2:.1f}"/><path d="{wd}" stroke-width="{S * 0.12:.1f}"/></g>'
            )
            out.append(
                f'<g fill="none" stroke-linejoin="round"><path d="{wd}" stroke="{COL["wall"]}" stroke-width="{S * 0.075:.1f}"/>'
                f'<path d="{wd}" stroke="{COL["wallStone"]}" stroke-width="{S * 0.035:.1f}"/>'
                f'<path d="{wd}" stroke="{COL["wall"]}" stroke-width="{S * 0.035:.1f}" stroke-dasharray="{S * 0.03:.1f} {S * 0.03:.1f}"/></g>'
            )
        if c.pennant:
            ax, ay = city_anchor(list(c.sides))
            out.append(_shield(ax * S, ay * S, S * 0.085))
    if any(p.kind == "M" for p in v.pieces):
        k = 1.3

        def T(x, y):
            return (S * (0.5 + (x - 0.5) * k), S * (0.5 + (y - 0.5) * k))

        def rect(x, y, w, h, fill):
            a, b = T(x, y)
            return f'<rect x="{a:.1f}" y="{b:.1f}" width="{S * w * k:.1f}" height="{S * h * k:.1f}" fill="{fill}"/>'

        out.append(f'<circle cx="50" cy="50" r="{S * 0.2 * k:.1f}" fill="{COL["garden"]}"/>')
        out.append(rect(0.39, 0.49, 0.27, 0.2, "rgba(0,0,0,.18)"))
        out.append(rect(0.37, 0.46, 0.26, 0.2, COL["chapel"]))
        roof = " ".join(
            "{:.1f},{:.1f}".format(*T(*q)) for q in ((0.33, 0.47), (0.5, 0.31), (0.67, 0.47))
        )
        out.append(f'<polygon points="{roof}" fill="{COL["roof"]}"/>')
        (a0, a1), (b0, b1), (e0, e1) = T(0.47, 0.66), T(0.47, 0.57), T(0.53, 0.66)
        r = S * 0.03 * k
        out.append(
            f'<path d="M{a0:.1f},{a1:.1f} L{b0:.1f},{b1:.1f} A{r:.1f},{r:.1f} 0 0 1 {b0 + 2 * r:.1f},{b1:.1f} L{e0:.1f},{e1:.1f} Z" fill="{COL["wall"]}"/>'
        )
        (p1, p2), (q1, q2), (r1, r2), (s1, s2) = (
            T(0.5, 0.31),
            T(0.5, 0.23),
            T(0.465, 0.26),
            T(0.535, 0.26),
        )
        out.append(
            f'<path d="M{p1:.1f},{p2:.1f}L{q1:.1f},{q2:.1f}M{r1:.1f},{r2:.1f}L{s1:.1f},{s2:.1f}" '
            f'stroke="{COL["wall"]}" stroke-width="{S * 0.012 * k:.1f}" stroke-linecap="round" fill="none"/>'
        )
    out.append(
        f'<rect x="{S * 0.008:.1f}" y="{S * 0.008:.1f}" width="{S * 0.984:.1f}" height="{S * 0.984:.1f}" '
        f'fill="none" stroke="{COL["border"]}" stroke-width="{S * 0.016:.1f}"/>'
    )
    return "".join(out)


def hash_variant(v) -> int:
    """同じタイル・向きなら毎回同じ模様にするための種（実行ごとに変わる hash() は使わない）。"""
    key = "".join(v.edges) + "".join(p.kind + "".join(map(str, p.sides)) for p in v.pieces)
    return sum((i + 1) * ord(ch) for i, ch in enumerate(key))


def meeple_svg(x, y, r, player):
    head = f'<circle cx="{x:.1f}" cy="{y - r * 0.9:.1f}" r="{r * 0.75:.1f}" fill="{PCOL[player]}" stroke="#fff" stroke-width="1.5"/>'
    body = (
        f'<polygon points="{x - r * 1.15:.1f},{y + r * 1.2:.1f} {x:.1f},{y - r * 0.2:.1f} {x + r * 1.15:.1f},{y + r * 1.2:.1f}" '
        f'fill="{PCOL[player]}" stroke="#fff" stroke-width="1.5"/>'
    )
    return head + body


def replay(deck: list[int], history: list, upto: int):
    """着手履歴の先頭 upto 手を再生し、(State, 盤上のミープル一覧) を返す。"""
    st = State(deck)
    meeples = []
    for x, y, ti, vi, piece in history[:upto]:
        assert st.current == ti
        player = st.player
        st.apply(Move(x, y, vi, piece))
        if piece is not None:
            meeples.append({"x": x, "y": y, "piece": piece, "player": player})
        meeples = [
            m
            for m in meeples
            if st.meeples[st._find(st.tile_nodes[(m["x"], m["y"])][m["piece"]])][m["player"]] > 0
        ]
    return st, meeples


def board_svg(st: State, meeples, center, radius=2, S=64, highlight=None, ghost=None, labels=None):
    """center 周辺 (2*radius+1)^2 マスを描く。highlight は枠で囲むマス [(x,y,色)]、
    ghost は半透明で描く候補タイル [(x,y,variant,色)]（手番タイル）。"""
    cx, cy = center
    # 窓の中でタイルのある範囲だけに切り詰める（空白の余白を作らない）
    inside = [p for p in st.board if abs(p[0] - cx) <= radius and abs(p[1] - cy) <= radius] + [
        center
    ]
    inside += [(g[0], g[1]) for g in (ghost or []) + (highlight or [])]  # 候補タイルも窓に入れる
    x_lo, x_hi = min(p[0] for p in inside), max(p[0] for p in inside)
    y_lo, y_hi = min(p[1] for p in inside), max(p[1] for p in inside)
    xs = range(x_lo, x_hi + 1)
    ys = range(y_hi, y_lo - 1, -1)
    W, H = S * len(xs), S * len(ys)
    parts = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img">']
    parts.append(f'<rect width="{W}" height="{H}" fill="var(--board-bg, #efe9dc)"/>')

    def left(x):
        return (x - xs[0]) * S

    def top(y):
        return (ys[0] - y) * S

    for (x, y), (ti, vi) in st.board.items():
        if x in xs and y in ys:
            parts.append(tile_svg(st.ts.types[ti].variants[vi], left(x), top(y), S))
    for x, y, vi, col in ghost or []:
        v = st.ts.types[st.current].variants[vi]
        parts.append(f'<g opacity="0.9">{tile_svg(v, left(x), top(y), S)}</g>')
    for m in meeples:
        if m["x"] in xs and m["y"] in ys:
            ti, vi = st.board[(m["x"], m["y"])]
            ax, ay = anchors(st.ts.types[ti].variants[vi])[m["piece"]]
            parts.append(
                meeple_svg(left(m["x"]) + ax * S, top(m["y"]) + ay * S, S * 0.1, m["player"])
            )
    for x, y, col in highlight or []:
        parts.append(
            f'<rect x="{left(x) + 2}" y="{top(y) + 2}" width="{S - 4}" height="{S - 4}" fill="none" stroke="{col}" stroke-width="3.5" rx="3"/>'
        )
    for x, y, text in labels or []:
        parts.append(
            f'<text x="{left(x) + S / 2}" y="{top(y) + S / 2 + 7}" text-anchor="middle" font-size="22" font-weight="700" fill="#222" stroke="#fff" stroke-width="3" paint-order="stroke">{text}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)
