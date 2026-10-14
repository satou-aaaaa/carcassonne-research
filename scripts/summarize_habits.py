"""`record_habits.py` の記録を集計し、AIの指し方の傾向を数値で出す。

例:
    py scripts/summarize_habits.py runs/habits_strong.jsonl runs/habits_greedy.jsonl --json runs/habits_summary.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carcassonne.state import Move, State

KINDS = ["C", "R", "M", "F"]
PHASES = [("序盤", 47, 99), ("中盤", 24, 46), ("終盤", 0, 23)]  # 残りタイル枚数で区切る


def phase_of(left: int) -> str:
    for name, lo, hi in PHASES:
        if lo <= left <= hi:
            return name
    return "終盤"


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def meeple_lives(game: dict) -> list[dict]:
    """棋譜を再生し、置いたミープル1個ごとに (種別, 置いた時の残り枚数, 拘束手数, 得点) を返す。"""
    st = State(State.new_game(game["seed"]).deck)
    got: dict[int, list[int]] = {}
    orig = State._award

    def award(self, root, points):
        m = self.meeples[root]
        top = max(m)
        got[root] = [points if top > 0 and m[p] == top else 0 for p in (0, 1)]
        orig(self, root, points)

    State._award = award
    active, out = [], []
    try:
        for ply, (x, y, ti, vi, piece) in enumerate(game["history"]):
            player = st.player
            left = len(st.deck) - st.draw_pos
            got.clear()
            st.apply(Move(x, y, vi, piece))
            if piece is not None:
                kind = st.ts.types[ti].variants[vi].pieces[piece].kind
                active.append(
                    {
                        "node": st.tile_nodes[(x, y)][piece],
                        "player": player,
                        "kind": kind,
                        "ply": ply,
                        "left": left,
                    }
                )
            keep = []
            for a in active:
                r = st._find(a["node"])
                if r in got:
                    out.append(
                        {
                            "kind": a["kind"],
                            "player": a["player"],
                            "left": a["left"],
                            "turns": (ply - a["ply"]) // 2,
                            "points": got[r][a["player"]],
                            "end": st.over,
                        }
                    )
                else:
                    keep.append(a)
            active = keep
    finally:
        State._award = orig
    return out


def summarize(path: str) -> dict:
    games = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
    moves = [m for g in games for m in g["moves"]]
    out: dict = {"level": games[0]["level"], "games": len(games), "moves": len(moves)}

    # 得点
    totals = [s for g in games for s in g["scores"]]
    out["avg_score"] = mean(totals)
    out["avg_winner_score"] = mean(max(g["scores"]) for g in games)
    out["first_player_win"] = mean(
        1.0 if g["scores"][0] > g["scores"][1] else 0.5 if g["scores"][0] == g["scores"][1] else 0.0
        for g in games
    )
    src = Counter()
    for g in games:
        for a in g["awards"]:
            key = ("F" if a["kind"] == "F" else a["kind"]) + ("_end" if a["end"] else "_done")
            src[key] += a["points"]
    n_player_games = 2 * len(games)
    out["points_by_source"] = {k: v / n_player_games for k, v in sorted(src.items())}
    win_src, lose_src = Counter(), Counter()
    for g in games:
        s = g["scores"]
        if s[0] == s[1]:
            continue
        w = 0 if s[0] > s[1] else 1
        for a in g["awards"]:
            (win_src if a["player"] == w else lose_src)[a["kind"]] += a["points"]
    decided = sum(1 for g in games if g["scores"][0] != g["scores"][1])
    out["winner_points_by_kind"] = {k: win_src[k] / decided for k in KINDS}
    out["loser_points_by_kind"] = {k: lose_src[k] / decided for k in KINDS}
    out["shared_points_share"] = sum(
        a["points"] for g in games for a in g["awards"] if a["shared"]
    ) / max(1, sum(totals))

    # ミープル
    out["meeple_rate"] = mean(1.0 if m["meeple"] else 0.0 for m in moves)
    by_phase = {}
    for name, lo, hi in PHASES:
        ms = [m for m in moves if lo <= m["left"] <= hi]
        kinds = Counter(m["meeple"]["kind"] for m in ms if m["meeple"])
        by_phase[name] = {
            "moves": len(ms),
            "meeple_rate": mean(1.0 if m["meeple"] else 0.0 for m in ms),
            "kind_rate": {k: kinds[k] / len(ms) for k in KINDS},
            "avg_supply": mean(m["supply"][0] for m in ms),
        }
    out["by_phase"] = by_phase
    placed = [m["meeple"] for m in moves if m["meeple"]]
    kinds = Counter(p["kind"] for p in placed)
    out["meeple_kind_share"] = {k: kinds[k] / len(placed) for k in KINDS}
    out["meeple_returned_now"] = mean(1.0 if p.get("returned_now") else 0.0 for p in placed)
    out["meeple_joins_existing"] = mean(1.0 if p["joins"] else 0.0 for p in placed)
    city = [p for p in placed if p["kind"] == "C"]
    road = [p for p in placed if p["kind"] == "R"]
    out["city_meeple_new"] = mean(1.0 if p["joins"] == 0 else 0.0 for p in city)
    out["road_meeple_new"] = mean(1.0 if p["joins"] == 0 else 0.0 for p in road)
    out["city_meeple_size"] = mean(p["size"] for p in city)
    out["road_meeple_size"] = mean(p["size"] for p in road)
    out["city_meeple_pennant"] = mean(1.0 if p["pennants"] else 0.0 for p in city)
    farms = [m for m in moves if m["meeple"] and m["meeple"]["kind"] == "F"]
    out["farm_first_left"] = mean(  # 各プレイヤーが最初に農民を置いたときの残りタイル枚数
        max(firsts)
        for g in games
        for p in (0, 1)
        if (
            firsts := [
                m["left"]
                for m in g["moves"]
                if m["player"] == p and m["meeple"] and m["meeple"]["kind"] == "F"
            ]
        )
    )
    out["farm_per_player_game"] = len(farms) / n_player_games
    out["farm_cities_at_place"] = mean(
        m["meeple"]["cities_done"] + m["meeple"]["cities_open"] for m in farms
    )
    out["farm_done_at_place"] = mean(m["meeple"]["cities_done"] for m in farms)
    # ミープル1個あたりの拘束手数と得点
    lives = [life for g in games for life in meeple_lives(g)]
    by = defaultdict(list)
    for life in lives:
        by[life["kind"]].append(life)
    out["meeple_life"] = {
        k: {
            "n": len(v),
            "turns": mean(x["turns"] for x in v),
            "points": mean(x["points"] for x in v),
            "points_per_turn": sum(x["points"] for x in v)
            / max(1, sum(max(1, x["turns"]) for x in v)),
            "stuck_to_end": mean(1.0 if x["end"] else 0.0 for x in v),
            "zero_points": mean(1.0 if x["points"] == 0 else 0.0 for x in v),
        }
        for k, v in by.items()
    }
    # 手持ちの推移（自分の手番開始時）
    curve = {}
    for left_mark in range(70, 0, -2):
        vals = [m["supply"][0] for m in moves if m["left"] == left_mark]
        curve[left_mark] = mean(vals)
    out["supply_curve"] = curve
    out["zero_supply_rate"] = mean(1.0 if m["supply"][0] == 0 else 0.0 for m in moves)
    # ミープルを置けるのに置かなかった割合（手持ちあり）
    has = [m for m in moves if m["supply"][0] > 0]
    out["skip_meeple_with_supply"] = mean(0.0 if m["meeple"] else 1.0 for m in has)

    # タイル配置
    def link_kind(m):
        own = any(lk["mine"] > 0 and lk["opp"] == 0 for lk in m["links"])
        opp = any(lk["opp"] > 0 and lk["mine"] == 0 for lk in m["links"])
        contested = any(lk["merge_contested"] for lk in m["links"])
        return own, opp, contested

    lk = [link_kind(m) for m in moves]
    out["extends_own"] = mean(1.0 if o else 0.0 for o, _, _ in lk)
    out["touches_opp"] = mean(1.0 if p else 0.0 for _, p, _ in lk)
    out["contested_merge"] = mean(1.0 if c else 0.0 for _, _, c in lk)
    out["touches_opp_only"] = mean(1.0 if p and not o else 0.0 for o, p, _ in lk)
    out["helps_opp_score_now"] = mean(1.0 if m["scored"][1] > 0 else 0.0 for m in moves)
    out["opp_points_given_per_move"] = mean(m["scored"][1] for m in moves)
    out["own_points_per_move"] = mean(m["scored"][0] for m in moves)
    out["around_own_monastery"] = mean(
        1.0 if "mine" in m["around_monastery"] else 0.0 for m in moves
    )
    out["around_opp_monastery"] = mean(
        1.0 if "opp" in m["around_monastery"] else 0.0 for m in moves
    )
    blocks = Counter()
    for m in moves:
        for b in m["newly_blocked"]:
            blocks[(b["owner"], b["kind"])] += 1
    out["blocks_per_game_player"] = {f"{o}_{k}": v / n_player_games for (o, k), v in blocks.items()}
    out["proj_gain_diff"] = mean(m["proj_gain"][0] - m["proj_gain"][1] for m in moves)
    if any("same_as_greedy" in m and m["same_as_greedy"] for m in moves):
        out["same_as_greedy"] = mean(1.0 if m["same_as_greedy"] else 0.0 for m in moves)
        out["same_place_as_greedy"] = mean(1.0 if m["same_place_as_greedy"] else 0.0 for m in moves)
    # 「同点の共有」を狙った合流
    out["contested_merge_with_meeple"] = mean(
        1.0 if any(lk["merge_contested"] for lk in m["links"]) else 0.0 for m in moves
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json")
    args = ap.parse_args()
    res = {Path(p).stem: summarize(p) for p in args.paths}
    text = json.dumps(res, ensure_ascii=False, indent=1)
    print(text)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
