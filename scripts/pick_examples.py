"""強いAIの対局記録から、解説ページの図版にする局面を選んでSVGで書き出す。

例:
    py scripts/pick_examples.py runs/habits_strong.jsonl --out runs/habits_examples.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from board_svg import board_svg, replay
from record_habits import dead_cells

from carcassonne.agents import GreedyAgent
from carcassonne.state import State

KIND_JA = {"C": "都市", "R": "道", "F": "草原（農民）", "M": "修道院"}


def render_after(game, ply, extra_labels=(), radius=2):
    deck = State.new_game(game["seed"]).deck
    st, meeples = replay(deck, game["history"], ply + 1)
    x, y = game["history"][ply][:2]
    return board_svg(
        st, meeples, (x, y), radius=radius, highlight=[(x, y, "#f5b400")], labels=list(extra_labels)
    )


def render_ghost(game, ply, radius=2):
    """着手直前の盤面に、AIが置いたタイルを枠付きで重ねて描く（直後に回収されるミープルも見える）。"""
    deck = State.new_game(game["seed"]).deck
    st, meeples = replay(deck, game["history"], ply)
    x, y, _, vi, _ = game["history"][ply]
    return board_svg(
        st, meeples, (x, y), radius=radius, highlight=[(x, y, "#f5b400")], ghost=[(x, y, vi, "")]
    )


def render_before(game, ply, radius=2):
    deck = State.new_game(game["seed"]).deck
    st, meeples = replay(deck, game["history"], ply)
    x, y = game["history"][ply][:2]
    return st, meeples, (x, y)


def pick(games):
    ex = {}
    # 1. 都市の封鎖: 相手のミープル付き都市の隣に、残りタイルでは埋まらない穴を作った
    for g in games:
        for m in g["moves"]:
            if (
                any(b["owner"] == "opp" and b["kind"] == "C" for b in m["newly_blocked"])
                and 12 < m["left"] < 50
            ):
                deck = State.new_game(g["seed"]).deck
                st, _ = replay(deck, g["history"], m["ply"] + 1)
                x, y = g["history"][m["ply"]][:2]
                holes = [c for c in dead_cells(st) if abs(c[0] - x) + abs(c[1] - y) == 1]
                if not holes:
                    continue
                ex["block"] = {
                    "svg": render_after(g, m["ply"], [(hx, hy, "×") for hx, hy in holes]),
                    "seed": g["seed"],
                    "ply": m["ply"],
                    "left": m["left"],
                    "mover": m["player"],
                    "meeple": m["meeple"],
                }
                break
        if "block" in ex:
            break
    # 2. 合流（相手の都市に、自分のミープルがいる都市を繋げて共有・横取りする）
    for g in games:
        for m in g["moves"]:
            if not (
                any(lk["merge_contested"] and lk["kind"] == "C" for lk in m["links"])
                and m["left"] > 15
            ):
                continue
            deck = State.new_game(g["seed"]).deck
            st, meeples = replay(deck, g["history"], m["ply"] + 1)
            x, y = g["history"][m["ply"]][:2]
            near = [q for q in meeples if abs(q["x"] - x) <= 2 and abs(q["y"] - y) <= 2]
            roots = {}
            for q in near:
                r = st._find(st.tile_nodes[(q["x"], q["y"])][q["piece"]])
                if st.kind[r] == "C":
                    roots.setdefault(r, set()).add(q["player"])
            if not any(len(v) == 2 for v in roots.values()):
                continue
            ex["merge"] = {
                "svg": render_after(g, m["ply"]),
                "seed": g["seed"],
                "ply": m["ply"],
                "left": m["left"],
                "mover": m["player"],
                "scored": m["scored"],
            }
            break
        if "merge" in ex:
            break
    # 3. あえて置かない: 序盤、同じ場所に置くが、貪欲法なら置くミープルを置かない
    for g in games:
        for m in g["moves"]:
            if (
                m["left"] > 40
                and m["meeple"] is None
                and m["same_place_as_greedy"]
                and m["supply"][0] >= 4
            ):
                st, meeples, pos = render_before(g, m["ply"])
                gm = GreedyAgent().act(st, __import__("random").Random(0))
                if gm.piece is None or (gm.x, gm.y, gm.variant) != pos + (
                    g["history"][m["ply"]][3],
                ):
                    continue
                kind = st.ts.types[st.current].variants[gm.variant].pieces[gm.piece].kind
                if kind not in ("R", "C"):
                    continue
                ex["skip"] = {
                    "svg": render_after(g, m["ply"]),
                    "seed": g["seed"],
                    "ply": m["ply"],
                    "left": m["left"],
                    "mover": m["player"],
                    "greedy_kind": kind,
                    "supply": m["supply"],
                }
                break
        if "skip" in ex:
            break
    # 4. 農民: 終盤、完成都市2つ以上に接する草原へ
    best = None
    for g in games:
        for m in g["moves"]:
            mm = m["meeple"]
            if mm and mm["kind"] == "F" and m["left"] < 20:
                score = mm["cities_done"] * 10 + mm["cities_open"]
                if best is None or score > best[0]:
                    best = (score, g, m)
    if best:
        _, g, m = best
        ex["farm"] = {
            "svg": render_after(g, m["ply"], radius=3),
            "seed": g["seed"],
            "ply": m["ply"],
            "left": m["left"],
            "mover": m["player"],
            "cities_done": m["meeple"]["cities_done"],
            "cities_open": m["meeple"]["cities_open"],
        }
    # 5. 修道院の周りを埋める（自分の修道院を完成させた手）
    for g in games:
        for m in g["moves"]:
            if "mine" in m["around_monastery"] and m["scored"][0] >= 9 and 10 < m["left"] < 55:
                ex["monastery"] = {
                    "svg": render_ghost(g, m["ply"]),
                    "seed": g["seed"],
                    "ply": m["ply"],
                    "left": m["left"],
                    "mover": m["player"],
                    "scored": m["scored"],
                }
                break
        if "monastery" in ex:
            break
    return ex


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    games = [json.loads(line) for line in Path(args.path).read_text(encoding="utf-8").splitlines()]
    ex = pick(games)
    Path(args.out).write_text(json.dumps(ex, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in ex.items():
        print(k, {kk: vv for kk, vv in v.items() if kk != "svg"})


if __name__ == "__main__":
    main()
