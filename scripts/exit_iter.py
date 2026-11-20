"""探索の値を教師に評価関数を学ぶ（Expert Iteration、BACKLOG R-013）。

今の自己対戦ループは「終局の得点差から作る TD(λ) の目標」で線形評価を学ぶ。ここでは、各局面で探索（評価＋2000回の
MCTS）が出した根の値（いちばん多く試した手の平均報酬を予想得点差に戻したもの）を教師にする。先生（評価＋探索）は
生徒（評価だけ）より強いので、生徒が先生に近づくと探索の土台が上がり、次はその評価で探索した値を教師にする（反復）。

  gen: 評価 E の探索で自己対戦し、局面の特徴量・終局得点差・手番・対局番号・根の値を保存する
  fit: 保存したデータから、目標（td / root / mix）を選んで線形評価を学ぶ（今のループと同じくチャンピオンへ正則化）

例:
  python scripts/exit_iter.py gen --eval models/eval_champion.npy --games 400 --seed 1 --out runs/x/d1.npz
  python scripts/exit_iter.py fit --data runs/x/d1.npz --prior models/eval_champion.npy --target root --out runs/x/w.npy
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carcassonne.fast import (
    SC_OVER,
    SC_PL,
    SC_S0,
    SC_S1,
    apply_move,
    random_move,
    seed_rng,
)
from carcassonne.fast_eval import NF, features, load_eval
from carcassonne.fast_mcts import FastMCTSAgent, search_stats
from carcassonne.ridge_stats import solve_ridge, stats_of
from carcassonne.selfplay_loop import eval_np
from carcassonne.td import td_lambda_targets


def root_search(agent: FastMCTSAgent, S, depth: int):
    """探索して (マス, 向き, 断片, 根の値) を返す。根の値は手番側視点の予想得点差。"""
    sc = agent.fast.scratch
    scale = agent.scale_for(S)
    cell, g, n1, w1, n2, _ = search_stats(
        S, agent.fast.T, agent.fast.P, agent.n_sims, agent.n_det, agent.c, scale,
        agent.meeple_prob, depth, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, sc.free, sc.rec,
        agent.eval_w, agent.eval_mode, agent.fbuf, agent.late, agent.fpu, agent.prior_visits,
        agent.root_allow(S), 0, True, 0, 0.0, 1, 3.0,
    )  # fmt: skip
    top = n1.max()
    cands = np.where(n1 == top)[0]
    bk = cands[random.randrange(len(cands))]
    bp = int(np.argmax(n2[bk])) - 1
    r = float(w1[bk] / max(n1[bk], 1))
    v = scale * math.atanh(min(max(2 * r - 1, -0.999), 0.999))
    return int(cell[bk]), int(g[bk]), bp, v


def _play(args):
    eval_path, sims, depth, n_games, seed, eps = args
    agent = FastMCTSAgent(sims, eval_path=eval_path, rollout_depth=depth)
    fast = agent.fast
    sc = fast.scratch
    ts = fast.ts
    rng = random.Random(seed)
    random.seed(seed)
    seed_rng(seed)
    base = [i for i, t in enumerate(ts.types) for _ in range(t.count)]
    base.remove(ts.start)
    f = np.zeros(NF)
    xs, ys, ps, gs, vs = [], [], [], [], []
    for gi in range(n_games):
        deck = base[:]
        rng.shuffle(deck)
        S = fast.new_game(deck)
        players = []
        while not S[10][SC_OVER]:
            me = int(S[10][SC_PL])
            features(S, fast.T, fast.P, me, f)
            xs.append(f.copy())
            players.append(me)
            cell, g, piece, v = root_search(agent, S, depth)
            vs.append(v)
            if rng.random() < eps:
                cell, g, piece = random_move(
                    S, fast.T, fast.P, 0.3, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, sc.free
                )
            apply_move(
                S, fast.T, fast.P, cell, g, piece, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g
            )
        d = int(S[10][SC_S0]) - int(S[10][SC_S1])
        ys.extend(d if me == 0 else -d for me in players)
        ps.extend(players)
        gs.extend([gi + seed * 10_000] * len(players))
    return np.array(xs), np.array(ys, float), np.array(ps), np.array(gs), np.array(vs)


def gen(a) -> None:
    per = [a.games // a.workers + (1 if i < a.games % a.workers else 0) for i in range(a.workers)]
    jobs = [(a.eval, a.sims, a.depth, n, a.seed * 100 + i, a.eps) for i, n in enumerate(per) if n]
    with ProcessPoolExecutor(a.workers) as ex:
        parts = list(ex.map(_play, jobs))
    X, y, p, g, v = (np.concatenate([q[i] for q in parts]) for i in range(5))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(a.out, X=X, y=y, p=p, g=g, v=v)
    print(f"{a.out}: {len(y)}局面 根の値と終局の相関 {np.corrcoef(v, y)[0, 1]:.3f}")


def targets(X, y, p, g, v, champ, mode, kind: str, lam: float, mix: float):
    if kind == "root":
        return v
    td = td_lambda_targets(eval_np(champ, mode, X), y, p, g, lam)
    if kind == "td":
        return td
    return (1 - mix) * v + mix * td


def fit(a) -> None:
    ds = [np.load(f) for f in a.data]
    X, y, p, g, v = (np.concatenate([d[k] for d in ds]) for k in ("X", "y", "p", "g", "v"))
    champ, mode = load_eval(a.prior)
    t = targets(X, y, p, g, v, champ, mode, a.target, a.lam, a.mix)
    w = solve_ridge(stats_of(X, t), a.ridge, champ if mode == 1 else None)
    np.save(a.out, w)
    va = g >= np.quantile(g, 0.8)

    def r2(pred, tgt):
        return 1 - ((tgt[va] - pred) ** 2).sum() / ((tgt[va] - tgt[va].mean()) ** 2).sum()

    pc, pw = eval_np(champ, mode, X[va]), eval_np(w, 1, X[va])
    print(
        f"{a.out}: 目標={a.target} {len(y)}局面 終局R² 生徒{r2(pw, y):.3f}/先生の評価{r2(pc, y):.3f}"
        f" 根の値R² 生徒{r2(pw, v):.3f}/先生の評価{r2(pc, v):.3f} 重みの変化 {np.abs(w - champ).sum():.3f}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("gen")
    s.add_argument("--eval", required=True)
    s.add_argument("--games", type=int, default=400)
    s.add_argument("--sims", type=int, default=2000)
    s.add_argument("--depth", type=int, default=10)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--eps", type=float, default=0.05)
    s.add_argument("--workers", type=int, default=4)
    s.add_argument("--out", required=True)
    s = sub.add_parser("fit")
    s.add_argument("--data", nargs="+", required=True)
    s.add_argument("--prior", required=True)
    s.add_argument("--target", choices=["td", "root", "mix"], default="root")
    s.add_argument("--lam", type=float, default=0.7)
    s.add_argument("--mix", type=float, default=0.5, help="mix: TD(λ) の割合")
    s.add_argument("--ridge", type=float, default=1000.0)
    s.add_argument("--out", required=True)
    a = ap.parse_args()
    {"gen": gen, "fit": fit}[a.cmd](a)


if __name__ == "__main__":
    main()
