"""人との対局から分かったことの集計（human_findings）。採点はにせものの coach で速く試す。"""

from __future__ import annotations

from carcassonne import human_findings as hf
from carcassonne.state import Move, State

from .test_human_games import TS, make_record


def fake_coach(loss_of):
    """AIの最善手はいつも「最初の合法手」、損は loss_of(ply) を返す coach。"""

    def coach(st: State, move: Move, seed: int) -> dict:
        m = st.legal_moves()[0]
        return {
            "best": {"x": m.x, "y": m.y, "v": m.variant, "piece": m.piece},
            "loss": loss_of(seed),
        }

    return coach


def test_category():
    assert hf.category(None, None, "C") == "unexplored"
    assert hf.category(5.0, None, "C") == "no_meeple"
    assert hf.category(5.0, "R", None) == "extra_meeple"
    assert hf.category(5.0, "R", "C") == "other_feature"
    assert hf.category(5.0, "C", "C") == "placement"
    assert hf.category(5.0, None, None) == "placement"


def test_phase():
    assert [hf.phase(p) for p in (0, 23, 24, 47, 48, 70)] == [
        "early", "early", "middle", "middle", "late", "late"
    ]  # fmt: skip


def test_analyze_game_scores_only_human_moves():
    rec = make_record(4, human_seat=1)
    moves = hf.analyze_game(rec, fake_coach(lambda ply: 0.0), TS)
    assert [m["ply"] for m in moves] == list(range(1, len(rec["moves"]), 2))
    assert all(m["cat"] in hf.CATS for m in moves)


def test_summarize_counts_bad_moves_and_examples():
    recs = [make_record(5), make_record(6, human_seat=1)]
    loss = lambda ply: 8.0 if ply in (2, 30) else (None if ply == 61 else 0.5)
    moves = [hf.analyze_game(r, fake_coach(loss), TS) for r in recs]
    swings = [{"game": 1, "ply": 12, "drop": 6.0}, {"game": 0, "ply": 3, "drop": 1.0}]
    s = hf.summarize(recs, moves, swings)
    assert s["games"] == 2 and s["trend"] is False
    # 先手の局は ply 2・30 が悪手、後手の局は ply 61 が「AIがほとんど考えなかった手」
    assert s["bad_moves"] == 3 and s["by_cat"]["unexplored"] == 1
    assert s["by_phase"]["early"]["bad"] == 1 and s["by_phase"]["middle"]["bad"] == 1
    assert s["by_phase"]["late"]["bad"] == 1
    assert [(w["game"], w["ply"]) for w in s["worst"]] == [(1, 3), (1, 31)]
    assert s["loss_bad_per_game"] == 8.0 and s["loss_small_per_game"] > 0
    assert s["ai_misreads"] == [{"game": 2, "ply": 12, "drop": 6.0}]
    assert hf.top_cat(s) is not None and hf.top_phase(s) is not None


def test_summarize_empty():
    s = hf.summarize([], [], [])
    assert s["games"] == 0 and s["bad_moves"] == 0 and s["mean_loss"] is None
    assert s["loss_small_per_game"] is None
    assert hf.top_cat(s) is None and hf.top_phase(s) is None
