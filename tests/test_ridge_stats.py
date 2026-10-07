import numpy as np

from carcassonne import ridge_stats
from carcassonne.fast_eval import fit_ridge


def make(n=500, nf=6, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, nf))
    X[:, -1] = 1.0
    w = rng.normal(size=nf)
    return X, X @ w + rng.normal(size=n)


def test_stats_solution_equals_direct_ridge():
    X, y = make()
    s = ridge_stats.stats_of(X, y)
    w = ridge_stats.solve_ridge(s, 3.0)
    assert np.allclose(w, fit_ridge(X, y, 3.0).w)


def test_merge_equals_concatenation_when_no_decay():
    X1, y1 = make(seed=1)
    X2, y2 = make(seed=2)
    merged = ridge_stats.merge(ridge_stats.stats_of(X1, y1), ridge_stats.stats_of(X2, y2), 1.0)
    full = ridge_stats.stats_of(np.concatenate([X1, X2]), np.concatenate([y1, y2]))
    for k in full:
        assert np.allclose(merged[k], full[k])


def test_decay_downweights_old_data():
    X1, y1 = make(seed=1)
    X2, y2 = make(seed=2)
    m = ridge_stats.merge(ridge_stats.stats_of(X1, y1), ridge_stats.stats_of(X2, y2), 0.5)
    assert np.isclose(m["n"], 0.5 * len(y1) + len(y2))


def test_r2_matches_direct_computation(tmp_path):
    X, y = make()
    s = ridge_stats.stats_of(X, y)
    w = ridge_stats.solve_ridge(s, 1.0)
    direct = 1 - ((y - X @ w) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    assert np.isclose(ridge_stats.r2(s, w), direct)
    path = tmp_path / "s.npz"
    ridge_stats.save(s, path)
    loaded = ridge_stats.load(path)
    assert all(np.allclose(loaded[k], s[k]) for k in s)
    assert ridge_stats.load(tmp_path / "none.npz") is None


def test_load_discards_stats_with_other_feature_count(tmp_path):
    rng = np.random.default_rng(1)
    X, y = rng.normal(size=(50, 4)), rng.normal(size=50)
    path = tmp_path / "s.npz"
    ridge_stats.save(ridge_stats.stats_of(X, y), path)
    assert ridge_stats.load(path, 4) is not None
    assert ridge_stats.load(path, 5) is None
    assert ridge_stats.load(path) is not None


def test_prior_is_kept_when_regularization_dominates():
    X, y = make()
    prior = np.arange(X.shape[1], dtype=float)
    w = fit_ridge(X, y, 1e9, prior=prior).w
    # バイアス（最後の列）以外は prior に張り付く
    assert np.allclose(w[:-1], prior[:-1], atol=1e-3)


def test_bias_feature_of_real_features_is_not_regularized():
    from carcassonne.fast_eval import NF_V6, bias_index

    rng = np.random.default_rng(0)
    X = rng.normal(size=(300, NF_V6))
    X[:, bias_index(NF_V6)] = 1.0
    y = np.full(300, 5.0)
    w = fit_ridge(X, y, 1e9).w
    assert abs(w[bias_index(NF_V6)] - 5.0) < 1e-3
