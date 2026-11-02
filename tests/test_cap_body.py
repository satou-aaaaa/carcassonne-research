"""scripts/cap_body.py（Issue・PR の本文を GitHub の上限に収める）を確かめる。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cap_body import DEFAULT_LIMIT, GITHUB_LIMIT, cap


def progress(rows: int) -> str:
    """selfplay の progress.md と同じ形の成績表（#110 のときは 890 行で 68700 文字）。"""
    head = "# 自己対戦ループの成績\n\n| 試行 | 日付 | 候補 vs チャンピオン | 得点差 | 判定 |\n|---|---|---|---|---|\n"
    body = "".join(
        f"| {i} | 2026-11-02 | 0.480（200局） | -0.40 | 不採用 |\n" for i in range(1, rows + 1)
    )
    return head + body


def test_short_body_is_unchanged() -> None:
    text = progress(10)
    assert cap(text) == text


def test_long_body_fits_and_keeps_head_and_newest_rows() -> None:
    text = progress(5000)
    assert len(text) > GITHUB_LIMIT
    out = cap(text, note="全文は progress.md")
    assert len(out) <= DEFAULT_LIMIT < GITHUB_LIMIT
    assert out.startswith("# 自己対戦ループの成績")
    assert "| 試行 |" in out
    assert out.rstrip().endswith("| 5000 | 2026-11-02 | 0.480（200局） | -0.40 | 不採用 |")
    assert "途中を省きました。全文は progress.md" in out


def test_cli_rewrites_file(tmp_path: Path) -> None:
    f = tmp_path / "body.md"
    f.write_text(progress(5000), encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "cap_body.py"), str(f)], check=True)
    assert len(f.read_text(encoding="utf-8")) <= DEFAULT_LIMIT
