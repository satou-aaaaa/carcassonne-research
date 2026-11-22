"""評価関数の重みを、対局の結果で直接合わせる（SPSA、Spall 1998）。

各反復で全部の重みを同時に ±c（重みごとの尺度 s 倍）だけずらした2つの版 w+ と w- を、同じ山札・先後入れ替えで
対戦させ、w+ の平均得点差 y から勾配を y / (2c·Δ) と見積もって重みを動かす。学習（予測の当たり具合）ではなく
強さそのものを目的にする。最後に後半の反復の重みを平均した版（Polyak 平均）を書き出す。

    python scripts/spsa.py --out runs/spsa --minutes 300 --pairs 16

出典: J. C. Spall, "Implementation of the simultaneous perturbation algorithm for stochastic optimization",
IEEE Trans. AES 34(3), 1998（a_k = a/(k+1+A)^0.602, c_k = c/(k+1)^0.101）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne.arena import play_game
from carcassonne.fast_mcts import FastMCTSAgent


def make_agent(w, sims: int, name: str) -> FastMCTSAgent:
    a = FastMCTSAgent(n_sims=sims, eval_path=str(ROOT / "models" / "eval_champion.npy"))
    a.eval_w = np.asarray(w, np.float64)
    a.name = name
    return a


def _game(job):
    seed, w0, w1, sims, plus_first = job
    r = play_game(seed, make_agent(w0, sims, "p0"), make_agent(w1, sims, "p1"))
    d = r.diff
    return d if plus_first else -d  # w+ 視点の得点差


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", default="runs/spsa")
    ap.add_argument("--minutes", type=float, default=300)
    ap.add_argument(
        "--pairs", type=int, default=16, help="1反復の山札の数（先後入れ替えで2倍の局数）"
    )
    ap.add_argument("--sims", type=int, default=800)
    ap.add_argument("--a", type=float, default=0.0003)
    ap.add_argument("--c", type=float, default=0.15)
    ap.add_argument("--floor", type=float, default=0.2, help="重みの尺度 s の下限")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--max-iters", type=int, default=100000)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    w0 = np.load(ROOT / "models" / "eval_champion.npy").astype(np.float64)
    s = np.maximum(np.abs(w0), args.floor)
    u = w0 / s
    rng = np.random.default_rng(args.seed)
    A = 50
    t_end = time.time() + args.minutes * 60
    hist = []
    workers = args.workers or None
    with ProcessPoolExecutor(max_workers=workers) as ex, open(out / "log.jsonl", "a") as log:
        k = 0
        while time.time() < t_end and k < args.max_iters:
            ck = args.c / (k + 1) ** 0.101
            ak = args.a * (A + 1) ** 0.602 / (k + 1 + A) ** 0.602
            delta = rng.choice([-1.0, 1.0], size=len(u))
            wp, wm = (u + ck * delta) * s, (u - ck * delta) * s
            base = 200000 + args.seed * 1000000 + k * args.pairs
            jobs = [(base + i, wp, wm, args.sims, True) for i in range(args.pairs)]
            jobs += [(base + i, wm, wp, args.sims, False) for i in range(args.pairs)]
            ys = list(ex.map(_game, jobs))
            y = float(np.mean(ys))
            u = u + ak * y / (2 * ck * delta)
            hist.append(u * s)
            log.write(json.dumps({"k": k, "y": y, "ak": ak, "ck": ck,
                                  "dist": float(np.linalg.norm(u - w0 / s))}) + "\n")  # fmt: skip
            log.flush()
            if k % 20 == 0:
                np.save(out / "spsa_last.npy", u * s)
                print(
                    f"反復{k} y={y:+.2f} 元からの距離={np.linalg.norm(u - w0 / s):.3f}", flush=True
                )
            k += 1
    final = np.mean(hist[len(hist) // 2 :], axis=0) if hist else w0
    np.save(out / "spsa_last.npy", u * s)
    np.save(out / "spsa_avg.npy", final)
    (out / "summary.json").write_text(json.dumps({
        "iters": k, "pairs": args.pairs, "sims": args.sims, "a": args.a, "c": args.c,
        "w0": w0.tolist(), "avg": final.tolist(),
        "rel_change": ((final - w0) / s).tolist(),
    }, ensure_ascii=False, indent=1))  # fmt: skip
    print(f"{k}反復。後半平均を {out / 'spsa_avg.npy'} に書きました")


if __name__ == "__main__":
    main()
