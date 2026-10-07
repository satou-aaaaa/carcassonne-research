"""TD(λ) の目標と前世代の重みへの正則化で、線形評価関数を学び直す。

新しい自己対戦データだけを終局得点差で学び直すと弱くなった（docs/EXPERIMENTS.md の v7）。
その対策として、次の2つを組み合わせる。

- 目標: 終局得点差の代わりに TD(λ) の目標（`carcassonne.td`）。次の局面の評価には `--value` の重みを使う。
- 正則化: 0 ではなく前世代の重み（`--prior`）に向かって縮める。過去の蓄積統計（`--past-stats`）も足せる。

データ収集（中断しても、終わった塊は飛ばす。`runs/td_data_<seed>.npz`）:
    py scripts/train_td.py collect --games 600 --chunk 100 --workers 4
学習（候補を models/ に書く）:
    py scripts/train_td.py fit --lam 0.7 --ridge 1000 --out models/eval_v8_lin.npy
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne import ridge_stats
from carcassonne.fast_eval import NF_V6, load_eval
from carcassonne.td import td_lambda_targets

V6 = "models/eval_v6_lin.npy"


def collect(args) -> None:
    from carcassonne.selfplay import generate

    Path("runs").mkdir(exist_ok=True)
    kw = {"n_sims": args.sims, "eval_path": args.agent}
    if args.depth:
        kw["rollout_depth"] = args.depth
    for i in range(0, args.games, args.chunk):
        seed = args.seed + i // args.chunk
        out = Path(f"runs/td_data_{seed}.npz")
        if out.exists():
            continue
        X, y, p, g = generate(kw, args.chunk, args.workers, seed=seed, with_meta=True)
        np.savez_compressed(out, X=X, y=y, p=p, g=g)
        print(f"seed={seed}: {len(y)}局面", flush=True)


def load_data(pattern: str, nf: int):
    Xs, ys, ps, gs, off = [], [], [], [], 0
    for f in sorted(glob.glob(pattern)):
        with np.load(f) as d:
            Xs.append(d["X"][:, :nf])
            ys.append(d["y"])
            ps.append(d["p"])
            gs.append(d["g"] + off)
            off = int(gs[-1].max()) + 1
    if not Xs:
        sys.exit(f"データがありません: {pattern}")
    return np.concatenate(Xs), np.concatenate(ys), np.concatenate(ps), np.concatenate(gs)


def r2(X, y, w) -> float:
    return float(1 - ((y - X @ w) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def fit(args) -> None:
    nf = args.nf
    X, y, p, g = load_data(args.data, nf)
    value_w = load_eval(args.value)[0][:nf]
    target = td_lambda_targets(X @ value_w, y, p, g, args.lam)
    # 後半20%の対局を検証に使い、終局得点差に対する決定係数を見る（目標の作り方に依らない物差し）
    cut = np.quantile(g, 0.8)
    tr, va = g < cut, g >= cut
    prior = load_eval(args.prior)[0][:nf] if args.prior else None
    stats = ridge_stats.stats_of(X[tr], target[tr])
    if args.past_stats:
        past = ridge_stats.load(args.past_stats, nf)
        if past is None:
            sys.exit(f"{args.past_stats} は特徴量数 {nf} の統計ではありません")
        stats = ridge_stats.merge(past, stats, args.past_weight)
    w = ridge_stats.solve_ridge(stats, args.ridge, prior)
    print(
        f"{len(y)}局面 λ={args.lam} ridge={args.ridge} prior={args.prior} past={args.past_stats}\n"
        f"  検証R2（終局得点差）: 新={r2(X[va], y[va], w):.3f} "
        f"v6={r2(X[va], y[va], load_eval(V6)[0][:nf]):.3f}",
        flush=True,
    )
    if args.out:
        np.save(args.out, w)
        print(f"  -> {args.out}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="自己対戦データを集める")
    c.add_argument("--games", type=int, default=600)
    c.add_argument("--chunk", type=int, default=100)
    c.add_argument("--workers", type=int, default=1)
    c.add_argument("--sims", type=int, default=2000)
    c.add_argument("--depth", type=int, default=0, help="評価前のランダム手数（0=なし）")
    c.add_argument("--agent", default=V6, help="データを作るMCTSの評価関数")
    c.add_argument("--seed", type=int, default=800)
    f = sub.add_parser("fit", help="TD(λ)の目標で学習する")
    f.add_argument("--data", default="runs/td_data_*.npz")
    f.add_argument("--nf", type=int, default=NF_V6, help="使う特徴量の数")
    f.add_argument("--lam", type=float, default=0.7, help="TD(λ)のλ（1=終局得点差）")
    f.add_argument("--value", default=V6, help="次の局面の評価に使う重み")
    f.add_argument("--ridge", type=float, default=10.0)
    f.add_argument("--prior", default=None, help="この重みに向かって正則化する")
    f.add_argument("--past-stats", default=None, help="足し合わせる過去の統計（ridge_stats.npz）")
    f.add_argument("--past-weight", type=float, default=1.0, help="過去の統計に掛ける重み")
    f.add_argument("--out", default=None)
    args = ap.parse_args()
    collect(args) if args.cmd == "collect" else fit(args)


if __name__ == "__main__":
    main()
