"""「利用規約・データの扱い」ページ（docs/terms.html）を組み立てる。

    py scripts/build_terms_page.py

本文は web/terms_template.html に手で書く（送ってもらう棋譜の公開・利用への同意、削除しないこと、データのライセンス
CC BY 4.0、個人情報、免責、商標、変更の扱い）。英語版は対訳表 web/i18n/en/terms.json。
対戦ページの「棋譜を送る」とみんなの対局ページからリンクする。
"""

from __future__ import annotations

from pathlib import Path

from i18n import to_english_page, write_pair
from site_nav import NAV_CSS, nav_html, support_html

ROOT = Path(__file__).resolve().parents[1]
PAGE = "terms.html"


def main() -> None:
    tpl = (ROOT / "web" / "terms_template.html").read_text(encoding="utf-8")
    ja = (
        tpl.replace("__NAV_CSS__", NAV_CSS)
        .replace("__NAV__", nav_html(PAGE))
        .replace("__SUPPORT__", support_html())
    )
    en = to_english_page(ja, PAGE, "terms", nav_html(PAGE), nav_html(PAGE, "en"))
    # 英語版から見たデータと CC の日本語の説明は、英語の版へ
    en = (
        en.replace('href="human_games.json"', 'href="../human_games.json"')
        .replace("deed.ja", "deed.en")
        .replace("legalcode.ja", "legalcode.en")
    )
    write_pair(PAGE, ja, en)
    print("docs/terms.html と docs/en/terms.html を書き出しました")


if __name__ == "__main__":
    main()
