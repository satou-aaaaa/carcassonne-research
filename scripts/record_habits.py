"""AIの対局を1手ずつ詳しく記録する（戦略の傾向分析用）。

例:
    py scripts/record_habits.py strong --seeds 40 --workers 4 --out runs/habits_strong.jsonl
    py scripts/record_habits.py greedy --seeds 100 --workers 4 --out runs/habits_greedy.jsonl

同じエージェント同士の自己対戦を、シードごとに1局指す。1局を1行のJSONとして書き出し、
各手には「何に繋げたか・何を完成させたか・どこにミープルを置いたか・相手の特徴を
完成不能にしたか」などを記録する。集計は `scripts/summarize_habits.py`。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carcassonne.agents import GreedyAgent
from carcassonne.state import AROUND, DIRS, State
from carcassonne.tiles import CITY, FIELD, MONASTERY, ROAD

ROOT = Path(__file__).resolve().parents[1]


def make_agent(level: str):
    if level == "greedy":
        return GreedyAgent()
    from carcassonne.fast_mcts import FastMCTSAgent

    ev = str(ROOT / "models" / "eval_v6_lin.npy")
    if level == "strong":  # 対人用「最強」と同じ設定（webplay.make_agent）
        return FastMCTSAgent(n_sims=12000, rollout_depth=10, eval_path=ev)
    if level == "standard":
        return FastMCTSAgent(n_sims=2000, eval_path=ev)
    raise SystemExit(f"未知のレベル: {level}")


def dead_cells(st: State) -> set[tuple[int, int]]:
    """残りのどのタイルも置けない空きマス（そこに接する特徴は完成しなくなる）。"""
    counts = st.remaining_counts()
    if st.current is not None:
        counts[st.current] += 1  # 手番のタイルも未配置として数える
    live = [ti for ti, c in enumerate(counts) if c > 0]
    return {pos for pos in st.req if not any(st._fitting_variants(ti, pos) for ti in live)}


def blocked_features(st: State, near=None) -> dict[int, tuple[str, int, int]]:
    """完成不能になった未完成の都市・道・修道院（ミープル付きのみ）: 根 -> (種別, 自0, 自1)。

    near を渡すと、そのマスに辺で接する死にマスだけを見る（＝その配置が作った封鎖）。
    """
    out = {}
    cells = dead_cells(st)
    if near is not None:
        cells = {c for c in cells if abs(c[0] - near[0]) + abs(c[1] - near[1]) == 1}
    for pos in cells:
        for s, (dx, dy) in enumerate(DIRS):
            npos = (pos[0] + dx, pos[1] + dy)
            nb = st.board.get(npos)
            if nb is None:
                continue
            nv = st.ts.types[nb[0]].variants[nb[1]]
            pi = nv.side_piece[(s + 2) % 4]
            if pi is None:
                continue
            r = st._find(st.tile_nodes[npos][pi])
            if any(st.meeples[r]):
                out[r] = (st.kind[r], *st.meeples[r])
        for dx, dy in AROUND:
            mpos = (pos[0] + dx, pos[1] + dy)
            n = st.monasteries.get(mpos)
            if n is not None:
                r = st._find(n)
                if any(st.meeples[r]):
                    out[r] = (MONASTERY, *st.meeples[r])
    return out


def touched_features(st: State, pos, v):
    """pos に v を置いたとき、各断片が繋がる既存特徴の根（置く前の状態で）。"""
    res = []
    for pi, p in enumerate(v.pieces):
        roots = set()
        if p.kind in (CITY, ROAD):
            for s in p.sides:
                dx, dy = DIRS[s]
                npos = (pos[0] + dx, pos[1] + dy)
                nb = st.board.get(npos)
                if nb is None:
                    continue
                nv = st.ts.types[nb[0]].variants[nb[1]]
                roots.add(st._find(st.tile_nodes[npos][nv.side_piece[(s + 2) % 4]]))
        elif p.kind == FIELD:
            for hh in p.halves:
                s, h = divmod(hh, 2)
                dx, dy = DIRS[s]
                npos = (pos[0] + dx, pos[1] + dy)
                nb = st.board.get(npos)
                if nb is None:
                    continue
                nv = st.ts.types[nb[0]].variants[nb[1]]
                fp = nv.half_piece[((s + 2) % 4) * 2 + (1 - h)]
                if fp is not None:
                    roots.add(st._find(st.tile_nodes[npos][fp]))
        res.append((pi, p, roots))
    return res


def field_info(st: State, root: int) -> tuple[int, int]:
    """草原の根に隣接する (完成都市数, 未完成都市数)。"""
    cities = {st._find(c) for c in st.field_cities[root]}
    done = sum(1 for c in cities if st.open_ends[c] == 0)
    return done, len(cities) - done


def record_move(st: State, move, greedy_move) -> dict:
    me, op = st.player, 1 - st.player
    pos = (move.x, move.y)
    ti = st.current
    v = st.ts.types[ti].variants[move.variant]
    proj_before = st.projected_scores()
    blocked_before = blocked_features(st)
    rec = {
        "ply": len(st.history),
        "player": me,
        "tile": st.ts.types[ti].id,
        "left": len(st.deck) - st.draw_pos,
        "supply": [st.supply[me], st.supply[op]],
        "lead": proj_before[me] - proj_before[op],
        "same_as_greedy": greedy_move == move,
        "same_place_as_greedy": greedy_move is not None
        and (greedy_move.x, greedy_move.y, greedy_move.variant) == (move.x, move.y, move.variant),
    }
    # このタイルが繋がる既存特徴（誰のものか）
    links = []
    meeple_parts = {}
    for pi, p, roots in touched_features(st, pos, v):
        mm = [0, 0]
        for r in roots:
            mm[0] += st.meeples[r][me]
            mm[1] += st.meeples[r][op]
        if roots:
            links.append(
                {
                    "kind": p.kind,
                    "n": len(roots),
                    "mine": mm[0],
                    "opp": mm[1],
                    "merge_contested": sum(1 for r in roots if any(st.meeples[r])) >= 2
                    and mm[0] > 0
                    and mm[1] > 0,
                }
            )
        meeple_parts[pi] = (p, roots)
    rec["links"] = links
    # 修道院の周囲を埋めたか（誰の修道院か）
    mon = []
    for dx, dy in AROUND:
        n = st.monasteries.get((pos[0] + dx, pos[1] + dy))
        if n is not None:
            r = st._find(n)
            if st.meeples[r][me]:
                mon.append("mine")
            elif st.meeples[r][op]:
                mon.append("opp")
    rec["around_monastery"] = mon
    # ミープル
    if move.piece is not None:
        p, roots = meeple_parts[move.piece]
        m = {"kind": p.kind, "joins": len(roots)}
        if p.kind in (CITY, ROAD):
            tiles = {pos}
            pen = 1 if p.pennant else 0
            for r in roots:
                tiles |= st.tiles[r]
                pen += st.pennants[r]
            m["size"] = len(tiles)
            m["pennants"] = pen
        rec["meeple"] = m
    else:
        rec["meeple"] = None
    scores_before = list(st.scores)
    st.apply(move)
    rec["scored"] = [st.scores[me] - scores_before[me], st.scores[op] - scores_before[op]]
    proj_after = st.projected_scores()
    rec["proj_gain"] = [proj_after[me] - proj_before[me], proj_after[op] - proj_before[op]]
    # 置いたミープルの行き先（即完成で戻ったか、草原なら隣接都市数）
    if move.piece is not None:
        node = st.tile_nodes[pos][move.piece]
        r = st._find(node)
        rec["meeple"]["returned_now"] = (
            st.meeples[r][me] == 0 and v.pieces[move.piece].kind != FIELD
        )
        if v.pieces[move.piece].kind == FIELD:
            rec["meeple"]["cities_done"], rec["meeple"]["cities_open"] = field_info(st, r)
    if not st.over:
        blocked_after = blocked_features(st, near=pos)
        new = {r: t for r, t in blocked_after.items() if r not in blocked_before}
        # 根は統合で変わり得るので、種別と所有者だけ記録する
        rec["newly_blocked"] = [
            {"kind": k, "owner": "mine" if (m0, m1)[me] >= (m0, m1)[op] else "opp"}
            for k, m0, m1 in new.values()
        ]
    else:
        rec["newly_blocked"] = []
    return rec


def play(args):
    level, seed = args
    agent = make_agent(level)
    greedy = GreedyAgent()
    st = State.new_game(seed)
    rngs = [random.Random(seed * 2 + i) for i in (0, 1)]
    grng = random.Random(seed)
    awards = []  # 得点の内訳

    orig_award = State._award

    def award(self, root, points):
        m = self.meeples[root]
        top = max(m)
        if self is st and top > 0:  # 探索・貪欲法の試し指し（複製）は数えない
            for p in (0, 1):
                if m[p] == top:
                    awards.append(
                        {
                            "player": p,
                            "kind": self.kind[root],
                            "points": points,
                            "end": self.over,
                            "shared": m[0] == m[1],
                            "ply": len(self.history),
                        }
                    )
        orig_award(self, root, points)

    State._award = award
    moves = []
    supply_curve = []
    while not st.over:
        p = st.player
        mv = agent.act(st, rngs[p])
        gmv = greedy.act(st, grng) if level != "greedy" else None
        supply_curve.append([st.supply[0], st.supply[1]])
        moves.append(record_move(st, mv, gmv))
    State._award = orig_award
    return {
        "level": level,
        "seed": seed,
        "scores": list(st.scores),
        "moves": moves,
        "awards": awards,
        "supply_curve": supply_curve,
        "history": [list(h) for h in st.history],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("level", choices=["strong", "standard", "greedy"])
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    jobs = [(args.level, s) for s in range(args.start, args.start + args.seeds)]
    with out.open("a", encoding="utf-8") as f, ProcessPoolExecutor(args.workers) as ex:
        for i, g in enumerate(ex.map(play, jobs), 1):
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{i}/{len(jobs)} seed={g['seed']} scores={g['scores']}", flush=True)


if __name__ == "__main__":
    main()
