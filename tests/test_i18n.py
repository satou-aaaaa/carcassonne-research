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

from i18n import LOGICAL, MOVED, leftover, out_path, page_url

DOCS = ROOT / "docs"
# ページは論理名（"rules.html"）で数え、置き場所は out_path（"learn/rules.html"）で引く
JA_PAGES = sorted(LOGICAL)
EN_PAGES = JA_PAGES


def _html_files(root: Path) -> list[str]:
    skip = {"en", "human_games", "results"}
    return sorted(
        str(p.relative_to(root))
        for p in root.rglob("*.html")
        if p.relative_to(root).parts[0] not in skip
    )


def test_every_page_has_english_version():
    assert _html_files(DOCS) == _html_files(DOCS / "en")


def test_every_html_file_is_a_page_or_redirect():
    """docs/ の HTML は、LOGICAL のページか、古い置き場所の転送ページのどちらか（入れ忘れを防ぐ）。"""
    known = {out_path(p) for p in LOGICAL} | set(MOVED)
    assert set(_html_files(DOCS)) == known


@pytest.mark.parametrize("page", MOVED)
def test_old_urls_redirect(page):
    for d in (DOCS, DOCS / "en"):
        html = (d / page).read_text(encoding="utf-8")
        target = out_path(page)
        assert f'content="0; url={target}"' in html, (d, page)
        assert (d / target).exists(), (d, target)


@pytest.mark.parametrize("page", JA_PAGES)
def test_hreflang_reciprocal(page):
    for lang, path in (("ja", DOCS / out_path(page)), ("en", DOCS / "en" / out_path(page))):
        html = path.read_text(encoding="utf-8")
        assert f'<html lang="{lang}">' in html, path
        for lg in ("ja", "en"):
            assert f'hreflang="{lg}" href="{page_url(page, lg)}"' in html, (path, lg)
        assert f'hreflang="x-default" href="{page_url(page, "en")}"' in html, path
        assert 'data-lang="' in html, f"{path}: 言語の切り替えリンクがない"


@pytest.mark.parametrize("page", JA_PAGES)
def test_social_card(page):
    """SNS にリンクを貼るとカードが出る（全ページ・日英。画像は scripts/make_og_card.mjs）。"""
    for lang, path in (("ja", DOCS / out_path(page)), ("en", DOCS / "en" / out_path(page))):
        html = path.read_text(encoding="utf-8")
        assert '<meta name="twitter:card" content="summary_large_image">' in html, path
        assert f'<meta property="og:url" content="{page_url(page, lang)}">' in html, path
        img = re.search(r'<meta property="og:image" content="([^"]+)">', html)
        assert img, path
        local = DOCS / img.group(1).split("/carcassonne-research/", 1)[1]
        assert local.exists() and local.stat().st_size < 5_000_000, (path, local)
        title = re.search(r'<meta property="og:title" content="([^"]+)">', html)
        assert title and title.group(1).strip(), path
        if lang == "en":
            assert leftover(title.group(1)) == [], path


@pytest.mark.parametrize("page", EN_PAGES)
def test_no_japanese_left(page):
    assert leftover((DOCS / "en" / out_path(page)).read_text(encoding="utf-8")) == []


def test_no_japanese_left_in_english_scripts():
    for js in (DOCS / "en").glob("*.js"):
        assert leftover(js.read_text(encoding="utf-8"), "js") == [], js


@pytest.mark.skipif(shutil.which("node") is None, reason="node が無い")
@pytest.mark.parametrize("page", EN_PAGES)
def test_english_scripts_parse(page, tmp_path):
    html = (DOCS / "en" / out_path(page)).read_text(encoding="utf-8")
    scripts = re.findall(
        r"<script\b([^>]*)>(.*?)</script\b[^>]*>", html, flags=re.DOTALL | re.IGNORECASE
    )
    for i, (attrs, src) in enumerate(scripts):
        if "application/json" in attrs:  # データの埋め込みはスクリプトではない
            continue
        f = tmp_path / f"s{i}.js"
        f.write_text(src, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(f)], check=False, capture_output=True, text=True)
        assert r.returncode == 0, f"en/{page} のスクリプト{i}: {r.stderr[:400]}"
