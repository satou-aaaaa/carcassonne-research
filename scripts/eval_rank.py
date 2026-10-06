"""評価関数の「手の順位付け」性能を測る（R²とは別の指標）。

ランダム〜貪欲の対局から局面を抽出し、各局面の全合法手について
  - 評価関数の値: 手を指した後の局面を、指した側の視点で評価
  - 基準値: 手の後からのランダムロールアウトK回の終局得点差の平均（指した側の視点）
を求め、局面ごとの Spearman 順位相関と、評価関数が選んだ手の基準値の後悔（基準値の最大との差）を平均する。

    py scripts/eval_rank.py models/eval_v6_lin.npy models/eval_v5_mlp.npy --positions 40 --rollouts 30
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carcassonne import State
from carcassonne.agents import GreedyAgent
from carcassonne.fast import SC_PL, copy_state, seed_rng
from carcassonne.fast_eval import NF, eval_value, features, load_eval
from carcassonne.fast_mcts import FastMCTSAgent


def ranks(a: np.ndarray) -> np.ndarray:
    order = a.argsort(kind="stable")
    r = np.empty(len(a))
    r[order] = np.arange(len(a))
    for v in np.unique(a):  # 同値は平均順位
        m = a == v
        r[m] = r[m].mean()
    return r


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra, rb = ranks(a), ranks(b)
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def sample_positions(n: int, seed: int) -> list[State]:
    rng = random.Random(seed)
    greedy = GreedyAgent()
    out = []
    while len(out) < n:
        st = State.new_game(rng.randrange(10**9))
        target = rng.randrange(4, 60)
        for _ in range(target):
            if st.over:
                break
            st.apply(greedy.act(st, rng) if rng.random() < 0.5 else st.random_move(rng))
        if not st.over and len(st.legal_moves()) >= 4:
            out.append(st)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("models", nargs="+")
    ap.add_argument("--positions", type=int, default=40)
    ap.add_argument("--rollouts", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    agent = FastMCTSAgent(n_sims=1)
    fast = agent.fast
    evals = [load_eval(m) for m in args.models]
    fbuf = np.zeros(NF)
    seed_rng(args.seed)
    rho = [[] for _ in evals]
    regret = [[] for _ in evals]
    for st in sample_positions(args.positions, args.seed):
        base = agent.to_fast(st)
        me = int(base[10][SC_PL])
        truth, vals = [], [[] for _ in evals]
        for m in st.legal_moves():
            S = copy_state(base)
            ti = st.current
            fast.apply(S, m.x, m.y, ti, m.variant, m.piece)
            for k, (w, mode) in enumerate(evals):
                features(S, fast.T, fast.P, me, fbuf)
                vals[k].append(eval_value(w, mode, fbuf))
            ds = []
            for _ in range(args.rollouts):
                R = copy_state(S)
                s0, s1 = fast.rollout(R)
                ds.append((s0 - s1) if me == 0 else (s1 - s0))
            truth.append(np.mean(ds))
        truth = np.array(truth)
        for k in range(len(evals)):
            v = np.array(vals[k])
            rho[k].append(spearman(v, truth))
            regret[k].append(truth.max() - truth[int(v.argmax())])
    for k, name in enumerate(args.models):
        print(
            f"{name}: Spearman平均 {np.nanmean(rho[k]):+.3f}  選択手の後悔 {np.mean(regret[k]):.2f}点"
            f"（{len(regret[k])}局面, K={args.rollouts}）"
        )


if __name__ == "__main__":
    main()
