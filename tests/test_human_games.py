"""人がAIと指した棋譜（対戦ページから送ってもらうもの）の検査・受け取り・学習データ化。"""

from __future__ import annotations

import json
import random

import numpy as np
import pytest

from carcassonne import human_games as hg
from carcassonne.fast import Fast
from carcassonne.fast_eval import NF
from carcassonne.selfplay_loop import Config, Loop
from carcassonne.state import State
from carcassonne.tiles import load_tileset

TS = load_tileset()


def make_record(seed: int, human_seat: int = 0) -> dict:
    """Python 版でランダムに1局指し、対戦ページが書き出すのと同じ形の棋譜にする。"""
    rng = random.Random(seed)
    deck = [i for i, t in enumerate(TS.types) for _ in range(t.count)]
    deck.remove(TS.start)
    rng.shuffle(deck)
    st = State(deck, TS)
    moves = []
    while not st.over:
        m = st.random_move(rng, 0.5)
        moves.append([m.x, m.y, m.variant, -1 if m.piece is None else m.piece])
        st.apply(m)
    return {
        "v": 1, "deck": deck, "moves": moves, "human_seat": human_seat, "level": "strong",
        "ai": "gen1", "coach": False, "hints": 0, "undos": 0, "scores": list(st.scores),
        "name": "山田",
    }  # fmt: skip


def issue_body(rec: dict) -> str:
    return f"<!-- {hg.MARK} -->\n説明\n\n```json\n{json.dumps(rec)}\n```\n"


def test_normalize_accepts_valid_game_and_drops_name():
    rec = hg.normalize(make_record(1), TS)
    assert "name" not in rec and rec["ai"] == "gen1"
    assert set(rec) == set(hg.KEEP)


@pytest.mark.parametrize(
    ("change", "msg"),
    [
        (lambda r: r["moves"].__setitem__(3, [40, 40, 0, -1]), "置けない"),
        (lambda r: r.__setitem__("scores", [999, 0]), "得点"),
        (
            lambda r: r.__setitem__("deck", r["deck"][:-1] + [(r["deck"][-1] + 1) % len(TS.types)]),
            "71枚",
        ),
        (lambda r: r.__setitem__("moves", r["moves"][:-5]), "最後まで"),
        (lambda r: r.__setitem__("level", "god"), "level"),
        (lambda r: r.__setitem__("v", 2), "版"),
    ],
)
def test_normalize_rejects_broken_records(change, msg):
    rec = make_record(2)
    change(rec)
    with pytest.raises(hg.RecordError, match=msg):
        hg.normalize(rec, TS)


def test_ingest_issue_adds_once(tmp_path):
    path = tmp_path / "games.jsonl"
    body = issue_body(make_record(3))
    assert hg.ingest_issue(body, path, TS)[0] == "added"
    assert hg.ingest_issue(body, path, TS)[0] == "duplicate"
    assert len(hg.load(path)) == 1
    assert hg.ingest_issue("ただの Issue", path, TS)[0] == "invalid"
    assert hg.ingest_issue(f"<!-- {hg.MARK} -->\n```json\n{{壊れた\n```", path, TS)[0] == "invalid"
    assert len(hg.load(path)) == 1


def test_to_data_and_report(tmp_path):
    games = [hg.normalize(make_record(s, s % 2), TS) for s in (4, 5)]
    X, y, p, g = hg.to_data(Fast(), games)
    n = sum(len(r["moves"]) for r in games)
    assert X.shape == (n, NF) and len(y) == len(p) == len(g) == n
    # 終局得点差は手番の視点（先手の差の符号を、後手の局面では反転）
    s0 = games[0]["scores"]
    assert y[0] == s0[0] - s0[1]
    w = np.load("models/eval_champion.npy")
    text = hg.report_md(Fast(), games, np.concatenate([w, np.zeros(NF - len(w))]))
    assert "受け取った対局: 2局" in text and "| strong | 2 |" in text
    # 各局・各「大きく下がった手」から対戦ページの再生へ飛べる（番号は1始まり、手はその直前から）
    assert f"[1局目]({hg.replay_url(1)})" in text and f"[2局目]({hg.replay_url(2)})" in text
    assert hg.replay_url(2, 5).endswith("play.html#replay=2&ply=5")


def test_selfplay_loop_mixes_human_games(tmp_path):
    games = tmp_path / "human.jsonl"
    hg.add(games, hg.normalize(make_record(6), TS))
    cfg = Config(games=1, chunk=1, sims=10, depth=2, window=1, workers=1, human_games=str(games))
    loop = Loop(tmp_path / "loop", cfg, "models/eval_v6_lin.npy")
    loop.step()  # 自己対戦
    _, y, _, g = loop.load_window()
    n_h = len(hg.load(games)[0]["moves"])
    assert loop.n_human == n_h and len(y) > n_h
    assert (g[:n_h] == 0).all() and g[n_h:].min() == 1  # 人の局は先頭、自己対戦はその後
    loop.cfg.human_weight = 0
    assert len(loop.load_window()[1]) == len(y) - n_h


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="node が必要")
def test_browser_record_is_accepted():
    """公開ページ（JavaScript）が書き出す棋譜を、Python 側がそのまま受け取れる。"""
    from tests.test_play_js import run_js

    for rec in run_js({"cmd": "record", "seeds": [1, 2]}):
        out = hg.normalize(rec, TS)
        assert out["undos"] == 1 and out["moves"] == rec["moves"]


def test_form_rows_are_checked_and_added(tmp_path):
    """Google フォームの回答（公開 CSV）から、正しい棋譜だけを足す。"""
    import csv
    import io

    good = json.dumps(make_record(7))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["タイムスタンプ", "棋譜"])
    w.writerows(
        [["2026/11/12 3:00:00", good], ["2026/11/12 3:01:00", good], ["x", "test"], ["y", ""]]
    )
    texts = hg.form_texts(buf.getvalue())
    assert len(texts) == 3
    got = hg.ingest_rows(texts, tmp_path / "g.jsonl", TS)
    assert got == {"added": 1, "duplicate": 1, "invalid": 1}


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="node が必要")
def test_browser_replay_steps_through_record():
    """対戦ページの再生（play_local.js の ReplayGame）が、受け取った棋譜を一手ずつ正しくたどる。"""
    from tests.test_play_js import run_js

    good = [hg.normalize(make_record(s, s % 2), TS) for s in (8, 9)]
    bad = make_record(10)
    bad["moves"][3] = [40, 40, 0, -1]
    short_deck = make_record(11)
    short_deck["deck"] = short_deck["deck"][:-1]
    got = run_js({"cmd": "replay", "records": [*good, bad, short_deck], "ply": 10})
    for rec, r in zip(good, got["out"], strict=False):
        assert r["mid"] == {
            "board": 11, "replay": r["mid"]["replay"], "over": False, "placements": 0
        }  # fmt: skip
        assert r["mid"]["replay"]["ply"] == 10 and r["mid"]["replay"]["total"] == len(rec["moves"])
        assert r["end"]["over"] and r["end"]["scores"] == rec["scores"]
    assert "4手目" in got["out"][2]["error"]
    assert "71枚" in got["out"][3]["error"]
    assert got["closed"] is None  # 再生の前に対局がなければ、閉じると何もない
