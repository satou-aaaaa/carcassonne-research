"""終盤編のクイズ（data/puzzles.json の "exact": true、scripts/endgame_quiz.py）。"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_puzzles
import endgame_quiz
import recheck_puzzles

from carcassonne.puzzles import snapshot

PUZ = json.loads((ROOT / "data/puzzles.json").read_text(encoding="utf-8"))
EXACT = [p for p in PUZ if p.get("exact")]


def test_there_are_endgame_puzzles():
    assert len(EXACT) >= 5
    for p in EXACT:
        assert len(p["options"]) == len(p["notes"]) == len(p["en"]["notes"])
        assert all("win" in o for o in p["options"])


def test_position_matches_deck_and_history():
    """問題の盤面・得点・手番のタイルが、山札と着手履歴から作り直したものと同じ（解説の前提）。"""
    for p in EXACT:
        st, meeples = endgame_quiz.replay(p)
        snap = snapshot(st, meeples)
        for k in ("board", "meeples", "scores", "supply", "player", "current", "remaining"):
            assert snap[k] == p[k], (p["id"], k)


def test_answers_are_exact():
    """読み切り直しても、正解（先頭）の勝つ確率がほかの選択肢より厳密に高く、書いてある値と同じ。"""
    for p in EXACT:
        r = recheck_puzzles.recheck_exact(p)
        assert r["best_ok"], p["id"]
        assert r["wins"] == [o["win"] for o in p["options"]], p["id"]


def test_page_data_and_order():
    pages = [build_puzzles.to_page(p) for p in PUZ if not p.get("disputed")]
    ex = [q for q in pages if q.get("exact")]
    assert ex and all("win" in o for q in ex for o in q["options"])
    # 終盤編は AI の世代の一文に混ぜない（読み切りなのでAIに依らない）
    assert "読み切り" not in build_puzzles.ai_note(PUZ)
