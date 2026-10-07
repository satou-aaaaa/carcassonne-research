"""「この局面ならどこに置く？」形式の練習問題を、AIの探索結果から作る。

自己対戦の途中局面で、AI（評価関数付きMCTS）が根の候補手ごとに集めた訪問数と平均報酬を
取り出し、平均報酬を「予想最終点差」に換算して手の良し悪しを比べる。最善手と、それより
はっきり劣る自然な候補手が並ぶ局面を問題として採用する。

点差への換算は探索の報酬 r = 0.5 + 0.5*tanh(diff/scale) の逆関数で、あくまでAIの見積もり。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .fast import C0, G, seed_rng
from .fast_mcts import FastMCTSAgent, search_stats
from .state import Move, State
from .tiles import CITY, FIELD, MONASTERY, ROAD

KIND_JA = {CITY: "都市", ROAD: "道", FIELD: "草原", MONASTERY: "修道院"}


@dataclass
class Option:
    """根の候補手1つ（配置＋ミープル）のAI評価。diff は手番側視点の予想最終点差。"""

    move: Move
    visits: int
    diff: float


def reward_to_diff(r: float, scale: float) -> float:
    r = min(max(r, 1e-6), 1 - 1e-6)
    return scale * math.atanh(2 * r - 1)


def analyze(agent: FastMCTSAgent, state: State, seed: int, min_visits: int = 1) -> list[Option]:
    """state（手番側が指す局面）を探索し、候補手を訪問数の多い順に返す。"""
    seed_rng(seed)
    S = agent.to_fast(state)
    sc = agent.fast.scratch
    depth = (
        agent.rollout_depth if agent.rollout_depth is not None else (0 if agent.eval_path else -1)
    )
    scale = agent.reward_scale or 30.0
    cells, gs, _, _, agg2, aggw2 = search_stats(
        S, agent.fast.T, agent.fast.P, agent.n_sims, agent.n_det, agent.c, scale,
        agent.meeple_prob, depth, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, sc.free,
        sc.rec, agent.eval_w, agent.eval_mode, agent.fbuf, agent.late,
    )  # fmt: skip
    base = int(agent.fast.T[11][state.current])
    out: list[Option] = []
    for k in range(len(cells)):
        x, y = int(cells[k]) // G - C0, int(cells[k]) % G - C0
        for q in np.nonzero(agg2[k] >= min_visits)[0]:
            n = int(agg2[k, q])
            piece = None if q == 0 else int(q) - 1
            out.append(
                Option(
                    Move(x, y, int(gs[k]) - base, piece), n, reward_to_diff(aggw2[k, q] / n, scale)
                )
            )
    out.sort(key=lambda o: -o.visits)
    return out


def track_meeples(st: State, meeples: list[dict], move: Move, player: int) -> list[dict]:
    """着手後の盤上ミープル一覧（State は位置を持たないため外で追跡する）。st は適用済み。"""
    if move.piece is not None:
        meeples = meeples + [{"x": move.x, "y": move.y, "piece": move.piece, "player": player}]
    return [
        m
        for m in meeples
        if st.meeples[st._find(st.tile_nodes[(m["x"], m["y"])][m["piece"]])][m["player"]] > 0
    ]


def move_facts(st: State, move: Move) -> dict:
    """着手の客観的な事実（即時得点、ミープルの置き先、相乗りの有無、予測得点の変化）。"""
    me = st.player
    v = st.ts.types[st.current].variants[move.variant]
    before, proj_before = list(st.scores), st.projected_scores()
    nxt = st.copy()
    nxt.apply(move)
    proj_after = nxt.projected_scores()
    facts: dict = {
        "gain_me": nxt.scores[me] - before[me],
        "gain_opp": nxt.scores[1 - me] - before[1 - me],
        "proj_me": proj_after[me] - proj_before[me],
        "proj_opp": proj_after[1 - me] - proj_before[1 - me],
        "meeple": None,
    }
    if move.piece is not None:
        p = v.pieces[move.piece]
        r = nxt._find(nxt.tile_nodes[(move.x, move.y)][move.piece])
        m = nxt.meeples[r]
        info = {"kind": p.kind, "kind_ja": KIND_JA[p.kind], "returned": m[me] == 0}
        if p.kind in (CITY, ROAD) and m[me] > 0:
            info["tiles"] = len(nxt.tiles[r])
            info["shared"] = m[1 - me] > 0
        if p.kind == FIELD and m[me] > 0:
            cities = {nxt._find(c) for c in nxt.field_cities[r]}
            info["done_cities"] = sum(1 for c in cities if nxt.open_ends[c] == 0)
            info["shared"] = m[1 - me] > 0
        facts["meeple"] = info
    return facts


def describe(facts: dict) -> str:
    """事実から短い日本語の説明を作る（手書きの解説の補助）。"""
    parts = []
    mp = facts["meeple"]
    if mp is None:
        parts.append("ミープルは置かない")
    elif mp["returned"]:
        parts.append(f"{mp['kind_ja']}にミープルを置き、その場で完成して回収")
    else:
        s = f"{mp['kind_ja']}にミープルを置く"
        if mp.get("shared"):
            s += "（相手と相乗り）"
        parts.append(s)
    if facts["gain_me"] or facts["gain_opp"]:
        g = f"即座に自分+{facts['gain_me']}点"
        if facts["gain_opp"]:
            g += f"・相手+{facts['gain_opp']}点"
        parts.append(g)
    return "、".join(parts)


def snapshot(st: State, meeples: list[dict]) -> dict:
    return {
        "board": [{"x": x, "y": y, "t": t, "v": v} for (x, y), (t, v) in st.board.items()],
        "meeples": [dict(m) for m in meeples],
        "scores": list(st.scores),
        "projected": st.projected_scores(),
        "supply": list(st.supply),
        "player": st.player,
        "current": st.current,
        "remaining": st.remaining_counts(),
        "deck_left": len(st.deck) - st.draw_pos,
        "turn": len(st.history) + 1,
    }


def pick_options(opts: list[Option], k: int = 4, min_share: float = 0.01) -> list[Option]:
    """問題の選択肢: 最善手（訪問数最大）と、AIもよく検討した（訪問の多い）劣る手から最大 k-1 個。

    同じマス・同じ向きの手（ミープルだけ違う手）は高々2つまでにする。
    """
    total = sum(o.visits for o in opts)
    good = [o for o in opts if o.visits >= min_share * total]
    if not good:
        return []
    best = max(good, key=lambda o: o.visits)
    chosen = [best]
    for o in good:
        if len(chosen) >= k:
            break
        if o is best or o.diff >= best.diff:
            continue
        if sum(c.move[:3] == o.move[:3] for c in chosen) >= 2:
            continue
        chosen.append(o)
    return chosen
