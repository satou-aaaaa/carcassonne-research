import json

import numpy as np

from carcassonne.fast_eval import NF, fit_mlp, load_eval
from carcassonne.selfplay_loop import Config, Loop, eval_np


def test_eval_np_matches_numba_eval():
    from carcassonne.fast_eval import eval_value

    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, NF))
    y = X[:, 0] * 3 + np.maximum(X[:, 1], 0) * 5
    w, _ = fit_mlp(X, y, hidden=4, epochs=2)
    p, mode = w, 4
    got = eval_np(p, mode, X[:5])
    want = [eval_value(p, mode, x) for x in X[:5]]
    assert np.allclose(got, want)
    lin = rng.normal(size=NF)
    assert np.allclose(eval_np(lin, 1, X[:5]), [eval_value(lin, 1, x) for x in X[:5]])


def test_loop_runs_and_resumes(tmp_path):
    cfg = Config(
        games=2, chunk=1, sims=10, depth=2, window=2, gate_seeds=2, gate_chunk=1,
        threshold=0.0, anchor_seeds=1, workers=1,
    )  # fmt: skip
    loop = Loop(tmp_path, cfg, "models/eval_v6_lin.npy")
    msgs = [loop.step() for _ in range(2)]  # 自己対戦2塊
    assert loop.state["phase"] == "train", msgs
    # 再開: 状態ファイルから読み直して続ける
    loop = Loop(tmp_path)
    assert loop.cfg == cfg
    loop.step()  # 学習
    assert (tmp_path / "models" / "gen001.npy").exists()
    assert load_eval(str(tmp_path / "models" / "gen001.npy"))[1] == 1
    loop.step()
    loop.step()  # 判定2塊（2塊目で集計） → 閾値0なので採用
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st["champion"] == "models/gen001.npy"
    assert st["phase"] == "anchor"
    loop.step()  # 初代と対戦
    assert loop.state["phase"] == "selfplay" and loop.attempt == 2
    assert loop.state["history"][0]["vs_initial"]["games"] == 2
    assert "採用" in (tmp_path / "progress.md").read_text(encoding="utf-8")


def test_run_skips_when_locked(tmp_path):
    cfg = Config(games=1, chunk=1, sims=10, depth=2, workers=1)
    loop = Loop(tmp_path, cfg, "models/eval_v6_lin.npy")
    (tmp_path / "lock").write_text("other")
    assert not loop.run(0.0, log=lambda m: None)
    assert (tmp_path / "lock").exists()
    assert loop.run(0.0, log=lambda m: None, stale_minutes=0)  # 古いロックは奪う
    assert not (tmp_path / "lock").exists()


def test_window_pads_data_from_before_new_features(tmp_path):
    """特徴量を足す前（29個）のデータも、新しい特徴量を0として学習に使える。"""
    cfg = Config(games=1, chunk=1, sims=10, depth=2, window=2, workers=1)
    loop = Loop(tmp_path, cfg, "models/eval_v6_lin.npy")
    n = 5
    for name, nf in (("a001_00.npz", 29), ("a001_01.npz", NF)):
        np.savez(
            tmp_path / "data" / name,
            X=np.ones((n, nf)), y=np.zeros(n), p=np.zeros(n, np.int64), g=np.zeros(n, np.int64),
        )  # fmt: skip
    X, _, _, g = loop.load_window()
    assert X.shape == (2 * n, NF)
    assert np.all(X[:n, 29:] == 0) and np.all(X[n:] == 1)
    assert list(g) == [0] * n + [1] * n
