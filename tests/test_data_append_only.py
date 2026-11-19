"""集めた対局データは足すだけ（scripts/check_data_append_only.py）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_data_append_only import problems


def test_append_is_ok():
    assert problems("a\nb\n", "a\nb\nc\n", "f") == []
    assert problems(None, "a\n", "f") == []  # まだ無いファイル
    assert problems("a\n", "a\n", "f") == []


def test_removal_or_rewrite_is_stopped():
    assert "消えて" in problems("a\n", None, "f")[0]
    assert "減って" in problems("a\nb\n", "a\n", "f")[0]
    assert "2 行目" in problems("a\nb\n", "a\nx\nc\n", "f")[0]


def test_duplicate_games_are_stopped():
    """同じ対局（山札・指し手・人の席が同じ）が2行あれば止める（局数・勝率の水増しを防ぐ）。"""
    from check_data_append_only import duplicates

    a = '{"deck":[1,2],"moves":[[0,1,0,-1]],"human_seat":0,"level":"strong"}'
    b = '{"deck":[1,2],"moves":[[0,1,0,-1]],"human_seat":1,"level":"strong"}'
    a2 = '{"deck":[1,2],"moves":[[0,1,0,-1]],"human_seat":0,"level":"standard","hints":2}'
    assert duplicates(f"{a}\n{b}\n", "f") == []
    got = duplicates(f"{a}\n{b}\n{a2}\n", "f")
    assert len(got) == 1 and "3 行目は 1 行目" in got[0]


def test_collected_games_have_no_duplicates():
    """いま集まっている棋譜に、同じ対局が2回入っていない。"""
    from check_data_append_only import PROTECTED, ROOT, duplicates

    for path in PROTECTED:
        p = ROOT / path
        assert duplicates(p.read_text(encoding="utf-8") if p.exists() else "", path) == []
