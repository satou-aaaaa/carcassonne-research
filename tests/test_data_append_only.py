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
