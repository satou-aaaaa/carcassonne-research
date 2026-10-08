"""自己対戦の棋譜を塊ごとに集める（中断しても、終わった塊は飛ばす）。

py scripts/collect_records.py --out-dir runs/records --games 800 --chunk 50 --workers 4
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne.records import play_records


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="runs/records")
    ap.add_argument("--games", type=int, default=800)
    ap.add_argument("--chunk", type=int, default=50)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--sims", type=int, default=2000)
    ap.add_argument("--depth", type=int, default=10)
    ap.add_argument("--agent", default="models/eval_v9_block.npy")
    ap.add_argument("--seed", type=int, default=1000)
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    kw = {"n_sims": args.sims, "eval_path": args.agent, "rollout_depth": args.depth}
    for i in range(0, args.games, args.chunk):
        seed = args.seed + i // args.chunk
        path = out / f"rec_{seed}.npz"
        if path.exists():
            continue
        t0 = time.time()
        decks, moves, nmoves = play_records(kw, args.chunk, args.workers, seed=seed)
        tmp = path.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, deck=decks, moves=moves, nmoves=nmoves)
        tmp.rename(path)
        print(f"seed={seed}: {len(nmoves)}局 {time.time() - t0:.0f}秒", flush=True)


if __name__ == "__main__":
    main()
