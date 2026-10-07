"""小型の方策・価値ネット（盤面を直接見るCNN）の試作。

データ収集（中断しても、終わった塊は飛ばす。`runs/nn_data_<seed>.npz`）:
    py scripts/nn_train.py collect --games 1000 --chunk 100 --workers 4
学習（PyTorch が必要。重みは numpy 形式で `models/` に書く）:
    py scripts/nn_train.py train --out models/nn_v1.npz
"""

from __future__ import annotations

import argparse
import glob
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne.nn_encode import NC, NG, NPOL, R

V6 = "models/eval_v6_lin.npy"


def collect(args) -> None:
    from carcassonne.nn_selfplay import generate

    Path("runs").mkdir(exist_ok=True)
    kw = {"n_sims": args.sims, "eval_path": args.agent, "rollout_depth": args.depth}
    for i in range(0, args.games, args.chunk):
        seed = args.seed + i // args.chunk
        out = Path(f"runs/nn_data_{seed}.npz")
        if out.exists():
            continue
        t = time.time()
        d = generate(kw, args.chunk, args.workers, seed=seed)
        np.savez_compressed(out, **d)
        print(f"seed={seed}: {len(d['y'])}局面 {time.time() - t:.0f}s", flush=True)


def load(pattern: str):
    parts = [dict(np.load(f)) for f in sorted(glob.glob(pattern))]
    if not parts:
        sys.exit(f"データがありません: {pattern}")
    off = 0
    for p in parts:
        p["game"] = p["game"] + off
        off = int(p["game"].max()) + 1
    d = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    n = NC * R * R
    d["planes"] = np.unpackbits(d["planes"], axis=1)[:, :n].reshape(-1, NC, R, R)
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="自己対戦データを集める")
    c.add_argument("--games", type=int, default=1000)
    c.add_argument("--chunk", type=int, default=100)
    c.add_argument("--workers", type=int, default=1)
    c.add_argument("--sims", type=int, default=2000)
    c.add_argument("--depth", type=int, default=10)
    c.add_argument("--agent", default=V6)
    c.add_argument("--seed", type=int, default=900)
    t = sub.add_parser("train", help="方策・価値ネットを学習する（PyTorch が必要）")
    t.add_argument("--data", default="runs/nn_data_*.npz")
    t.add_argument("--channels", type=int, default=48)
    t.add_argument("--blocks", type=int, default=4)
    t.add_argument("--epochs", type=int, default=12)
    t.add_argument("--batch", type=int, default=256)
    t.add_argument("--lr", type=float, default=2e-3)
    t.add_argument("--value-weight", type=float, default=1.0)
    t.add_argument("--out", default="models/nn_v1.npz")
    args = ap.parse_args()
    if args.cmd == "collect":
        collect(args)
    else:
        from carcassonne.nn_torch import train

        d = load(args.data)
        print(
            f"{len(d['y'])}局面（{int(d['game'].max()) + 1}局）, 入力 {NC}x{R}x{R}+{NG}, 方策 {NPOL}"
        )
        train(d, args)


if __name__ == "__main__":
    main()
