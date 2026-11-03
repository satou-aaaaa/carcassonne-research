"""公開ページの英語版（docs/en/）の点検。

- 日本語ページと英語ページが1対1でそろい、互いに hreflang で指し合っている（Google の決まり）
- 英語ページに日本語の文が残っていない（lang="ja" の切り替えリンクとコメントは除く）
- 英語ページのスクリプトが文法エラーにならない（訳文の引用符でスクリプトが壊れるのを防ぐ。node が要る）
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from i18n import leftover, page_url

DOCS = ROOT / "docs"
JA_PAGES = sorted(p.name for p in DOCS.glob("*.html"))
EN_PAGES = sorted(p.name for p in (DOCS / "en").glob("*.html"))


def test_every_page_has_english_version():
    assert JA_PAGES == EN_PAGES


@pytest.mark.parametrize("page", JA_PAGES)
def test_hreflang_reciprocal(page):
    for lang, path in (("ja", DOCS / page), ("en", DOCS / "en" / page)):
        html = path.read_text(encoding="utf-8")
        assert f'<html lang="{lang}">' in html, path
        for lg in ("ja", "en"):
            assert f'hreflang="{lg}" href="{page_url(page, lg)}"' in html, (path, lg)
        assert f'hreflang="x-default" href="{page_url(page, "en")}"' in html, path
        assert 'data-lang="' in html, f"{path}: 言語の切り替えリンクがない"


@pytest.mark.parametrize("page", EN_PAGES)
def test_no_japanese_left(page):
    assert leftover((DOCS / "en" / page).read_text(encoding="utf-8")) == []


def test_no_japanese_left_in_english_scripts():
    for js in (DOCS / "en").glob("*.js"):
        assert leftover(js.read_text(encoding="utf-8"), "js") == [], js


@pytest.mark.skipif(shutil.which("node") is None, reason="node が無い")
@pytest.mark.parametrize("page", EN_PAGES)
def test_english_scripts_parse(page, tmp_path):
    html = (DOCS / "en" / page).read_text(encoding="utf-8")
    for i, src in enumerate(re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL)):
        f = tmp_path / f"s{i}.js"
        f.write_text(src, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(f)], check=False, capture_output=True, text=True)
        assert r.returncode == 0, f"en/{page} のスクリプト{i}: {r.stderr[:400]}"
