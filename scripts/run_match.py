"""エージェント同士の対戦を実行して集計する。

例:
    py scripts/run_match.py greedy random --seeds 100 --workers 10
    py scripts/run_match.py mcts:sims=400,det=8 greedy --seeds 50 --workers 10 --log runs/m1.jsonl

エージェント指定は `名前[:キー=値,...]`。名前は random / greedy / mcts（Python版）/ fmcts（Numba版）。
同じシードで先後を入れ替えた2局を1組として集計する（山札の運の差を打ち消す）。
"""

from __future__ import annotations

import argparse
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carcassonne.agents import GreedyAgent, RandomAgent
from carcassonne.arena import run_match
from carcassonne.fast_mcts import FastMCTSAgent
from carcassonne.mcts import MCTSAgent

FACTORIES = {
    "random": RandomAgent,
    "greedy": GreedyAgent,
    "mcts": MCTSAgent,
    "fmcts": FastMCTSAgent,
}
INT_KEYS = {"sims": "n_sims", "det": "n_det", "depth": "rollout_depth"}
BOOL_KEYS = {"fact": "factored", "chance": "chance"}
FLOAT_KEYS = {
    "c": "c",
    "scale": "reward_scale",
    "meeple_cost": "meeple_cost",
    "mp": "meeple_prob",
}


def parse_agent(spec: str):
    name, _, rest = spec.partition(":")
    if name not in FACTORIES:
        raise SystemExit(f"未知のエージェント: {name}（{', '.join(FACTORIES)}）")
    kwargs = {}
    for item in filter(None, rest.split(",")):
        key, _, value = item.partition("=")
        if key in INT_KEYS:
            kwargs[INT_KEYS[key]] = int(value)
        elif key == "eval":
            kwargs["eval_path"] = value
        elif key in BOOL_KEYS:
            kwargs[BOOL_KEYS[key]] = value not in ("0", "false", "False")
        elif key in FLOAT_KEYS:
            kwargs[FLOAT_KEYS[key]] = float(value)
        else:
            raise SystemExit(f"未知のパラメータ: {key}")
    return partial(FACTORIES[name], **kwargs)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--seeds", type=int, default=20, help="シード数（先後入替で2倍の局数）")
    ap.add_argument("--start", type=int, default=0, help="先頭シード")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--log", default=None, help="JSONLの出力先")
    args = ap.parse_args()
    seeds = range(args.start, args.start + args.seeds)
    summary = run_match(parse_agent(args.a), parse_agent(args.b), seeds, args.log, args.workers)
    print(f"A={args.a}  B={args.b}\n{summary}")


if __name__ == "__main__":
    main()
