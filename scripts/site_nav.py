"""公開ページ（docs/）の共通ナビゲーション。各ページの組み立てスクリプトが差し込む。

ページは docs/ 直下に並べる（GitHub Pages で docs/ を公開する想定）。
CSS は各ページの色トークン（--paper, --ink, --muted, --line, --field）を使う。
"""

from __future__ import annotations

from i18n import lang_link

PAGES = [
    ("index.html", "トップ"),
    ("rules.html", "ルール入門"),
    ("strategy.html", "戦略ガイド"),
    ("ai_tips.html", "強いAIのコツ"),
    ("quiz.html", "次の一手クイズ"),
    ("play.html", "AIと対戦"),
]
HOME = {"ja": "カルカソンヌ入門", "en": "Carcassonne Primer"}
PAGES_EN = [
    ("index.html", "Home"),
    ("rules.html", "Rules"),
    ("strategy.html", "Strategy"),
    ("ai_tips.html", "Lessons from the AI"),
    ("quiz.html", "Next-Move Quiz"),
    ("play.html", "Play the AI"),
]

NAV_CSS = """
nav.site { display: flex; flex-wrap: wrap; gap: 4px 6px; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--line); font-size: 14px; }
nav.site .home { font-weight: 700; margin-right: 8px; color: var(--ink); text-decoration: none; }
nav.site a.p { color: var(--muted); text-decoration: none; padding: 3px 10px; border-radius: 999px; }
nav.site a.p:hover, nav.site a.p:focus-visible { color: var(--ink); background: var(--paper); outline: none; }
nav.site a.p[aria-current="page"] { color: var(--paper); background: var(--field); }
nav.site a.lang { margin-left: auto; border: 1px solid var(--line); }
@media (pointer: coarse) { nav.site a { min-height: 44px; display: inline-flex; align-items: center; } }
/* 共通: 見出しを語の切れ目で折り返す・開閉の見出しを押しやすく */
h1, h2, h3 { word-break: auto-phrase; }
summary { padding-block: 6px; }
"""


def nav_html(current: str, lang: str = "ja") -> str:
    """current はそのページのファイル名（例 "rules.html"）。lang は "ja" か "en"。
    最後に、もう一方の言語の同じページへのリンクを置く。"""
    pages = PAGES if lang == "ja" else PAGES_EN
    aria = "サイト内のページ" if lang == "ja" else "Site pages"
    links = []
    for href, label in pages[1:]:
        cur = ' aria-current="page"' if href == current else ""
        links.append(f'<a class="p" href="{href}"{cur}>{label}</a>')
    return (
        f'<nav class="site" aria-label="{aria}">'
        f'<a class="home" href="index.html">{HOME[lang]}</a>'
        + "".join(links)
        + lang_link(current, lang, "p lang")
        + "</nav>"
    )
