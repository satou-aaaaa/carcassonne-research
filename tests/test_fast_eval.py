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
    for n in (
        "score_diff",
        "proj_diff",
        "proj_city",
        "proj_road",
        "proj_field",
        "proj_monastery",
        "city_bonus",
        "supply_x_remaining",
        "proj_field_x_remaining",
        "proj_city_x_remaining",
        "monastery_room_x_remaining",
    ):
        i = names.index(n)
        assert abs(a[i] + b[i]) < 1e-12, n
    # 自分/相手の開放端数・置きっぱなしのミープルは入れ替わる
    assert a[names.index("open_city_mine")] == b[names.index("open_city_theirs")]
    assert a[names.index("stuck_mine")] == b[names.index("stuck_theirs")]


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


def test_legacy_mlp_is_padded(tmp_path):
    """特徴量22個の旧MLPを読むと、追加特徴量の値によらず旧特徴量だけの出力になる。"""
    from carcassonne.fast_eval import NF_V6

    rng = np.random.default_rng(0)
    H = 4
    old = np.concatenate(
        [
            rng.normal(size=NF_V6),
            rng.uniform(0.5, 2.0, NF_V6),
            rng.normal(size=NF_V6 * H + 2 * H + 1),
        ]
    )
    path = tmp_path / "old_mlp.npy"
    np.save(path, old)
    w, mode = load_eval(str(path))
    assert mode == H
    f = rng.normal(size=NF)
    g = f.copy()
    g[NF_V6:] = rng.normal(size=NF - NF_V6) * 100
    assert abs(eval_value(w, mode, f) - eval_value(w, mode, g)) < 1e-9
    mean, std = old[:NF_V6], old[NF_V6 : 2 * NF_V6]
    off = 2 * NF_V6
    W1 = old[off : off + NF_V6 * H].reshape(NF_V6, H)
    b1 = old[off + NF_V6 * H : off + NF_V6 * H + H]
    W2 = old[off + NF_V6 * H + H : off + NF_V6 * H + 2 * H]
    ref = np.maximum(((f[:NF_V6] - mean) / std) @ W1 + b1, 0) @ W2 + old[-1]
    assert abs(eval_value(w, mode, f) - ref) < 1e-9
