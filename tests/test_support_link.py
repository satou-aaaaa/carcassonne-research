"""公開ページすべてに Ko-fi の支援リンクがあること（ページを足したときの入れ忘れを防ぐ）。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from site_nav import KOFI_URL


def test_every_page_links_kofi():
    pages = sorted((ROOT / "docs").glob("*.html"))
    assert pages
    missing = [p.name for p in pages if f'href="{KOFI_URL}"' not in p.read_text(encoding="utf-8")]
    assert not missing, (
        f"Ko-fi の支援リンクが無いページ: {missing}（site_nav.support_html を差し込む）"
    )
