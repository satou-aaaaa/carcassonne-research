"""ブラウザ版（docs/ の JavaScript）のエンジンとAIが Python 版と一致するかの検証。

node で tests/play_js_harness.js を実行し、その記録を Python 版で再生して比べる。
node が無い環境では飛ばす（GitHub Actions の ubuntu-latest には入っている）。
"""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from carcassonne import State, load_tileset
from carcassonne.fast import Fast
from carcassonne.fast_eval import NF, features
from carcassonne.state import Move

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node が必要")
TS = load_tileset()


def run_js(args: dict, timeout: int = 600):
    r = subprocess.run(
        [NODE, str(ROOT / "tests" / "play_js_harness.js"), json.dumps(args)],
        capture_output=True, text=True, check=True, timeout=timeout,
    )  # fmt: skip
    return json.loads(r.stdout)


def py_snap(st: State) -> dict:
    return {
        "scores": list(st.scores),
        "supply": list(st.supply),
        "over": st.over,
        "player": st.player,
        "cur": -1 if st.current is None else st.current,
        "disc": len(st.discarded),
    }


def test_engine_matches_python():
    """同じ山札・同じ着手列で、毎手の合法手・得点・手持ち・予測得点・特徴量が Python 版と一致する。"""
    fast = Fast()
    f = np.zeros(NF)
    games = run_js({"cmd": "games", "seeds": list(range(8)), "meeple_prob": 0.6})
    n_meeple_moves = 0
    for game in games:
        st = State(game["deck"], TS)
        S = fast.new_game(game["deck"])
        assert py_snap(st) == game["start"]
        for step in game["steps"]:
            legal = {tuple(m) for m in step["legal"]}
            assert legal == {(m.x, m.y, st.current, m.variant, m.piece) for m in st.legal_moves()}
            features(S, fast.T, fast.P, st.player, f)
            np.testing.assert_allclose(step["feats"], f, atol=1e-9)
            x, y, ti, vi, piece = step["move"]
            assert ti == st.current
            st.apply(Move(x, y, vi, piece))
            fast.apply(S, x, y, ti, vi, piece)
            n_meeple_moves += piece is not None
            assert step["snap"] == py_snap(st)
            assert step["projected"] == st.projected_scores()
        assert st.over
    assert n_meeple_moves > 100  # ミープルを置く手も十分に確かめている


def test_search_returns_legal_moves():
    for level in ("standard", "greedy"):
        res = run_js({"cmd": "search", "seeds": [1, 2, 3], "plies": 20, "level": level})
        assert res and all(r["legal"] for r in res)


@pytest.mark.slow
def test_browser_ai_beats_greedy():
    """ブラウザ版の標準設定（MCTS 2000回＋評価関数）が、貪欲法に勝ち越す。"""
    res = run_js({"cmd": "match", "seeds": [1, 2, 3, 4], "a": "standard", "b": "greedy"})
    wins = sum(r["diff_a"] > 0 for r in res)
    mean = sum(r["diff_a"] for r in res) / len(res)
    assert wins >= 6 and mean > 5, res
