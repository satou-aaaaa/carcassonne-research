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
import refresh_ai_content

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


def test_claims_ignore_order_within_noise():
    """得点源の順位が数点の差で入れ替わっただけでは止めない。

    gen576 で草原と道が逆になり（#83）、gen836 で都市が3位になって（#105）止まった。
    """
    summ = json.loads((ROOT / "docs/results/habits_summary.json").read_text(encoding="utf-8"))
    s, g = summ["habits_strong"], summ["habits_greedy"]
    # 集計の更新に左右されないよう、得点源ごとの差は固定値にする
    for lead in (
        {"C": 6.0, "F": 3.0, "R": 3.5, "M": 2.0},
        {"C": 5.7, "F": 6.4, "R": 1.4, "M": 0.8},
        {"C": 4.1, "F": 5.6, "R": 2.4, "M": 5.2},
    ):
        build_tips_page.check_claims(s, g, lead)
    # 勝った側が都市で負けているなら、本文の言い切りは成り立たない
    with pytest.raises(SystemExit, match="#citywins"):
        build_tips_page.check_claims(s, g, {"C": -1.0, "F": 6.0, "R": 3.0, "M": 5.0})


HISTORY = sorted((ROOT / "tests/data/habits_history").glob("*.json"))


@pytest.mark.parametrize("path", HISTORY, ids=[p.stem for p in HISTORY])
def test_claims_hold_on_every_past_generation(path):
    """本文の言い切りは、過去の世代の集計でもすべて成り立つこと（48局のぶれで止まらない言い方か）。

    言い切りを足す・変えるときは、ここが通る言い方にする。学習ページを作り直した世代は
    tests/data/habits_history/ に足していく（AI content の PR に入れなくてよい。止まったときに足す）。
    """
    d = json.loads(path.read_text(encoding="utf-8"))
    s, g = d["habits_strong"], d["habits_greedy"]
    lead = {k: s["winner_points_by_kind"][k] - s["loser_points_by_kind"][k] for k in "CRMF"}
    build_tips_page.check_claims(s, g, lead)


def test_history_has_enough_generations():
    assert len(HISTORY) >= 8


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


def test_flipped_claim_holds_the_tips_page_instead_of_failing(tmp_path, monkeypatch):
    """言い切りが1つ外れても、ジョブを止めずにコツ集を前の版で残し、同じAIでは作り直さない。

    以前は止めていたので、文を直すまで毎日赤になった（gen419・gen576・gen836・gen926、2026-10-24〜11-03 に 11 回）。
    """
    summ = json.loads((ROOT / "docs/results/habits_summary.json").read_text(encoding="utf-8"))
    assert build_tips_page.summary_failed_claims(summ) == []
    flipped = copy.deepcopy(summ)
    s = flipped["habits_strong"]
    s["winner_points_by_kind"]["C"] = s["loser_points_by_kind"]["C"] - 1  # 勝った側が都市で負けた
    flipped["ai"] = {"name": "genX"}
    bad = build_tips_page.summary_failed_claims(flipped)
    assert any("#citywins" in m for m in bad)

    monkeypatch.setattr(refresh_ai_content, "BLOCKED", tmp_path / "tips_blocked.json")
    monkeypatch.setattr(refresh_ai_content, "champion_info", lambda: {"name": "genX"})
    monkeypatch.setattr(
        refresh_ai_content, "content_ai", lambda: {"tips": "gen1", "quiz": ["genX"]}
    )
    assert refresh_ai_content.is_stale()  # コツ集が古い
    refresh_ai_content.hold(flipped, bad)
    held = json.loads((tmp_path / "tips_blocked.json").read_text(encoding="utf-8"))
    assert held["ai"]["name"] == "genX" and held["failed_claims"] == bad
    assert set(held) >= {
        "habits_strong",
        "habits_greedy",
    }  # 直すときに tests/data/habits_history/ へ足せる
    assert not refresh_ai_content.is_stale()  # 同じAIでは毎日作り直さない
    monkeypatch.setattr(refresh_ai_content, "champion_info", lambda: {"name": "genY"})
    assert refresh_ai_content.is_stale()  # 次のAIが出たら、また試す


def test_no_held_tips_left_in_the_repository():
    """data/tips_blocked.json が main に残っていたら、言い切りの直しが済んでいない（Issue が開いている）。

    ここでは失敗にしない（自動の PR を止めないため）。中身が直し方どおりの形かだけ見る。
    """
    p = ROOT / "data" / "tips_blocked.json"
    if p.exists():
        held = json.loads(p.read_text(encoding="utf-8"))
        assert held["failed_claims"] and held["ai"]["name"]
