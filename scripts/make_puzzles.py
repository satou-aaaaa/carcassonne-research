"""AIの自己対戦から「この局面ならどこに置く？」の練習問題の候補を集める。

1. 最強設定のAI同士で自己対戦し、各手番で根の候補手の評価を取り出す。
2. 最善手と、AIもよく検討した劣る手の差（予想最終点差）が大きい局面を候補にする。
3. 候補局面を5倍の探索量（4決定化）で再解析し、差が残るものだけを出力する。

例:
    py scripts/make_puzzles.py --seeds 0-11 --workers 4 --out runs/puzzles/cands.jsonl

出力は1局面1行のJSONL（局面スナップショット、選択肢と各手のAI評価・事実）。
問題の採否と解説は人が選んで data/puzzles.json に書き、scripts/build_puzzles.py で
ページ用データ web/puzzles.json を作る。
"""

from __future__ import annotations

import argparse
import json
import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carcassonne.fast_mcts import FastMCTSAgent
from carcassonne.puzzles import analyze, move_facts, pick_options, snapshot, track_meeples
from carcassonne.state import State
from carcassonne.webplay import best_eval_path


def parse_seeds(s: str) -> list[int]:
    if "-" in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in s.split(",")]


def gap_of(opts) -> tuple[float, float]:
    """(最善手と2番目の選択肢の点差, 最善手の訪問割合)。"""
    total = sum(o.visits for o in opts)
    ch = pick_options(opts)
    if len(ch) < 3:
        return 0.0, 0.0
    return ch[0].diff - ch[1].diff, ch[0].visits / total


def run_seed(seed: int, args) -> list[dict]:
    # 対局画面の「最強」と同じく、評価前に10手のロールアウトを挟む（webplay.make_agent）
    play = FastMCTSAgent(n_sims=args.sims, rollout_depth=10, eval_path=best_eval_path())
    deep = FastMCTSAgent(
        n_sims=args.sims * 5, n_det=4, rollout_depth=10, eval_path=best_eval_path()
    )
    st = State.new_game(seed)
    meeples: list[dict] = []
    out: list[dict] = []
    while not st.over:
        turn = len(st.history) + 1
        opts = analyze(play, st, seed * 1000 + turn)
        gap, _ = gap_of(opts)
        n_cells = len({(m.x, m.y) for m in st.legal_moves()})
        if args.min_turn <= turn <= args.max_turn and n_cells >= 3 and gap >= args.gap:
            dopts = analyze(deep, st, seed * 1000 + turn + 500)
            dgap, dshare = gap_of(dopts)
            if dgap >= args.gap and dshare >= args.share:
                total = sum(o.visits for o in dopts)
                out.append(
                    {
                        "id": f"s{seed}t{turn}",
                        "seed": seed,
                        "gap": round(dgap, 2),
                        "share": round(dshare, 3),
                        "history": [list(h) for h in st.history],
                        **snapshot(st, meeples),
                        "options": [
                            {
                                "move": list(o.move),
                                "visits": round(o.visits / total, 4),
                                "diff": round(o.diff, 2),
                                "facts": move_facts(st, o.move),
                            }
                            for o in pick_options(dopts)
                        ],
                    }
                )
                print(f"seed {seed} turn {turn}: gap {dgap:.1f}", flush=True)
        mv = opts[0].move if opts else st.legal_moves()[0]  # 訪問数最大の手を指す
        player = st.player
        st.apply(mv)
        meeples = track_meeples(st, meeples, mv, player)
    print(f"seed {seed} done: {len(out)} candidates", flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="0-3")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--sims", type=int, default=12000)
    ap.add_argument("--gap", type=float, default=2.5, help="最善手と次点の予想点差の下限")
    ap.add_argument("--share", type=float, default=0.25, help="最善手の訪問割合の下限")
    ap.add_argument("--min-turn", type=int, default=3)
    ap.add_argument("--max-turn", type=int, default=66)
    ap.add_argument("--out", default="runs/puzzles/cands.jsonl")
    args = ap.parse_args()
    seeds = parse_seeds(args.seeds)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with Pool(args.workers) as pool, path.open("a", encoding="utf-8") as f:
        for recs in pool.imap_unordered(_run, [(s, args) for s in seeds]):
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()


def _run(a):
    return run_seed(*a)


if __name__ == "__main__":
    main()
