"""評価関数を「depth 手のランダムロールアウトの先で使われる」前提で学習する（`carcassonne.rollout_fit`）。

1) 棋譜からロールアウト先の平均特徴量を作る（塊ごとにキャッシュ。中断しても終わった塊は飛ばす）:
    py scripts/train_rollout_eval.py build --records "runs/records/rec_*.npz" --out-dir runs/leaf
2) 学習して候補を書く。検証は後半2割の対局で、探索が葉で見る値（ロールアウト先の評価値の平均）の
   終局得点差に対する決定係数（葉R²）を、今の評価関数と比べる:
    py scripts/train_rollout_eval.py fit --data "runs/leaf/leaf_*.npz" --out models/eval_v10_roll.npy
"""

from __future__ import annotations

import argparse
import glob
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne import ridge_stats
from carcassonne.fast_eval import FEATURE_NAMES, NF, load_eval
from carcassonne.td import td_lambda_targets

V9 = "models/eval_v9_block.npy"


def _build_one(job):
    src, dst, k, depth, seed = job
    from carcassonne.rollout_fit import records_to_leaf_data

    with np.load(src) as d:
        out = records_to_leaf_data(d["deck"], d["moves"], d["nmoves"], k=k, depth=depth, seed=seed)
    names = ("X", "L", "Lo", "fin", "y", "p", "g")
    tmp = Path(str(dst) + ".tmp.npz")
    np.savez_compressed(tmp, **dict(zip(names, out, strict=True)))
    tmp.rename(dst)
    return f"{dst.name}: {len(out[4])}局面"


def build(args) -> None:
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    jobs = []
    for i, src in enumerate(sorted(glob.glob(args.records))):
        dst = out / ("leaf_" + Path(src).stem.split("_")[-1] + ".npz")
        if not dst.exists():
            jobs.append((src, dst, args.k, args.depth, args.seed + i))
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for msg in ex.map(_build_one, jobs):
            print(msg, flush=True)


def load(pattern: str):
    parts = {k: [] for k in ("X", "L", "Lo", "fin", "y", "p", "g")}
    off = 0
    for f in sorted(glob.glob(pattern)):
        with np.load(f) as d:
            for k, v in parts.items():
                v.append(d[k] + (off if k == "g" else 0))
            off = int(parts["g"][-1].max()) + 1
    if not parts["X"]:
        sys.exit(f"データがありません: {pattern}")
    return {k: np.concatenate(v) for k, v in parts.items()}


def r2(pred, y) -> float:
    return float(1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def fit(args) -> None:
    D = load(args.data)
    X, L, Lo, fin, y, p, g = (D[k] for k in ("X", "L", "Lo", "fin", "y", "p", "g"))
    v9 = load_eval(V9)[0]
    value_w = load_eval(args.value)[0]
    target = td_lambda_targets(X @ value_w, y, p, g, args.lam)
    cut = np.quantile(g, 0.8)
    tr, va = g < cut, g >= cut
    # 手番側視点の行と相手視点の行（目標と終局分の符号を反転）を並べる
    A = np.vstack([L[tr], Lo[tr]])
    b = np.concatenate([target[tr] - fin[tr], -(target[tr] - fin[tr])])
    prior = load_eval(args.prior)[0] if args.prior else None
    w = ridge_stats.solve_ridge(ridge_stats.stats_of(A, b), args.ridge, prior)
    print(
        f"{len(y)}局面（学習 {tr.sum()}、検証 {va.sum()}） λ={args.lam} ridge={args.ridge} prior={args.prior}"
    )
    print("  葉R²（ロールアウト先の評価の平均 vs 終局得点差、検証）:")
    for name, ww in (("新", w), ("v9", v9)):
        print(
            f"    {name}: 手番側 {r2(fin[va] + L[va] @ ww, y[va]):.4f}"
            f" 相手視点 {r2(fin[va] - Lo[va] @ ww, y[va]):.4f}"
            f" 実局面にそのまま {r2(X[va] @ ww, y[va]):.4f}"
        )
    if args.show:
        for i in range(NF):
            print(f"    {FEATURE_NAMES[i]:>24} v9={v9[i]:+8.3f} 新={w[i]:+8.3f}")
    if args.out:
        np.save(args.out, w)
        print(f"  -> {args.out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="棋譜からロールアウト先の特徴量を作る")
    b.add_argument("--records", default="runs/records/rec_*.npz")
    b.add_argument("--out-dir", default="runs/leaf")
    b.add_argument("--k", type=int, default=4, help="1局面あたりのロールアウト本数")
    b.add_argument("--depth", type=int, default=10)
    b.add_argument("--workers", type=int, default=4)
    b.add_argument("--seed", type=int, default=0)
    f = sub.add_parser("fit", help="学習して葉R²を比べる")
    f.add_argument("--data", default="runs/leaf/leaf_*.npz")
    f.add_argument("--lam", type=float, default=0.7)
    f.add_argument("--value", default=V9, help="TD(λ)で次の局面の評価に使う重み")
    f.add_argument("--ridge", type=float, default=100.0)
    f.add_argument("--prior", default=None, help="この重みに向かって正則化する")
    f.add_argument("--show", action="store_true", help="重みを並べて表示する")
    f.add_argument("--out", default=None)
    args = ap.parse_args()
    build(args) if args.cmd == "build" else fit(args)


if __name__ == "__main__":
    main()
