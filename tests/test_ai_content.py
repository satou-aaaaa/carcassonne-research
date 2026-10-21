"""学習ページ（コツ集・クイズ）を最新AIで作り直す仕組みの確認。"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_puzzles
import build_tips_page
import recheck_puzzles

from carcassonne.webplay import champion_eval_path, champion_info


def test_champion_is_used_everywhere():
    # 対戦ページ・ローカル対戦・コツ集・クイズは、どれも最新チャンピオンの評価関数を使う
    assert champion_eval_path().endswith("eval_champion.npy")
    assert champion_info()["name"]


def test_tips_and_quiz_name_the_ai_they_were_made_with():
    summ = json.loads((ROOT / "docs/results/habits_summary.json").read_text(encoding="utf-8"))
    assert summ["ai"]["name"]
    puzzles = json.loads((ROOT / "data/puzzles.json").read_text(encoding="utf-8"))
    assert all(p.get("checked_by", {}).get("name") for p in puzzles)
    html = (ROOT / "docs/ai_tips.html").read_text(encoding="utf-8")
    assert summ["ai"]["name"] in html


def test_captions_cover_every_example():
    ex = json.loads((ROOT / "docs/results/habits_examples.json").read_text(encoding="utf-8"))
    caps = build_tips_page.captions(ex)
    assert set(caps) == {f"cap_{k}" for k in ex}
    assert all("実戦の例" in c for c in caps.values())


def test_claims_stop_the_build_when_the_trend_flips():
    summ = json.loads((ROOT / "docs/results/habits_summary.json").read_text(encoding="utf-8"))
    s, g = summ["habits_strong"], summ["habits_greedy"]
    lead = {k: s["winner_points_by_kind"][k] - s["loser_points_by_kind"][k] for k in "CRMF"}
    build_tips_page.check_claims(s, g, lead)  # いまの集計は本文と合っている
    flipped = copy.deepcopy(s)
    flipped["skip_meeple_with_supply"] = g["skip_meeple_with_supply"] - 0.01
    with pytest.raises(SystemExit, match="#keep"):
        build_tips_page.check_claims(flipped, g, lead)


def test_disputed_puzzle_is_marked_and_left_out_of_the_page():
    puzzles = json.loads((ROOT / "data/puzzles.json").read_text(encoding="utf-8"))[:2]
    res = [
        {"id": puzzles[0]["id"], "diffs": [1.0, 5.0, None, 0.0][: len(puzzles[0]["options"])],
         "visits": [0.1] * len(puzzles[0]["options"]), "best_ok": False, "top": 1},
        {"id": puzzles[1]["id"], "diffs": [None] * len(puzzles[1]["options"]),
         "visits": [0.0] * len(puzzles[1]["options"]), "best_ok": True, "top": 0},
    ]  # fmt: skip
    old_diff = puzzles[1]["options"][0]["diff"]
    bad = recheck_puzzles.apply_results(puzzles, res, {"name": "genX", "date": "2026-01-01"})
    assert bad == [puzzles[0]["id"]]
    assert "genX" in puzzles[0]["disputed"]
    assert "disputed" not in puzzles[1]
    assert puzzles[1]["options"][0]["diff"] == old_diff  # 探索されなかった手は前の値を残す
    assert puzzles[0]["checked_by"]["name"] == "genX"
    note = build_puzzles.ai_note([puzzles[1]])
    assert "genX" in note and "2026-01-01" in note


def test_recheck_rebuilds_the_puzzle_position():
    p = json.loads((ROOT / "data/puzzles.json").read_text(encoding="utf-8"))[0]
    r = recheck_puzzles.recheck(p, sims=40)
    assert r["id"] == p["id"] and len(r["diffs"]) == len(p["options"])
    assert any(d is not None for d in r["diffs"])


def test_disputed_when_ai_top_is_outside_the_options():
    p = json.loads((ROOT / "data/puzzles.json").read_text(encoding="utf-8"))[:1]
    n = len(p[0]["options"])
    res = [{"id": p[0]["id"], "diffs": [1.0] * n, "visits": [0.1] * n,
            "best_ok": False, "top": 0, "ai_top_listed": False}]  # fmt: skip
    assert recheck_puzzles.apply_results(p, res, {"name": "genX"}) == [p[0]["id"]]
    assert "選択肢の外" in p[0]["disputed"]


def test_dispute_reason_names_both_problems():
    r = {"top": 1, "ai_top_listed": False}
    assert recheck_puzzles.reason(r) == "選択肢2の点差が最大、一番よく選ぶ手は選択肢の外"
    assert recheck_puzzles.reason({"top": 2, "ai_top_listed": True}) == "選択肢3の点差が最大"
