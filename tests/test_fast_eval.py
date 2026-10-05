import numpy as np

from carcassonne import State
from carcassonne.fast import Fast
from carcassonne.fast_eval import (
    FEATURE_NAMES,
    NF,
    collect,
    eval_value,
    fit_mlp,
    fit_ridge,
    load_eval,
)

FAST = Fast()


def test_feature_names_match_nf():
    assert len(FEATURE_NAMES) == NF


def test_features_are_antisymmetric_for_difference_features():
    from carcassonne.fast_eval import features

    st = State.new_game(5)
    S = FAST.new_game(st.deck)
    import random

    rng = random.Random(0)
    for _ in range(25):
        m = rng.choice(st.legal_moves())
        ti = st.current
        st.apply(m)
        FAST.apply(S, m.x, m.y, ti, m.variant, m.piece)
    a, b = np.zeros(NF), np.zeros(NF)
    features(S, FAST.T, FAST.P, 0, a)
    features(S, FAST.T, FAST.P, 1, b)
    names = list(FEATURE_NAMES)
    for n in ("score_diff", "proj_diff", "proj_city", "proj_road", "proj_field", "proj_monastery"):
        i = names.index(n)
        assert a[i] == -b[i], n
    # 自分/相手の開放端数は入れ替わる
    assert a[names.index("open_city_mine")] == b[names.index("open_city_theirs")]


def test_mlp_numba_forward_matches_numpy(tmp_path):
    X, y = collect(FAST, 40, seed=7)
    p, _ = fit_mlp(X, y, hidden=8, epochs=3)
    path = tmp_path / "m.npy"
    np.save(path, p)
    w, mode = load_eval(str(path))
    assert mode == 8
    mean, std = w[:NF], w[NF : 2 * NF]
    H = 8
    off = 2 * NF
    W1 = w[off : off + NF * H].reshape(NF, H)
    b1 = w[off + NF * H : off + NF * H + H]
    W2 = w[off + NF * H + H : off + NF * H + 2 * H]
    b2 = w[-1]
    for row in X[:20]:
        ref = np.maximum(((row - mean) / std) @ W1 + b1, 0) @ W2 + b2
        assert abs(eval_value(w, mode, row) - ref) < 1e-6


def test_linear_ridge_and_padding(tmp_path):
    X, y = collect(FAST, 60, seed=3)
    m = fit_ridge(X, y, 1.0)
    assert m.w.shape == (NF,)
    old = np.arange(14, dtype=float)
    path = tmp_path / "old.npy"
    np.save(path, old)
    w, mode = load_eval(str(path))
    assert mode == 1 and len(w) == NF and np.all(w[14:] == 0)
