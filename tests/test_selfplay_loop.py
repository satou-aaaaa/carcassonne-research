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


def _fake_data(path, n=3):
    np.savez(
        path, X=np.ones((n, NF)), y=np.zeros(n), p=np.zeros(n, np.int64), g=np.zeros(n, np.int64)
    )


def test_window_and_prune_across_attempt_1000(tmp_path):
    """試行番号が3桁から4桁に変わっても、直近 window 試行のデータを使い・それより前だけを消す。

    以前は名前を [1:4] で切っていたので a1003 を 100 と読み、学習のデータが全部消えた（Issue #141）。
    """
    from carcassonne.selfplay_loop import data_attempt, data_files, prune_data

    cfg = Config(games=1, chunk=1, sims=10, depth=2, window=4, workers=1)
    loop = Loop(tmp_path, cfg, "models/eval_v6_lin.npy")
    for a in range(996, 1004):
        _fake_data(tmp_path / "data" / f"a{a:03d}_00.npz")
    assert data_attempt(tmp_path / "data" / "a1003_00.npz") == 1003
    assert [data_attempt(f) for f in data_files(tmp_path / "data")] == list(range(996, 1004))
    loop.state["attempt"] = 1003
    loop.save()
    X, *_ = loop.load_window()
    assert len(X) == 4 * 3  # 1000〜1003
    gone = prune_data(tmp_path)
    assert sorted(data_attempt(f) for f in gone) == list(range(996, 1000))
    assert [data_attempt(f) for f in data_files(tmp_path / "data")] == list(range(1000, 1004))


def test_train_redoes_selfplay_when_data_is_missing(tmp_path):
    """学習の番なのにこの試行のデータが無いときは、落ちずに自己対戦からやり直す。"""
    cfg = Config(games=2, chunk=1, sims=10, depth=2, window=2, workers=1)
    loop = Loop(tmp_path, cfg, "models/eval_v6_lin.npy")
    loop.state["phase"] = "train"
    loop.save()
    msg = loop.step()
    assert loop.state["phase"] == "selfplay", msg
    assert "やり直" in msg


def test_data_names_are_not_cut_at_fixed_width():
    """ファイル名から番号を取るのに `name[1:4]` のような決まった幅の切り出しを使わない（桁が増えると読み違える）。"""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    files = [
        *root.glob("src/**/*.py"),
        *root.glob("scripts/**/*.py"),
        *root.glob(".github/workflows/*.yml"),
    ]
    bad = [
        f"{f.relative_to(root)}:{i}: {line.strip()}"
        for f in files
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"\b(name|stem)\[\d*:\d+\]", line)
    ]
    assert not bad, "番号は正規表現で取ってください（selfplay_loop.data_attempt）:\n" + "\n".join(
        bad
    )


def _through_git(root, work):
    """CI と同じく、状態を git のコミットにして別の場所へ取り出す（空のフォルダはここで消える）。"""
    import shutil
    import subprocess

    def git(*a, cwd):
        subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)

    repo = work / "repo"
    shutil.rmtree(repo, ignore_errors=True)
    shutil.copytree(root, repo / "loop")
    git("init", "-q", cwd=repo)
    git("add", "-A", "-f", "loop", cwd=repo)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "s", cwd=repo)
    out = work / f"clone{len(list(work.glob('clone*')))}"
    git("clone", "-q", str(repo), str(out), cwd=work)
    return out / "loop"


def test_loop_survives_state_passed_through_git(tmp_path):
    """CI は状態をブランチ selfplay-state で受け渡す。git は空のフォルダを残さないので、
    1単位ごとに git を通して取り出しても、どの番でも落ちずに進む（Issue #143: data/ が無くて落ちた）。
    """
    from carcassonne.selfplay_loop import prune_data

    cfg = Config(
        games=1, chunk=1, sims=10, depth=2, window=1, gate_seeds=1, gate_chunk=1,
        threshold=0.0, anchor_seeds=1, workers=1,
    )  # fmt: skip
    root = tmp_path / "start"
    Loop(root, cfg, "models/eval_v6_lin.npy")  # 作った直後は data/・gate/ が空
    seen = set()
    for _ in range(8):  # 自己対戦→学習→判定→初代と対戦→（次の試行）…
        root = _through_git(root, tmp_path)
        loop = Loop(root)
        seen.add(loop.state["phase"])
        loop.step()
        prune_data(root)  # CI は保存の前に片付ける
    assert seen == {"selfplay", "train", "gate", "anchor"}
    assert loop.attempt >= 2
    # 試行1003 のように data/ が丸ごと消えた状態から、学習の番を迎えても続けられる
    for f in (root / "data").glob("*.npz"):
        f.unlink()
    loop.state["phase"] = "train"
    loop.save()
    root = _through_git(root, tmp_path)
    assert not (root / "data").exists()
    loop = Loop(root)
    assert "やり直" in loop.step()
    loop.step()  # 自己対戦（以前はここで FileNotFoundError）
    assert loop.state["phase"] == "train"
