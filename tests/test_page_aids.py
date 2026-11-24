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

from i18n import LOGICAL, out_path
from site_nav import NEXT_EXTRA, NO_ENHANCE, PATH, TOC_MIN, enhance, page_sections

PAGES = [
    (page, d / out_path(page))
    for d in (ROOT / "docs", ROOT / "docs" / "en")
    for page in sorted(LOGICAL)
    if page not in NO_ENHANCE
]


@pytest.mark.parametrize("page,path", PAGES, ids=lambda x: str(x).split("docs/")[-1])
def test_long_page_has_toc_and_links(page, path):
    html = path.read_text(encoding="utf-8")
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    if len(page_sections(html)) >= TOC_MIN:
        assert 'id="page-toc"' in html, f"{path.name}: 見出しが多いのに目次がない"
        assert 'class="totop"' in html, f"{path.name}: 「目次へ」ボタンがない"
    for href in re.findall(r'<nav class="pagetoc".*?</nav>', html, re.DOTALL):
        for a in re.findall(r'href="#([^"]+)"', href):
            assert a in ids, f"{path.name}: 目次の飛び先 #{a} がない"
    if page in PATH or page in NEXT_EXTRA:
        assert 'class="nextread"' in html, f"{path.name}: 前後のページへのリンクがない"
        for a in re.findall(r'<nav class="nextread".*?</nav>', html, re.DOTALL):
            for href in re.findall(r'href="([^"#]+)"', a):
                t = path.parent / href
                assert (t / "index.html" if href.endswith("/") else t).exists(), (
                    f"{path}: {href} がない"
                )


def test_enhance_is_idempotent():
    html = (ROOT / "docs" / out_path("stats.html")).read_text(encoding="utf-8")
    assert enhance(html, "stats.html", "ja") == html
