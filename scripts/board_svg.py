"""盤面の一部をSVGで描く（解説ページの図版用）。描き方は web/play.html のタイル描画に合わせている。"""

from __future__ import annotations

import itertools
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carcassonne.state import Move, State

PCOL = ["#d64541", "#2f6fd6"]
EM = [(0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5)]
HP = [(0.25, 0), (0.75, 0), (1, 0.25), (1, 0.75), (0.75, 1), (0.25, 1), (0, 0.75), (0, 0.25)]
D = 0.28
TRAP = {
    0: [(0, 0), (1, 0), (0.8, D), (0.2, D)],
    1: [(1, 0), (1, 1), (1 - D, 0.8), (1 - D, 0.2)],
    2: [(0, 1), (1, 1), (0.8, 1 - D), (0.2, 1 - D)],
    3: [(0, 0), (0, 1), (D, 0.8), (D, 0.2)],
}
INNER = {
    0: [(0.2, D), (0.8, D)],
    1: [(1 - D, 0.2), (1 - D, 0.8)],
    2: [(0.2, 1 - D), (0.8, 1 - D)],
    3: [(D, 0.2), (D, 0.8)],
}


def _hull(pts):
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts

    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def _anchor(p):
    if p.kind == "M":
        return (0.5, 0.5)
    if p.kind == "C":
        inner = {0: (0.5, D * 0.7), 1: (1 - D * 0.7, 0.5), 2: (0.5, 1 - D * 0.7), 3: (D * 0.7, 0.5)}
        pts = [inner[s] for s in p.sides]
        return (sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts))
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
    "tuft": "rgba(52,105,38,.55)",
    "roadEdge": "#8a6f48",
    "road": "#f2e2b6",
    "pebble": "rgba(201,178,128,.55)",
    "hub": "#c9b07a",
    "wall": "#6a4a30",
    "cityHi": "#e2ad78",
    "cityLo": "#c98656",
    "shield": "#2f5fb5",
    "shieldMark": "#ffd75e",
    "garden": "#b4dd8f",
    "chapel": "#f3ead6",
    "roof": "#b8463a",
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
    x0 = y0 = 0
    S = 100
    uid = "@ID@"
    rnd = random.Random(hash_variant(v))

    def pt(q):
        return (x0 + q[0] * S, y0 + q[1] * S)

    def pts_str(pts):
        return " ".join(f"{a:.0f},{b:.0f}" for a, b in map(pt, pts))

    defs = (
        f'<defs><radialGradient id="tf{uid}" cx="0.4" cy="0.35" r="0.8" fx="0.4" fy="0.35">'
        f'<stop offset="0.12" stop-color="{COL["fieldHi"]}"/><stop offset="1" stop-color="{COL["fieldLo"]}"/></radialGradient>'
        f'<linearGradient id="tc{uid}" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{COL["cityHi"]}"/><stop offset="1" stop-color="{COL["cityLo"]}"/></linearGradient></defs>'
    )
    out = [defs, f'<rect x="{x0}" y="{y0}" width="{S}" height="{S}" fill="url(#tf{uid})"/>']
    tufts = []
    for _ in range(14):
        x, y, h = rnd.random(), rnd.random(), 0.025 + rnd.random() * 0.02
        a, b, c, d = (
            pt((x - h * 0.5, y - h)),
            pt((x, y)),
            pt((x + h * 0.5, y - h)),
            pt((x, y - h * 1.1)),
        )
        tufts.append(
            f"M{a[0]:.0f},{a[1]:.0f}L{b[0]:.0f},{b[1]:.0f}L{c[0]:.0f},{c[1]:.0f}M{b[0]:.0f},{b[1]:.0f}L{d[0]:.0f},{d[1]:.0f}"
        )
    out.append(
        f'<path d="{"".join(tufts)}" stroke="{COL["tuft"]}" stroke-width="{S * 0.008:.1f}" fill="none" stroke-linecap="round"/>'
    )
    for _ in range(5):
        col = "rgba(255,248,200,.85)" if rnd.random() < 0.5 else "rgba(255,255,255,.8)"
        cx, cy = pt((rnd.random(), rnd.random()))
        out.append(f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{S * 0.009:.1f}" fill="{col}"/>')
    roads = [p for p in v.pieces if p.kind == "R"]
    paths = []
    for r in roads:
        if len(r.sides) >= 2:
            a, b, m = pt(EM[r.sides[0]]), pt(EM[r.sides[1]]), pt((0.5, 0.5))
            paths.append(f"M{a[0]:.0f},{a[1]:.0f} L{m[0]:.0f},{m[1]:.0f} L{b[0]:.0f},{b[1]:.0f}")
        else:
            a = pt(EM[r.sides[0]])
            f = 0.78 if len(roads) >= 3 else 1
            c = (x0 + S / 2, y0 + S / 2)
            e = (a[0] + (c[0] - a[0]) * f, a[1] + (c[1] - a[1]) * f)
            paths.append(f"M{a[0]:.0f},{a[1]:.0f} L{e[0]:.0f},{e[1]:.0f}")
    for w, col, dash in (
        (0.19, COL["roadEdge"], ""),
        (0.135, COL["road"], ""),
        (0.135, COL["pebble"], f' stroke-dasharray="{S * 0.012:.0f} {S * 0.05:.0f}"'),
    ):
        for d in paths:
            out.append(
                f'<path d="{d}" stroke="{col}" stroke-width="{S * w:.0f}" fill="none" stroke-linejoin="round"{dash}/>'
            )
    if len(roads) >= 3:
        cx, cy = x0 + S / 2, y0 + S / 2
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{S * 0.085:.0f}" fill="{COL["roadEdge"]}"/>')
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{S * 0.055:.0f}" fill="{COL["hub"]}"/>')
    cities = [p for p in v.pieces if p.kind == "C"]
    shapes = []
    for c in cities:
        shapes.append(TRAP[s] for s in c.sides)
        if len(c.sides) > 1:
            shapes.append([_hull([q for s in c.sides for q in INNER[s]])])
    shapes = [s for group in shapes for s in group]
    if shapes:
        wall = COL["wall"]
        for sh in shapes:
            out.append(
                f'<polygon points="{pts_str(sh)}" fill="none" stroke="{wall}" stroke-width="{S * 0.06:.0f}" stroke-linejoin="miter"/>'
            )
        for sh in shapes:
            out.append(
                f'<polygon points="{pts_str(sh)}" fill="none" stroke="{wall}" stroke-width="{S * 0.1:.0f}" '
                f'stroke-dasharray="{S * 0.04:.0f} {S * 0.035:.0f}" stroke-linejoin="miter"/>'
            )
        clip = "".join(f'<polygon points="{pts_str(sh)}"/>' for sh in shapes)
        out.append(f'<clipPath id="tk{uid}">{clip}</clipPath>')
        for sh in shapes:
            out.append(
                f'<polygon points="{pts_str(sh)}" fill="url(#tc{uid})" stroke="url(#tc{uid})" stroke-width="{S * 0.008:.0f}" stroke-linejoin="round"/>'
            )
        roofs = []
        for _ in range(14):
            x, y, w = rnd.random(), rnd.random(), 0.035
            col = "rgba(178,72,52,.55)" if rnd.random() < 0.5 else "rgba(150,90,60,.45)"
            roofs.append(
                f'<polygon points="{pts_str([(x - w, y), (x, y - w * 0.9), (x + w, y)])}" fill="{col}"/>'
            )
        out.append(f'<g clip-path="url(#tk{uid})">{"".join(roofs)}</g>')
        for c in cities:
            if c.pennant:
                ax, ay = pt(_anchor(c))
                out.append(_shield(ax, ay, S * 0.065))
    if any(p.kind == "M" for p in v.pieces):
        cx, cy = pt((0.5, 0.5))
        out.append(
            f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{S * 0.2:.0f}" fill="{COL["garden"]}"/>'
        )

        def rect(x, y, w, h, fill):
            return f'<rect x="{x0 + S * x:.0f}" y="{y0 + S * y:.0f}" width="{S * w:.0f}" height="{S * h:.0f}" fill="{fill}"/>'

        out.append(rect(0.39, 0.49, 0.27, 0.2, "rgba(0,0,0,.18)"))
        out.append(rect(0.37, 0.46, 0.26, 0.2, COL["chapel"]))
        out.append(
            f'<polygon points="{pts_str([(0.33, 0.47), (0.5, 0.31), (0.67, 0.47)])}" fill="{COL["roof"]}"/>'
        )
        a, b = pt((0.47, 0.66)), pt((0.47, 0.57))
        e = pt((0.53, 0.66))
        out.append(
            f'<path d="M{a[0]:.0f},{a[1]:.0f} L{b[0]:.0f},{b[1]:.0f} A{S * 0.03:.0f},{S * 0.03:.0f} 0 0 1 {b[0] + S * 0.06:.0f},{b[1]:.0f} L{e[0]:.0f},{e[1]:.0f} Z" fill="{COL["wall"]}"/>'
        )
        p1, p2, p3, p4 = pt((0.5, 0.31)), pt((0.5, 0.23)), pt((0.465, 0.26)), pt((0.535, 0.26))
        out.append(
            f'<path d="M{p1[0]:.0f},{p1[1]:.0f}L{p2[0]:.0f},{p2[1]:.0f}M{p3[0]:.0f},{p3[1]:.0f}L{p4[0]:.0f},{p4[1]:.0f}" '
            f'stroke="{COL["wall"]}" stroke-width="{S * 0.012:.0f}" stroke-linecap="round" fill="none"/>'
        )
    lw, o, e = S * 0.012, S * 0.006, S * 0.994
    out.append(
        f'<path d="M{x0 + o:.0f},{y0 + S:.0f} L{x0 + o:.0f},{y0 + o:.0f} L{x0 + S:.0f},{y0 + o:.0f}" stroke="rgba(255,255,255,.35)" stroke-width="{lw:.0f}" fill="none"/>'
        f'<path d="M{x0 + e:.0f},{y0:.0f} L{x0 + e:.0f},{y0 + e:.0f} L{x0:.0f},{y0 + e:.0f}" stroke="rgba(40,30,10,.45)" stroke-width="{lw:.0f}" fill="none"/>'
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
