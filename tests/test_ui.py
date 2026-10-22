"""公開ページ（docs/*.html）の UI 点検を、スマホ幅とPC幅で行う（scripts/ui_check.mjs）。

横のはみ出し・小さすぎる押す場所・名前のないボタン・コンソールエラー・対戦ページの基本操作を見る。
node と Playwright（Chromium）が要る。無い環境では飛ばす。CI では test.yml の ui ジョブが入れて動かす。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


def _has_playwright() -> bool:
    if NODE is None:
        return False
    r = subprocess.run(
        [NODE, str(ROOT / "scripts" / "ui_check.mjs"), "--probe"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return r.returncode == 0


pytestmark = pytest.mark.skipif(not _has_playwright(), reason="node と Playwright が必要")


def test_pages_pass_ui_check():
    r = subprocess.run(
        [NODE, str(ROOT / "scripts" / "ui_check.mjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
