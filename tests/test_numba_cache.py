"""Numba の古いキャッシュを消す仕組み（_numba_cache）の確認。"""

from carcassonne._numba_cache import clear_if_stale


def test_clear_when_any_source_changes(tmp_path):
    (tmp_path / "fast.py").write_text("a = 1\n")
    (tmp_path / "fast_eval.py").write_text("b = 1\n")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "fast_mcts.run_tree-1.py313.nbi").write_text("x")
    assert clear_if_stale(tmp_path)  # 記録が無い: 消す
    assert not list(cache.glob("*.nbi"))

    (cache / "fast_mcts.run_tree-1.py313.nbi").write_text("x")
    assert not clear_if_stale(tmp_path)  # ソースが同じ: そのまま使う
    assert list(cache.glob("*.nbi"))

    # 呼ばれる側（fast_eval.py）だけ変えても、呼ぶ側のキャッシュまで消える
    (tmp_path / "fast_eval.py").write_text("b = 2\n")
    assert clear_if_stale(tmp_path)
    assert not list(cache.glob("*.nbi"))
