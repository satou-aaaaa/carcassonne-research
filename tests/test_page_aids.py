"""長いページを「ペライチ」にしない工夫（目次・「目次へ」ボタン・前後のページ）が全ページに入っていること。

ページを足したり見出しを増やしたりしても、i18n.write_pair → site_nav.enhance が自動で入れる。
ここでは公開中の docs/ を読んで、入れ忘れ・切れたリンクがないかを確かめる。
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from site_nav import NEXT_EXTRA, NO_ENHANCE, PATH, TOC_MIN, enhance, page_sections

PAGES = [
    p
    for d in (ROOT / "docs", ROOT / "docs" / "en")
    for p in sorted(d.glob("*.html"))
    if p.name not in NO_ENHANCE
]


@pytest.mark.parametrize("path", PAGES, ids=lambda p: str(p.relative_to(ROOT / "docs")))
def test_long_page_has_toc_and_links(path):
    html = path.read_text(encoding="utf-8")
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    if len(page_sections(html)) >= TOC_MIN:
        assert 'id="page-toc"' in html, f"{path.name}: 見出しが多いのに目次がない"
        assert 'class="totop"' in html, f"{path.name}: 「目次へ」ボタンがない"
    for href in re.findall(r'<nav class="pagetoc".*?</nav>', html, re.DOTALL):
        for a in re.findall(r'href="#([^"]+)"', href):
            assert a in ids, f"{path.name}: 目次の飛び先 #{a} がない"
    if path.name in PATH or path.name in NEXT_EXTRA:
        assert 'class="nextread"' in html, f"{path.name}: 前後のページへのリンクがない"
        for a in re.findall(r'<nav class="nextread".*?</nav>', html, re.DOTALL):
            for href in re.findall(r'href="([^"#]+)"', a):
                assert (path.parent / href).exists(), f"{path.name}: {href} がない"


def test_enhance_is_idempotent():
    html = (ROOT / "docs" / "stats.html").read_text(encoding="utf-8")
    assert enhance(html, "stats.html", "ja") == html
