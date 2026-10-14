"""先手有利の検定: 同じエージェント同士で N 局指し、先手の勝率と得点差を集計する。

    py scripts/first_player.py fmcts:sims=2000 --games 400 --workers 4 --log docs/results/first_player.jsonl
    py scripts/first_player.py random --games 4000 --workers 4

先手の勝率は引き分けを0.5勝として、Wilson区間と両側の二項検定（p=0.5）で評価する。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_match import parse_agent

from carcassonne.arena import GameResult, play_game, wilson


def _job(job: tuple) -> GameResult:
    seed, make = job
    return play_game(seed, make(), make())


def binom_two_sided(k: int, n: int) -> float:
    """p=0.5 の両側二項検定（正確）。"""
    if n == 0:
        return 1.0
    pk = [math.comb(n, i) / 2**n for i in range(n + 1)]
    return min(1.0, sum(p for p in pk if p <= pk[k] * (1 + 1e-12)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("agent")
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--log", default=None)
    args = ap.parse_args()
    make = parse_agent(args.agent)
    jobs = [(s, make) for s in range(args.start, args.start + args.games)]
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            res = list(ex.map(_job, jobs, chunksize=1))
    else:
        res = [_job(j) for j in jobs]
    if args.log:
        path = Path(args.log)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for r in res:
                f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    w0 = sum(r.diff > 0 for r in res)
    w1 = sum(r.diff < 0 for r in res)
    draws = len(res) - w0 - w1
    n = len(res)
    lo, hi = wilson(w0 + 0.5 * draws, n)
    diffs = [r.diff for r in res]
    mean = sum(diffs) / n
    se = math.sqrt(sum((d - mean) ** 2 for d in diffs) / max(n - 1, 1) / n)
    p = binom_two_sided(w0, w0 + w1)
    print(
        f"{args.agent}: {n}局 先手勝{w0}/後手勝{w1}/引分{draws} 先手勝率(引分0.5) "
        f"{(w0 + 0.5 * draws) / n:.3f} [{lo:.3f}, {hi:.3f}] 平均得点差(先手-後手) {mean:+.2f}±{se:.2f} "
        f"二項検定p={p:.4f}"
    )


if __name__ == "__main__":
    main()
