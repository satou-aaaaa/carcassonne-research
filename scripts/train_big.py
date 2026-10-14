"""自己対戦ループが貯めた全データ（数万局）で評価関数を学び直す。

ループ（`selfplay_loop.py`）は直近4試行（約800局）のデータしか使わない。ここでは全試行のデータを
まとめて、TD(λ) の目標で線形（対照）と1隠れ層MLPを学習し、後半の対局で検証R²を比べる。

    python scripts/train_big.py --data /mnt/project-files/carcassonne-runs/loop/data \\
        --champion /mnt/project-files/carcassonne-runs/loop/models/gen151.npy \\
        --out /mnt/project-files/carcassonne-runs/bigdata --hidden 32 64
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carcassonne.fast_eval import NF, fit_mlp, load_eval
from carcassonne.ridge_stats import solve_ridge, stats_of
from carcassonne.selfplay_loop import eval_np
from carcassonne.td import td_lambda_targets


def load_all(data_dir: Path):
    """data/a*.npz を試行・塊の順に読み、対局番号を通しで振り直して返す。"""
    Xs, ys, ps, gs, off = [], [], [], [], 0
    for f in sorted(data_dir.glob("a*.npz")):
        with np.load(f) as d:
            X = d["X"]
            if X.shape[1] < NF:
                X = np.hstack([X, np.zeros((len(X), NF - X.shape[1]))])
            Xs.append(X)
            ys.append(d["y"])
            ps.append(d["p"])
            gs.append(d["g"] - d["g"].min() + off)
        off = int(gs[-1].max()) + 1
    return np.concatenate(Xs), np.concatenate(ys), np.concatenate(ps), np.concatenate(gs)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--champion", required=True, help="TD(λ) の目標に使う評価関数")
    ap.add_argument("--out", required=True)
    ap.add_argument("--lam", type=float, default=0.7)
    ap.add_argument("--hidden", type=int, nargs="*", default=[32])
    ap.add_argument("--epochs", type=int, default=20)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    X, y, p, g = load_all(Path(args.data))
    print(
        f"{len(y)}局面 / {len(np.unique(g))}局 を読み込み（{time.time() - t0:.0f}秒）", flush=True
    )
    champ, mode = load_eval(args.champion)
    target = td_lambda_targets(eval_np(champ, mode, X), y, p, g, args.lam)
    va = g >= np.quantile(g, 0.9)  # 最後の1割の対局を検証に使う
    tr = ~va

    def r2(params, m):
        pred = eval_np(params, m, X[va])
        return float(1 - ((y[va] - pred) ** 2).sum() / ((y[va] - y[va].mean()) ** 2).sum())

    report = {"positions": len(y), "games": len(np.unique(g)), "r2_champion": r2(champ, mode)}
    w = solve_ridge(stats_of(X[tr], target[tr]), 1.0, None)
    np.save(out / "lin_all.npy", w)
    report["r2_lin_all"] = r2(w, 1)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    for h in args.hidden:
        t1 = time.time()
        params, _ = fit_mlp(X[tr], target[tr], hidden=h, epochs=args.epochs, seed=h)
        np.save(out / f"mlp{h}_all.npy", params)
        report[f"r2_mlp{h}_all"] = r2(params, h)
        print(f"mlp{h}: R²={report[f'r2_mlp{h}_all']:.4f}（{time.time() - t1:.0f}秒）", flush=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
