"""棋譜から評価関数の特徴量（36個）と候補の特徴量（`fast_eval_ext`）を計算し、候補を1つずつ足したときの
決定係数の変化を比べる。候補の重み（TD(λ=0.7)、v9 へ正則化したリッジ）も書き出せる。

    py scripts/collect_records.py --out-dir runs/records --games 400
    py scripts/feature_r2.py build --run runs        # runs/records/*.npz -> runs/feat/*.npz
    py scripts/feature_r2.py compare --run runs --ridge 1000
    py scripts/feature_r2.py fit --run runs --out runs/cand   # ctrl / merge / all の重み（47個）

決定係数は後半20%の対局での「終局得点差」に対する値（`train_td.py` と同じ物差し）。
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
from carcassonne.fast import Fast
from carcassonne.fast_eval import NF, load_eval
from carcassonne.fast_eval_ext import EXT_NAMES, NX, features_ext
from carcassonne.records import records_to_data
from carcassonne.td import td_lambda_targets

V9 = str(ROOT / "models/eval_v9_block.npy")


def build(run: Path) -> None:
    fast = Fast()
    for f in sorted(glob.glob(str(run / "records/rec_*.npz"))):
        out = run / "feat" / Path(f).name
        if out.exists():
            continue
        out.parent.mkdir(exist_ok=True)
        d = np.load(f)
        X, y, p, g = records_to_data(fast, d["deck"], d["moves"], d["nmoves"])
        Xe = records_to_data(fast, d["deck"], d["moves"], d["nmoves"], feat=features_ext, nf=NX)[0]
        np.savez_compressed(out, X=X, Xe=Xe, y=y, p=p, g=g)
        print(out.name, len(y), flush=True)


def load(run: Path):
    Xs, ys, ps, gs, off = [], [], [], [], 0
    for f in sorted(glob.glob(str(run / "feat/rec_*.npz"))):
        d = np.load(f)
        Xs.append(np.hstack([d["X"], d["Xe"]]))
        ys.append(d["y"])
        ps.append(d["p"])
        gs.append(d["g"] + off)
        off = int(gs[-1].max()) + 1
    if not Xs:
        sys.exit(f"{run}/feat にデータがありません（先に build）")
    return [np.concatenate(a) for a in (Xs, ys, ps, gs)]


def r2(y, pred) -> float:
    return float(1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def fit_cols(cols, X, y, p, g, ridge):
    """列 cols だけで学習し、(47個に0埋めした重み, 検証R²) を返す。"""
    v9 = load_eval(V9)[0][:NF]
    prior = np.concatenate([v9, np.zeros(NX)])
    tgt = td_lambda_targets(X[:, :NF] @ v9, y, p, g, 0.7)
    cut = np.quantile(g, 0.8)
    tr, va = g < cut, g >= cut
    st = ridge_stats.stats_of(X[tr][:, cols], tgt[tr])
    w = ridge_stats.solve_ridge(st, ridge, prior[cols])
    full = np.zeros(NF + NX)
    full[cols] = w
    return full, r2(y[va], X[va] @ full)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "compare", "fit"])
    ap.add_argument("--run", default="runs")
    ap.add_argument("--ridge", type=float, default=1000.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    run = Path(args.run)
    if args.cmd == "build":
        build(run)
        return
    X, y, p, g = load(run)
    base = list(range(NF))
    print(f"{len(y)}局面 {len(np.unique(g))}局")
    if args.cmd == "compare":
        _, a = fit_cols(base, X, y, p, g, args.ridge)
        print(f"36特徴で学び直し: R2={a:.4f}")
        for j, name in enumerate(EXT_NAMES):
            w, b = fit_cols(base + [NF + j], X, y, p, g, args.ridge)
            print(f"+{name:28s} R2={b:.4f}（{b - a:+.4f}） 重み={w[NF + j]:+.3f}")
        w, b = fit_cols(list(range(NF + NX)), X, y, p, g, args.ridge)
        print(f"+全部 R2={b:.4f}（{b - a:+.4f}）")
        return
    out = Path(args.out or run / "cand")
    out.mkdir(parents=True, exist_ok=True)
    merge = [NF + EXT_NAMES.index("merge_gain_mine"), NF + EXT_NAMES.index("merge_gain_theirs")]
    for name, cols in (("ctrl", base), ("merge", base + merge), ("all", list(range(NF + NX)))):
        w, b = fit_cols(cols, X, y, p, g, args.ridge)
        np.save(out / f"{name}.npy", w)
        print(f"{name}: R2={b:.4f} -> {out / name}.npy")


if __name__ == "__main__":
    main()
