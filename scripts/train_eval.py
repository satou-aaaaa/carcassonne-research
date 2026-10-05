"""方策反復: MCTS自己対戦のデータで線形評価関数を再学習する。

    py scripts/train_eval.py --iters 3 --games 400 --sims 500 --workers 11

反復0はロールアウト版MCTS、反復k>=1は直前の評価関数を使うMCTSでデータを作る。
データは全反復を蓄積し、リッジ回帰で `models/eval_v{k}.npy` を出力する。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carcassonne.fast_eval import FEATURE_NAMES, fit_mlp, fit_ridge
from carcassonne.selfplay import generate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=3)
    ap.add_argument("--games", type=int, default=400)
    ap.add_argument("--sims", type=int, default=500)
    ap.add_argument("--eval-sims", type=int, default=4000, help="評価関数版MCTSの反復数")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--start", type=int, default=1, help="出力する最初のバージョン番号")
    ap.add_argument("--init", default=None, help="反復0の代わりに使う初期重み(.npy)")
    ap.add_argument("--lam", type=float, default=10.0)
    ap.add_argument(
        "--model",
        choices=["linear", "mlp"],
        default="linear",
        help="次反復のデータ生成に使うモデル",
    )
    ap.add_argument("--hidden", type=int, default=32)
    ap.add_argument("--epochs", type=int, default=40)
    args = ap.parse_args()

    Path("models").mkdir(exist_ok=True)
    Path("runs").mkdir(exist_ok=True)
    X_all, y_all = [], []
    prev = args.init
    for k in range(args.start, args.start + args.iters):
        kw = (
            {"n_sims": args.sims} if prev is None else {"n_sims": args.eval_sims, "eval_path": prev}
        )
        t = time.time()
        X, y = generate(kw, args.games, args.workers, seed=k)
        np.savez_compressed(f"runs/data_v{k}.npz", X=X, y=y)
        X_all.append(X)
        y_all.append(y)
        Xa, ya = np.concatenate(X_all), np.concatenate(y_all)
        lin = fit_ridge(Xa, ya, args.lam)
        r2 = 1 - ((ya - Xa @ lin.w) ** 2).sum() / ((ya - ya.mean()) ** 2).sum()
        lin.save(f"models/eval_v{k}_lin.npy")
        print(
            f"v{k}: {len(y)}局面（累計{len(ya)}） 線形R2={r2:.3f} {time.time() - t:.0f}s",
            flush=True,
        )
        print("  " + " ".join(f"{n}={w:.2f}" for n, w in zip(FEATURE_NAMES, lin.w)), flush=True)
        mlp, r2m = fit_mlp(Xa, ya, hidden=args.hidden, epochs=args.epochs)
        np.save(f"models/eval_v{k}_mlp.npy", mlp)
        print(f"v{k}: MLP(H={args.hidden}) 検証R2={r2m:.3f}", flush=True)
        out = f"models/eval_v{k}_{'mlp' if args.model == 'mlp' else 'lin'}.npy"
        prev = out


if __name__ == "__main__":
    main()
