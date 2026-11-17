"""独立した別実装（wingedsheep/carcassonne、MIT）で同じ棋譜をたどり、終局の得点を突き合わせる（R-004）。

別実装のコードはこのリポジトリに取り込まない。`--ref` に、別に clone したその実装のフォルダを渡す:

    git clone https://github.com/wingedsheep/carcassonne.git <dir>
    git -C <dir> checkout e80dbb429e0d74727d0df2038802a42188b6fc62
    python scripts/crosscheck_wingedsheep.py --ref <dir> --games 100 --out docs/results/crosscheck.json

やること:
1. こちらのエンジン（`carcassonne.state.State`）で対局を作る（ランダムな手の対局と、探索AIの対局を半々）。
2. 同じ山札の並び・同じ着手（場所・向き・ミープルの位置）を別実装に1手ずつ与える。タイルの向きは辺と
   都市・道・草原のつながりの形で、ミープルの位置は特徴（都市・道・草原・修道院）で対応づける。
3. 1手ごとの得点と終局の得点を比べ、最初に食い違った手と、その手で何が起きたかを記録する。

別実装には公式ルールと違う所がある（同数のミープルで引き分けた特徴に、誰にも点を入れない）。
`--official-ties` を付けると、その所だけ公式ルール（同数なら全員が満点）に差し替えて比べる。
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne.agents import RandomAgent
from carcassonne.state import State
from carcassonne.tiles import CITY, FIELD, MONASTERY, ROAD

PINNED = "e80dbb429e0d74727d0df2038802a42188b6fc62"
# こちらの半辺 side*2+h（辺の上を時計回り）→ 別実装の FarmerSide の名前
HALF_NAMES = ["tlt", "trt", "trr", "brr", "brb", "blb", "bll", "tll"]
SIDE_NAMES = ["top", "right", "bottom", "left"]
OFF = 50  # 別実装の盤の中心（行・列）。こちらの (x, y) は (行 OFF-y, 列 OFF+x)


def load_ref(ref: Path):
    sys.path.insert(0, str(ref))
    from wingedsheep.carcassonne.carcassonne_game_state import CarcassonneGameState
    from wingedsheep.carcassonne.objects.actions.meeple_action import MeepleAction
    from wingedsheep.carcassonne.objects.actions.pass_action import PassAction
    from wingedsheep.carcassonne.objects.actions.tile_action import TileAction
    from wingedsheep.carcassonne.objects.coordinate import Coordinate
    from wingedsheep.carcassonne.objects.meeple_type import MeepleType
    from wingedsheep.carcassonne.tile_sets.base_deck import base_tile_counts, base_tiles
    from wingedsheep.carcassonne.tile_sets.supplementary_rules import SupplementaryRule
    from wingedsheep.carcassonne.tile_sets.tile_sets import TileSet
    from wingedsheep.carcassonne.utils.action_util import ActionUtil
    from wingedsheep.carcassonne.utils.points_collector import PointsCollector
    from wingedsheep.carcassonne.utils.state_updater import StateUpdater

    return {
        "State": CarcassonneGameState, "MeepleAction": MeepleAction, "PassAction": PassAction,
        "TileAction": TileAction, "Coordinate": Coordinate, "MeepleType": MeepleType,
        "base_tiles": base_tiles, "base_tile_counts": base_tile_counts, "Rule": SupplementaryRule,
        "TileSet": TileSet, "ActionUtil": ActionUtil, "Points": PointsCollector, "Updater": StateUpdater,
    }  # fmt: skip


class Tied(int):
    """同数で引き分けた勝者たち（int としては先頭の1人）。"""

    players: tuple[int, ...] = ()


class TieScores(list):
    """`scores[勝者] += 点` の勝者が Tied なら、同数の全員に同じ点を足す得点表。"""

    def __setitem__(self, i, v):
        if isinstance(i, Tied):
            delta = v - list.__getitem__(self, int(i))
            for p in i.players:
                list.__setitem__(self, p, list.__getitem__(self, p) + delta)
        else:
            list.__setitem__(self, i, v)


def patch_official_ties(R) -> None:
    """別実装の得点処理のうち「同数なら誰も得点しない」所だけを、公式ルール（同数なら全員が満点）に差し替える。

    別実装は勝者1人（int か None）を返し `scores[勝者] += 点` と足す形なので、同数のときは Tied を返し、
    得点表 TieScores が同数の全員に足す（別実装のコードは書き換えない）。
    """
    import numpy as np

    def winner(c):
        c = np.array(c)
        top = c.max()
        if top <= 0:
            return None
        w = tuple(int(i) for i in np.argwhere(c == top).ravel())
        if len(w) == 1:
            return w[0]
        t = Tied(w[0])
        t.players = w
        return t

    R["Points"].get_winning_player = staticmethod(winner)
    R["tie_scores"] = True


def piece_sig(v):
    """こちらの Variant を、向きで変わる形の署名にする（別実装のタイルと突き合わせる用）。"""
    cities, roads, fields = [], [], []
    mon = False
    for p in v.pieces:
        if p.kind == CITY:
            cities.append((tuple(sorted(SIDE_NAMES[s] for s in p.sides)), p.pennant))
        elif p.kind == ROAD:
            roads.append(tuple(sorted(SIDE_NAMES[s] for s in p.sides)))
        elif p.kind == FIELD:
            adj = tuple(sorted(s for c in p.city_adj for s in v.pieces[c].sides))
            fields.append((tuple(sorted(HALF_NAMES[h] for h in p.halves)), adj))
        elif p.kind == MONASTERY:
            mon = True
    return (tuple(sorted(cities)), tuple(sorted(roads)), tuple(sorted(fields)), mon)


def ref_sig(t):
    """別実装の（回したあとの）タイルの署名。都市・道・草原の分け方と盾・修道院。"""
    shield = bool(t.shield)
    cities = [(tuple(sorted(str(s) for s in c)), shield) for c in t.city]
    # 別実装は盾を「タイルに1つ」で持つ。都市が1つより多いタイルに盾は無い（基本セット）
    ends: dict = {}
    for i, c in enumerate(t.road):
        for s in (c.a, c.b):
            if str(s) != "center":
                ends.setdefault(i, []).append(str(s))
    # 端が CENTER の道（行き止まり）は1辺だけの道。両端が辺の道は2辺の道
    roads = [tuple(sorted(e)) for e in ends.values()]
    side_idx = {n: i for i, n in enumerate(SIDE_NAMES)}
    fields = []
    for f in t.farms:
        adj = tuple(sorted(side_idx[str(s)] for s in f.city_sides))
        fields.append((tuple(sorted(str(h) for h in f.tile_connections)), adj))
    return (tuple(sorted(cities)), tuple(sorted(roads)), tuple(sorted(fields)), bool(t.chapel))


def tile_map(R, ts):
    """こちらの (種別, 向き) → (別実装のタイル名, 回転数)。形がちょうど1通りに決まることを確かめる。"""
    sigs: dict = {}
    for name, t in R["base_tiles"].items():
        for k in range(4):
            sigs.setdefault(ref_sig(t.turn(k)), []).append((name, k))
    out = {}
    for ti, tt in enumerate(ts.types):
        for vi, v in enumerate(tt.variants):
            m = sigs.get(piece_sig(v))
            if not m:
                raise SystemExit(f"別実装に形の合うタイルがない: {tt.id} 向き{vi} {piece_sig(v)}")
            # 絵柄違い（花の有無）の同形タイルは同じ扱い。名前は1つに決める
            out[(ti, vi)] = min(m)
    return out


def ref_counts_by_shape(R) -> Counter:
    """別実装の基本セットの枚数を、こちらの種別の形（回転0の署名）でまとめる。"""
    c: Counter = Counter()
    for name, n in R["base_tile_counts"].items():
        t = R["base_tiles"][name]
        c[min(ref_sig(t.turn(k)) for k in range(4))] += n
    return c


def our_counts_by_shape(ts) -> Counter:
    c: Counter = Counter()
    for tt in ts.types:
        c[min(piece_sig(v) for v in tt.variants)] += tt.count
    return c


def meeple_side(v, piece: int, ref_tile) -> tuple[str, str]:
    """こちらの断片 → 別実装の (MeepleType 名, Side 名)。"""
    p = v.pieces[piece]
    if p.kind == MONASTERY:
        return "NORMAL", "center"
    if p.kind in (CITY, ROAD):
        return "NORMAL", SIDE_NAMES[p.sides[0]]
    halves = {HALF_NAMES[h] for h in p.halves}
    for f in ref_tile.farms:
        if {str(h) for h in f.tile_connections} == halves:
            return "FARMER", str(f.farmer_positions[0])
    raise ValueError("草原の対応が見つからない")


def make_games(n: int, start: int, mcts_sims: int) -> list[dict]:
    """半分はランダムな手（珍しい形が出やすい）、半分は探索AIどうしの対局を作る。"""
    from carcassonne.fast_mcts import FastMCTSAgent

    games = []
    for i in range(n):
        seed = start + i
        st = State.new_game(seed)
        rng = random.Random(seed)
        if i % 2 == 0:
            agents = [RandomAgent(), RandomAgent()]
            kind = "random"
        else:
            agents = [FastMCTSAgent(n_sims=mcts_sims), FastMCTSAgent(n_sims=mcts_sims)]
            kind = f"fmcts{mcts_sims}"
        trace = []
        while not st.over:
            st.apply(agents[st.player].act(st, rng))
            trace.append(list(st.scores))
        games.append(
            {"seed": seed, "kind": kind, "history": [list(h) for h in st.history], "trace": trace,
                 "scores": list(st.scores), "discarded": len(st.discarded)}
        )  # fmt: skip
    return games


def replay(R, ts, tmap, g) -> dict:
    """別実装で棋譜をたどる。1手ごとの得点を返す（合法手に無い手があれば、そこで止めて理由を返す）."""
    T = R["base_tiles"]
    st = R["State"](
        tile_sets=[R["TileSet"].BASE], supplementary_rules=[R["Rule"].FARMERS],
        players=2, board_size=(2 * OFF + 1, 2 * OFF + 1), starting_position=R["Coordinate"](OFF, OFF),
    )  # fmt: skip
    if R.get("tie_scores"):
        st.scores = TieScores(st.scores)
    name0, k0 = tmap[(ts.start, 0)]
    st.board[OFF][OFF] = T[name0].turn(k0)
    hist = g["history"]
    st.deck = [T[tmap[(h[2], 0)][0]] for h in hist[1:]]
    st.next_tile = T[tmap[(hist[0][2], 0)][0]]
    trace = []
    for i, (x, y, ti, vi, piece) in enumerate(hist):
        name, k = tmap[(ti, vi)]
        coord = R["Coordinate"](OFF - y, OFF + x)
        want = ref_sig(T[name].turn(k))
        acts = R["ActionUtil"].get_possible_actions(st)
        act = next(
            (
                a
                for a in acts
                if isinstance(a, R["TileAction"])
                and a.coordinate == coord
                and ref_sig(a.tile) == want
            ),
            None,
        )
        if act is None:
            return {"trace": trace, "stop": i, "why": "タイルの置き方が別実装の合法手に無い"}
        with contextlib.redirect_stdout(io.StringIO()):
            st = R["Updater"].apply_action(st, act)
        if piece is None:
            m = R["PassAction"]()
        else:
            v = ts.types[ti].variants[vi]
            mt, side = meeple_side(v, piece, act.tile)
            acts = R["ActionUtil"].get_possible_actions(st)
            m = next(
                (
                    a
                    for a in acts
                    if isinstance(a, R["MeepleAction"])
                    and a.meeple_type.name == mt
                    and a.coordinate_with_side.coordinate == coord
                    and str(a.coordinate_with_side.side) == side
                ),
                None,
            )
            if m is None:
                return {
                    "trace": trace,
                    "stop": i,
                    "why": f"ミープル（{mt} {side}）が別実装の合法手に無い",
                }
        with contextlib.redirect_stdout(io.StringIO()):
            st = R["Updater"].apply_action(st, m)
        trace.append(list(st.scores))
    return {"trace": trace, "stop": None, "why": None}


def tie_events(g, upto: int) -> bool:
    """こちらの手 upto（0始まり）の得点で、2人に同じ点が同時に入ったか（同数の引き分け）。"""
    before = [0, 0] if upto == 0 else g["trace"][upto - 1]
    after = g["trace"][upto]
    d = [after[0] - before[0], after[1] - before[1]]
    return d[0] > 0 and d[0] == d[1]


def compare(R, ts, tmap, games) -> dict:
    rows = []
    for g in games:
        r = replay(R, ts, tmap, g)
        ours = g["trace"]
        first = None
        for i, s in enumerate(r["trace"]):
            if s != ours[i]:
                first = i
                break
        last = len(hist := g["history"]) - 1
        if first is None and r["stop"] is None and r["trace"] and r["trace"][-1] != g["scores"]:
            first = last  # 終局の数え（最後の手のあと）だけが食い違う
        row = {
            "seed": g["seed"], "kind": g["kind"], "ours": g["scores"],
            "theirs": r["trace"][-1] if r["trace"] else None, "stop": r["stop"], "why": r["why"],
            "first_diff": first, "plies": len(hist),
        }  # fmt: skip
        if first is not None:
            row["ours_at"] = ours[first]
            row["theirs_at"] = r["trace"][first]
            row["final_only"] = first == last
            row["tie"] = tie_events(g, first) if first < last else None
        rows.append(row)
    match = sum(1 for r in rows if r["first_diff"] is None and r["stop"] is None)
    return {"games": len(rows), "match": match, "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", required=True, help="wingedsheep/carcassonne を clone したフォルダ")
    ap.add_argument("--games", type=int, default=100)
    ap.add_argument("--start", type=int, default=40000)
    ap.add_argument("--sims", type=int, default=300, help="探索AIの対局の1手の探索回数")
    ap.add_argument(
        "--official-ties", action="store_true", help="別実装の同数の扱いを公式ルールに差し替える"
    )
    ap.add_argument("--out", help="結果の JSON")
    a = ap.parse_args()
    R = load_ref(Path(a.ref))
    from carcassonne.tiles import load_tileset

    ts = load_tileset()
    if ref_counts_by_shape(R) != our_counts_by_shape(ts):
        raise SystemExit("タイルの形ごとの枚数が別実装と合わない")
    tmap = tile_map(R, ts)
    games = make_games(a.games, a.start, a.sims)
    res = {"ref": f"wingedsheep/carcassonne@{PINNED[:12]}", "tiles_match": True}
    res["as_is"] = compare(R, ts, tmap, games)
    patch_official_ties(R)
    res["official_ties"] = compare(R, ts, tmap, games)
    for key in ("as_is", "official_ties"):
        r = res[key]
        bad = [x for x in r["rows"] if x["first_diff"] is not None or x["stop"] is not None]
        kinds = Counter(
            "合法手の違い" if x["stop"] is not None else ("終局の数え" if x["final_only"] else
            ("同数の引き分け" if x["tie"] else "途中の得点")) for x in bad
        )  # fmt: skip
        r["mismatch_kinds"] = dict(kinds)
        print(f"{key}: {r['match']}/{r['games']} 局が全手一致 食い違い {dict(kinds)}")
    if a.out:
        Path(a.out).write_text(
            json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
