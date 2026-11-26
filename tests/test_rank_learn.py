"""scripts/rank_learn.py（R-024、先生の手を上に並べる学習）の部品。"""

import importlib.util
import random
from pathlib import Path

import numpy as np

from carcassonne.fast_mcts import FastMCTSAgent
from carcassonne.state import State

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rank_learn", ROOT / "scripts" / "rank_learn.py")
rl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rl)


def test_rank_loss_gradient_matches_finite_difference():
    rng = np.random.default_rng(0)
    n = np.array([3, 5, 2])
    C = rng.normal(size=(n.sum(), rl.NF))
    w = rng.normal(size=rl.NF) * 0.1
    loss, grad = rl.rank_loss(w, C, n, 3.0)
    for j in (0, 5, 17):
        e = np.zeros(rl.NF)
        e[j] = 1e-6
        num = (rl.rank_loss(w + e, C, n, 3.0)[0] - rl.rank_loss(w - e, C, n, 3.0)[0]) / 2e-6
        assert abs(num - grad[j]) < 1e-5
    assert loss > 0


def test_legal_moves_include_agent_choice_and_children_differ():
    agent = FastMCTSAgent(n_sims=30, eval_path="models/eval_v9_block.npy")
    S = agent.to_fast(State.new_game(5))
    random.seed(1)
    moves = rl.legal_moves(S, agent.fast)
    assert len(set(moves)) == len(moves) > 1
    cell, g, piece = agent.choose(S)
    assert (int(cell), int(g), int(piece)) in moves
    F = rl.child_features(S, agent.fast, moves, int(S[10][rl.SC_PL]))
    assert F.shape == (len(moves), rl.NF)
    assert np.ptp(F, axis=0).max() > 0  # 手によって着手後の局面が違う


def test_feature_screen_candidates_run_on_a_position():
    spec2 = importlib.util.spec_from_file_location(
        "feature_screen", ROOT / "scripts" / "feature_screen.py"
    )
    fs = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(fs)
    agent = FastMCTSAgent(n_sims=30, eval_path="models/eval_v9_block.npy")
    S = agent.to_fast(State.new_game(5))
    for name, (width, fn, _) in fs.SETS.items():
        out = np.full(width, np.nan)
        fn(S, agent.fast.T, agent.fast.P, 0, out)
        assert np.isfinite(out).all(), name
    # 先生の手（先頭）が別の手と同点なら、一致は同点の数で割る
    C = np.array([[1.0], [1.0], [0.0]])
    assert fs.agreement(np.array([1.0]), C, np.array([3])) == 0.5
