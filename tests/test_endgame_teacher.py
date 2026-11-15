"""終盤の勝率を教師にした評価関数（scripts/endgame_teacher.py）と、切り替え型の評価関数（mode=-1）。"""

import importlib.util
from pathlib import Path

import numpy as np

from carcassonne import State
from carcassonne.fast import SC_DRAW, SC_END, SC_OVER, apply_move, random_move, seed_rng
from carcassonne.fast_eval import (
    NF,
    eval_value,
    features,
    load_eval,
    split_eval_params,
)
from carcassonne.fast_mcts import FastMCTSAgent, reward_of

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "endgame_teacher", ROOT / "scripts/endgame_teacher.py"
)
et = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(et)


def _positions(n_games=3, seed=5):
    """ランダムに進めた局面（特徴量と山札の残り）。"""
    ag = FastMCTSAgent(n_sims=1)
    f = ag.fast
    sc = f.scratch
    out = []
    fb = np.zeros(NF)
    for g in range(n_games):
        S = ag.to_fast(State.new_game(seed + g))
        seed_rng(seed + g)
        while not S[10][SC_OVER]:
            features(S, f.T, f.P, 0, fb)
            out.append((fb.copy(), int(S[10][SC_END] - S[10][SC_DRAW])))
            m = random_move(
                S, f.T, f.P, 0.3, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, sc.free
            )
            apply_move(S, f.T, f.P, *m, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
    return out


def test_split_eval_switches_on_bag(tmp_path):
    rng = np.random.default_rng(0)
    a, b = rng.normal(size=NF), rng.normal(size=NF)
    p = tmp_path / "split.npy"
    np.save(p, split_eval_params(a, b, 4))
    w, mode = load_eval(str(p))
    assert mode == -1
    seen = set()
    for fb, bag in _positions():
        want = (b if bag <= 4 else a) @ fb
        assert abs(eval_value(w, mode, fb) - want) < 1e-9
        seen.add(bag <= 4)
    assert seen == {True, False}


def test_split_agent_plays(tmp_path):
    """切り替え型でも探索が評価関数を使う（mode=-1 を「評価関数なし」と取り違えない）。"""
    from carcassonne.webplay import champion_eval_path

    main_w, _ = load_eval(champion_eval_path())
    p = tmp_path / "split.npy"
    np.save(p, split_eval_params(main_w, main_w, 4))
    ag1 = FastMCTSAgent(n_sims=200, eval_path=str(p))
    ag2 = FastMCTSAgent(n_sims=200, eval_path=champion_eval_path())
    st = State.new_game(3)
    seed_rng(1)
    a1 = ag1.choose(ag1.to_fast(st))
    seed_rng(1)
    a2 = ag2.choose(ag2.to_fast(st))
    assert a1 == a2


def test_logit_weights_match_search_reward():
    """w*scale/2 で保存した重みは、探索の報酬 0.5+0.5*tanh(v/scale) で sigmoid(w·f) になる。"""
    rng = np.random.default_rng(1)
    w = rng.normal(size=NF) * 0.1
    for fb, _ in _positions(1)[:30]:
        z = float(w @ fb)
        assert (
            abs(reward_of(float((w * et.SCALE / 2) @ fb), et.SCALE) - 1 / (1 + np.exp(-z))) < 1e-9
        )


def test_fit_logistic_recovers_weights():
    rng = np.random.default_rng(2)
    X = np.column_stack([rng.normal(size=4000) * 5 + 3, rng.normal(size=4000), np.ones(4000)])
    w_true = np.array([0.4, -1.0, 0.3])
    y = 1 / (1 + np.exp(-(X @ w_true)))  # 確率そのものを教師にする
    w, b = et.fit_logistic(X, y, l2=1e-8)
    w[2] += b
    assert np.allclose(w, w_true, atol=1e-3)
