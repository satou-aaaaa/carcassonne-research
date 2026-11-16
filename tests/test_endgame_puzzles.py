"""終盤クイズの材料集め（scripts/endgame_puzzles.py、BACKLOG R-002）。"""

import importlib.util
import json
from pathlib import Path

import numpy as np

from carcassonne import State
from carcassonne.endgame import bag_left
from carcassonne.fast import SC_OVER, SC_PL, SC_S0, apply_move, copy_state, random_move, seed_rng
from carcassonne.fast_mcts import FastMCTSAgent

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "endgame_puzzles", ROOT / "scripts/endgame_puzzles.py"
)
ep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ep)


def test_gap_of():
    assert ep.gap_of(np.array([0.2, 0.9, 0.5, 0.9])) == (0.9, 0.5, 2)
    assert ep.gap_of(np.array([0.4, 0.4])) == (0.4, 0.4, 2)


def _record(tmp_path, seed=3):
    """ランダムな1局を records.py と同じ形の npz に保存する。"""
    ag = FastMCTSAgent(n_sims=1)
    f = ag.fast
    sc = f.scratch
    st = State.new_game(seed)
    S = ag.to_fast(st)
    seed_rng(seed)
    moves = []
    while not S[10][SC_OVER]:
        m = random_move(S, f.T, f.P, 0.3, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, sc.free)
        moves.append([int(x) for x in m])
        apply_move(S, f.T, f.P, *m, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g)
    p = tmp_path / "rec_test.npz"
    arr = np.full((1, 80, 3), -1, np.int32)
    arr[0, : len(moves)] = moves
    np.savez(p, deck=np.array([st.deck], np.int16), moves=arr, nmoves=np.array([len(moves)]))
    return p, ag, S


def test_job_rows_are_consistent(tmp_path):
    p, ag, _ = _record(tmp_path)
    rows = ep._job((str(p), 0, (1,), 0.0, 7))
    assert len(rows) == 1
    r = rows[0]
    assert r["bag"] == 1
    assert abs(r["best"] - r["second"] - r["gap"]) < 1e-6
    assert abs(r["best_move"]["win"] - r["best"]) < 1e-9
    for k in ("greedy", "diff", "champ"):
        assert r[k]["win"] <= r["best"] + 1e-9
    # 履歴（[x, y, 種別, 向き, 断片]）をたどると、同じ局面（山札の残り・得点）に戻る
    f = ag.fast
    S = f.new_game(r["deck"])
    for x, y, ti, vi, piece in r["history"]:
        f.apply(S, x, y, ti, vi, piece)
    assert len(r["history"]) == r["ply"]
    assert bag_left(S) == r["bag"]
    pl = int(S[10][SC_PL])
    assert (int(S[10][SC_S0 + pl]), int(S[10][SC_S0 + 1 - pl])) == (r["score_me"], r["score_opp"])
    # 最善手も同じ形で適用できる
    x, y, ti, vi, piece = r["best_move"]["move"]
    assert ti == r["tile"]
    S2 = copy_state(S)
    f.apply(S2, x, y, ti, vi, piece)
    assert State.new_game(3).deck == r["deck"]
    assert isinstance(ep.lesson(r), str)


def test_summary(tmp_path):
    p, _, _ = _record(tmp_path, seed=4)
    rows = ep._job((str(p), 0, (1, 2), 0.0, 7))
    out = tmp_path / "x.jsonl"

    out.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    s = ep.summarize(str(out))
    assert s["positions"] == len(rows)
    assert sum(v["count"] for v in s["lessons"].values()) == len(rows)
