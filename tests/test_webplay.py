import copy
import json
import random

from carcassonne.agents import RandomAgent
from carcassonne.state import State
from carcassonne.webplay import HumanGame, tile_library


def _play(seed: int, seat: int, tmp_path):
    g = HumanGame(seed, seat, "test", RandomAgent(), "t", tmp_path / "g.jsonl")
    rng = random.Random(seed)
    while not g.st.over:
        v = g.view()
        assert v["placements"], "人間の手番なのに合法手がない"
        p = rng.choice(v["placements"])
        piece = rng.choice(p["pieces"] + [None])
        g.human_move(p["x"], p["y"], p["v"], piece)
        # 追跡中のミープル数が、手持ちの減少数と一致する
        for pl in (0, 1):
            assert sum(m["player"] == pl for m in g.meeples) == 7 - g.st.supply[pl]
    return g


def test_full_game_and_record(tmp_path):
    for seed, seat in [(1, 0), (2, 1)]:
        g = _play(seed, seat, tmp_path)
        assert g.view()["meeples"] == []  # 終局時はすべて回収
        # 棋譜ログの各行は盤上の場所を持つ（画面で押すとそのマスを示す）
        assert all({"x", "y"} <= e.keys() for e in g.events)
    lines = (tmp_path / "g.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[0])
    assert rec["diff_human"] == rec["human_score"] - rec["ai_score"]


def test_replay_matches_record(tmp_path):
    """記録した着手列を再生すると、同じ最終得点になる。"""
    g = _play(3, 0, tmp_path)
    rec = json.loads((tmp_path / "g.jsonl").read_text(encoding="utf-8"))
    st = State.new_game(rec["seed"])
    from carcassonne.state import Move

    for _, x, y, t, v, piece in rec["moves"]:
        assert st.current == t
        st.apply(Move(x, y, v, piece))
    assert st.scores == rec["scores"] == g.st.scores


def test_rejects_illegal_move(tmp_path):
    g = HumanGame(5, 0, "test", RandomAgent(), "t", tmp_path / "g.jsonl")
    try:
        g.human_move(99, 99, 0, None)
    except ValueError:
        return
    raise AssertionError("不正手が通った")


def test_tile_library():
    lib = tile_library()
    assert len(lib) == 24 and sum(t["count"] for t in lib) == 72


def test_coach_reports_loss_and_marks_record(tmp_path):
    """ヒントありの対局: 人間の手ごとにAIの最善手と損失を返し、記録に coach が付く。"""
    from carcassonne.fast_mcts import FastMCTSAgent
    from carcassonne.webplay import coach_text, make_coach

    coach = make_coach(FastMCTSAgent(n_sims=300))
    g = HumanGame(4, 0, "test", RandomAgent(), "t", tmp_path / "g.jsonl", coach=coach)
    rng = random.Random(4)
    for _ in range(3):
        v = g.view()
        p = rng.choice(v["placements"])
        g.human_move(p["x"], p["y"], p["v"], None)
        c = g.view()["last_coach"]
        assert c["loss"] is None or c["loss"] >= 0
        assert {"x", "y", "v", "piece", "kind"} <= c["best"].keys()
        assert coach_text(c).startswith("ヒント")
    assert any(e["text"].startswith("ヒント") for e in g.events)
    while not g.st.over:
        p = rng.choice(g.view()["placements"])
        g.human_move(p["x"], p["y"], p["v"], None)
    rec = json.loads((tmp_path / "g.jsonl").read_text(encoding="utf-8"))
    assert rec["coach"] is True


def test_undo_restores_position_and_marks_record(tmp_path):
    """待った: 自分の手とAIの返し手を取り消して同じ局面に戻り、記録に回数が残る。"""
    g = HumanGame(6, 0, "test", RandomAgent(), "t", tmp_path / "g.jsonl")
    rng = random.Random(6)
    for _ in range(3):
        p = rng.choice(g.view()["placements"])
        g.human_move(p["x"], p["y"], p["v"], p["pieces"][0] if p["pieces"] else None)
    before = copy.deepcopy(g.view())
    p = rng.choice(before["placements"])
    g.human_move(p["x"], p["y"], p["v"], p["pieces"][0] if p["pieces"] else None)
    g.undo()
    after = g.view()
    for k in ("board", "scores", "supply", "meeples", "placements", "current", "player"):
        assert after[k] == before[k], k
    assert after["can_undo"] and g.undos == 1
    while not g.st.over:
        p = rng.choice(g.view()["placements"])
        g.human_move(p["x"], p["y"], p["v"], None)
    assert not g.view()["can_undo"]
    rec = json.loads((tmp_path / "g.jsonl").read_text(encoding="utf-8"))
    assert rec["undos"] == 1 and rec["hints"] == 0


def test_hint_returns_legal_move(tmp_path):
    from carcassonne.fast_mcts import FastMCTSAgent
    from carcassonne.webplay import make_advisor

    g = HumanGame(7, 0, "test", RandomAgent(), "t", tmp_path / "g.jsonl",
                  advisor=make_advisor(FastMCTSAgent(n_sims=200)))  # fmt: skip
    g.request_hint()
    h = g.view()["hint"]
    p = next(
        q for q in g.view()["placements"] if (q["x"], q["y"], q["v"]) == (h["x"], h["y"], h["v"])
    )
    assert h["piece"] is None or h["piece"] in p["pieces"]
    g.human_move(h["x"], h["y"], h["v"], h["piece"])
    assert g.view()["hint"] is None and g.hints == 1
