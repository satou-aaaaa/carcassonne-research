"""データページ（docs/stats.html）用に、最新チャンピオン同士の対局を1手ずつ記録する。

    py scripts/collect_game_stats.py --decks 1000 --plays 2 --workers 4 --out runs/stats/selfplay.jsonl

同じ山札（シード）を、指し手の乱数だけ変えて --plays 回ずつ指す。同じ山札の対局どうしが
どれだけ似た結果になるかで「山札の運」の大きさを測る（scripts/summarize_game_stats.py）。
AIは対戦ページの「標準」と同じ設定（2000回探索＋最新チャンピオンの評価関数）。
1局を1行のJSONで書く。集計は scripts/summarize_game_stats.py。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carcassonne.state import State


def make_agent():
    from carcassonne.webplay import make_agent

    return make_agent("standard")


_AGENT = None


def play(job: tuple[int, int]) -> dict:
    """山札 seed を play 番目の乱数で1局指し、記録を返す。"""
    global _AGENT
    seed, k = job
    if _AGENT is None:
        _AGENT = make_agent()
    agent = _AGENT
    st = State.new_game(seed)
    rngs = [random.Random((seed * 16 + k) * 2 + i) for i in (0, 1)]
    awards = []
    orig = State._award

    def award(self, root, points):
        m = self.meeples[root]
        top = max(m)
        if self is st and top > 0:  # 探索中の複製は数えない
            awards.append(
                [
                    [p for p in (0, 1) if m[p] == top],
                    self.kind[root],
                    points,
                    int(self.over),
                    len(self.history),
                ]
            )
        orig(self, root, points)

    State._award = award
    moves = []
    try:
        while not st.over:
            p = st.player
            legal = len(st.legal_moves())
            places = len(st.placements())
            kinds = sum(1 for c in st.remaining_counts() if c > 0)
            ti = st.current
            supply = list(st.supply)
            mv = agent.act(st, rngs[p])
            before = st.projected_scores()
            piece_kind = None
            if mv.piece is not None:
                piece_kind = st.ts.types[ti].variants[mv.variant].pieces[mv.piece].kind
            st.apply(mv)
            after = st.projected_scores()
            moves.append(
                {
                    "p": p,
                    "t": st.ts.types[ti].id,
                    "legal": legal,
                    "places": places,
                    "kinds": kinds,
                    "sup": supply,
                    "m": piece_kind,
                    "sc": list(st.scores),
                    "proj": after,
                    "gain": [after[0] - before[0], after[1] - before[1]],
                }
            )
    finally:
        State._award = orig
    return {
        "seed": seed,
        "play": k,
        "scores": list(st.scores),
        "discarded": len(st.discarded),
        "awards": awards,
        "moves": moves,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--decks", type=int, default=100)
    ap.add_argument("--plays", type=int, default=2)
    ap.add_argument("--start", type=int, default=200000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():  # 途中から再開できるようにする
        for line in out.read_text(encoding="utf-8").splitlines():
            g = json.loads(line)
            done.add((g["seed"], g["play"]))
    jobs = [
        (s, k)
        for s in range(args.start, args.start + args.decks)
        for k in range(args.plays)
        if (s, k) not in done
    ]
    with out.open("a", encoding="utf-8") as f, ProcessPoolExecutor(args.workers) as ex:
        for i, g in enumerate(ex.map(play, jobs, chunksize=2), 1):
            f.write(json.dumps(g, separators=(",", ":")) + "\n")
            f.flush()
            if i % 20 == 0:
                print(f"{i}/{len(jobs)}", flush=True)


if __name__ == "__main__":
    main()
