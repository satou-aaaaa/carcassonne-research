"""棋譜の記録・再生（records）と候補の特徴量（fast_eval_ext）。"""

from pathlib import Path

import numpy as np

from carcassonne.fast import Fast
from carcassonne.fast_eval_ext import NX, features_ext
from carcassonne.records import play_records, records_to_data, replay
from carcassonne.selfplay import generate

ROOT = Path(__file__).resolve().parents[1]
KW = {"n_sims": 20, "eval_path": str(ROOT / "models/eval_v9_block.npy"), "rollout_depth": 4}


def test_replay_matches_selfplay():
    """同じシードなら、棋譜から作り直したデータが selfplay.generate と一致する。"""
    decks, moves, nmoves = play_records(KW, 2, 1, seed=3)
    assert decks.shape == (2, 71) and (nmoves > 60).all()
    got = records_to_data(Fast(), decks, moves, nmoves)
    ref = generate(KW, 2, 1, seed=3, with_meta=True)
    for a, b in zip(got, ref):
        np.testing.assert_array_equal(a, b)


def test_ext_features_finite_and_symmetric():
    """候補の特徴量は有限で、手持ち0・合流の見込みは自分と相手を入れ替えると入れ替わる。"""
    decks, moves, nmoves = play_records(KW, 1, 1, seed=4)
    fast = Fast()
    f0, f1 = np.zeros(NX), np.zeros(NX)
    for k, S in enumerate(replay(fast, decks[0], moves[0], int(nmoves[0]))):
        if k == nmoves[0]:
            break
        features_ext(S, fast.T, fast.P, 0, f0)
        features_ext(S, fast.T, fast.P, 1, f1)
        assert np.isfinite(f0).all()
        assert (f0[5], f0[6]) == (f1[6], f1[5])
        assert np.isclose(f0[9], f1[10]) and np.isclose(f0[10], f1[9])
        assert np.isclose(f0[0], -f1[0]) and np.isclose(f0[2], f1[3])
        assert f0[2] >= 0.0 and f0[3] >= 0.0
