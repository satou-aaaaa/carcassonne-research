"""盤面の一部をSVGで描く（解説ページの図版用）。描き方は web/play.html のタイル描画に合わせている。"""

from __future__ import annotations

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


def tile_svg(v, x0, y0, S):
    """左上 (x0,y0)・一辺 S のタイル1枚。"""

    def pt(q):
        return (x0 + q[0] * S, y0 + q[1] * S)

    def poly(pts, **kw):
        attrs = " ".join(f'{k.replace("_", "-")}="{val}"' for k, val in kw.items())
        return (
            f'<polygon points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in map(pt, pts))}" {attrs}/>'
        )

    out = [f'<rect x="{x0}" y="{y0}" width="{S}" height="{S}" fill="#86b96a"/>']
    roads = [p for p in v.pieces if p.kind == "R"]
    for w, col in ((0.17, "#7a6a45"), (0.11, "#f3e7c3")):
        for r in roads:
            if len(r.sides) >= 2:
                a, b, m = pt(EM[r.sides[0]]), pt(EM[r.sides[1]]), pt((0.5, 0.5))
                d = f"M{a[0]:.1f},{a[1]:.1f} L{m[0]:.1f},{m[1]:.1f} L{b[0]:.1f},{b[1]:.1f}"
            else:
                a = pt(EM[r.sides[0]])
                f = 0.78 if len(roads) >= 3 else 1
                c = (x0 + S / 2, y0 + S / 2)
                e = (a[0] + (c[0] - a[0]) * f, a[1] + (c[1] - a[1]) * f)
                d = f"M{a[0]:.1f},{a[1]:.1f} L{e[0]:.1f},{e[1]:.1f}"
            out.append(
                f'<path d="{d}" stroke="{col}" stroke-width="{S * w:.1f}" fill="none" stroke-linejoin="round"/>'
            )
    if len(roads) >= 3:
        out.append(
            f'<circle cx="{x0 + S / 2}" cy="{y0 + S / 2}" r="{S * 0.06:.1f}" fill="#7a6a45"/>'
        )
    cities = [p for p in v.pieces if p.kind == "C"]
    shapes = []
    for c in cities:
        sh = [TRAP[s] for s in c.sides]
        if len(c.sides) > 1:
            sh.append(_hull([q for s in c.sides for q in INNER[s]]))
        shapes.append(sh)
    for sh in shapes:
        for s in sh:
            out.append(
                poly(s, fill="#5e3f26", stroke="#5e3f26", stroke_width=4, stroke_linejoin="round")
            )
    for sh in shapes:
        for s in sh:
            out.append(poly(s, fill="#c08a5a"))
    for c in cities:
        if c.pennant:
            ax, ay = pt(_anchor(c))
            k = S / 128
            pts = [(-8, -10), (8, -10), (8, 3), (0, 11), (-8, 3)]
            out.append(
                '<polygon points="'
                + " ".join(f"{ax + a * k:.1f},{ay + b * k:.1f}" for a, b in pts)
                + '" fill="#2f5fb5" stroke="#fff" stroke-width="1"/>'
            )
    if any(p.kind == "M" for p in v.pieces):
        out.append(
            f'<rect x="{x0 + S * 0.36:.1f}" y="{y0 + S * 0.46:.1f}" width="{S * 0.28:.1f}" height="{S * 0.2:.1f}" fill="#e9e1d0" stroke="#5a3a2a" stroke-width="1"/>'
        )
        out.append(poly([(0.32, 0.46), (0.5, 0.3), (0.68, 0.46)], fill="#b8403a"))
    out.append(
        f'<rect x="{x0 + 0.5}" y="{y0 + 0.5}" width="{S - 1}" height="{S - 1}" fill="none" stroke="rgba(0,0,0,.4)" stroke-width="1"/>'
    )
    return "".join(out)


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
