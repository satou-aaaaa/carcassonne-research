"""評価関数の「手の順位付け」性能を測る（R²とは別の指標）。

ランダム〜貪欲の対局から局面を抽出し、各局面の全合法手について
  - 評価関数の値: 手を指した後の局面を、指した側の視点で評価
  - 基準値: 手の後からのランダムロールアウトK回の終局得点差の平均（指した側の視点）
を求め、局面ごとの Spearman 順位相関と、評価関数が選んだ手の基準値の後悔（基準値の最大との差）を平均する。

    py scripts/eval_rank.py models/eval_v6_lin.npy models/eval_v5_mlp.npy --positions 40 --rollouts 30

--root-sims N を付けると、基準をロールアウト版MCTS（N回）の根の訪問数に置き換える（配置単位。
評価関数側は各配置で最も良いミープル選択の値を使う）。ランダムロールアウト基準より探索の目的に近い。
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
from carcassonne.fast import (
    SC_CUR,
    SC_PL,
    SC_SUP0,
    apply_move,
    copy_state,
    gen_placements,
    piece_free,
    seed_rng,
)
from carcassonne.fast_eval import NF, eval_value, features, load_eval
from carcassonne.fast_mcts import FastMCTSAgent, run_tree, shuffle_rest


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


def root_visits(agent: FastMCTSAgent, S, sims: int):
    """ロールアウト版MCTSの根の訪問数を、配置ごとに返す（cells, gs, visits）。"""
    fast, sc = agent.fast, agent.fast.scratch
    sc.stamp_box[0] += 1
    k = gen_placements(
        S, fast.T, S[10][SC_CUR], sc.stamp, sc.stamp_box[0], sc.out_cell, sc.out_g, False
    )
    cells, gs = sc.out_cell[:k].copy(), sc.out_g[:k].copy()
    agg1 = np.zeros(k, np.int64)
    agg2 = np.zeros((k, fast.P + 1), np.int64)
    D, W = copy_state(S), copy_state(S)
    shuffle_rest(D)
    run_tree(
        D, fast.T, fast.P, sims, 0.5, 30.0, 0.3, -1, sc.stamp, sc.stamp_box, sc.out_cell,
        sc.out_g, sc.free, sc.rec, W, agg1, agg2, cells, gs, k,
        np.zeros(NF), 0, np.zeros(NF), 0,
    )  # fmt: skip
    return cells, gs, agg1


def best_piece_eval(agent, S, cell, g, me, w, mode, fbuf):
    """配置 (cell, g) の後局面を、ミープルなし/置ける各断片で評価した最大値（me視点）。"""
    fast, sc = agent.fast, agent.fast.scratch
    opts = [-1]
    if S[10][SC_SUP0 + me] > 0:
        opts += [
            pi for pi in range(int(fast.T[1][g])) if piece_free(S, fast.T, fast.P, cell, g, pi)
        ]
    best = -1e30
    for pi in opts:
        R = copy_state(S)
        apply_move(R, fast.T, fast.P, cell, g, pi, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
        features(R, fast.T, fast.P, me, fbuf)
        best = max(best, eval_value(w, mode, fbuf))
    return best


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
    ap.add_argument("--root-sims", type=int, default=0, help="根の訪問数を基準にする（0で無効）")
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
        if args.root_sims:
            cells, gs, vis = root_visits(agent, base, args.root_sims)
            truth = vis.astype(float)
            for k, (w, mode) in enumerate(evals):
                v = np.array(
                    [
                        best_piece_eval(agent, base, c, g, me, w, mode, fbuf)
                        for c, g in zip(cells, gs)
                    ]
                )
                rho[k].append(spearman(v, truth))
                regret[k].append((truth.max() - truth[int(v.argmax())]) / max(truth.sum(), 1))
            continue
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
        if args.root_sims:
            print(
                f"{name}: Spearman平均(根の訪問数) {np.nanmean(rho[k]):+.3f}  "
                f"選択配置の訪問数の取りこぼし {np.mean(regret[k]):.3f}（{len(regret[k])}局面, "
                f"根{args.root_sims}回）"
            )
            continue
        print(
            f"{name}: Spearman平均 {np.nanmean(rho[k]):+.3f}  選択手の後悔 {np.mean(regret[k]):.2f}点"
            f"（{len(regret[k])}局面, K={args.rollouts}）"
        )


if __name__ == "__main__":
    main()
