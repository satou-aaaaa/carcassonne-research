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
    ("stats.html", "データで見る"),
    ("games.html", "みんなの対局"),
    ("play.html", "AIと対戦"),
]
HOME = {"ja": "カルカソンヌ入門", "en": "Carcassonne Primer"}
PAGES_EN = [
    ("index.html", "Home"),
    ("rules.html", "Rules"),
    ("strategy.html", "Strategy"),
    ("ai_tips.html", "Lessons from the AI"),
    ("quiz.html", "Next-Move Quiz"),
    ("stats.html", "By the Numbers"),
    ("games.html", "Community Games"),
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
/* 共通: ページ下の支援リンク（Ko-fi）。目立ちすぎないよう枠線だけのボタンにする */
.support { margin-top: 40px; padding-top: 14px; border-top: 1px solid var(--line); font-size: 13.5px; color: var(--muted); display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
.support a.kofi { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 16px; border: 1px solid var(--line); border-radius: 999px; background: var(--paper); color: var(--ink); text-decoration: none; font-weight: 600; }
.support a.kofi:hover, .support a.kofi:focus-visible { border-color: var(--field); }
"""

# 作者の Ko-fi ページ（2026-11-03 satou さん設定）。外部スクリプト・外部画像は読み込まない
KOFI_URL = "https://ko-fi.com/satouaaaaa"


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


def support_html(lang: str = "ja") -> str:
    """ページ下に置く支援リンク。全ページで同じものを使う（docs/index.html・web/play.html は手で合わせる）。"""
    text, label = (
        ("このサイトが役に立ったら、作者を応援できます。", "Ko-fiで応援する")
        if lang == "ja"
        else ("If this site helped you, you can support the author.", "Support on Ko-fi")
    )
    return (
        f'<div class="support">{text}'
        f'<a class="kofi" href="{KOFI_URL}" target="_blank" rel="noopener">'
        f'<span aria-hidden="true">☕</span>{label}</a></div>'
    )


# ---------- 長いページを「ペライチ」にしない工夫（2026-11-24） ----------
# i18n.write_pair が全ページに自動でかける（新しいページを足しても入れ忘れない）。
# 1. 目次: 見出し（<section id=…><h2>）が4つ以上あるページに、ページ上部の目次を作る（手書きの目次があればそれを使う）。
# 2. 「目次へ」ボタン: 目次のあるページで、1画面以上スクロールしたら右下に出す。
# 3. 「次に読む」: ページの下に、学ぶ順の前後のページへのリンクを置く。
# 参考: NN/g「Back-to-Top Button Design Guidelines」（4画面を超える長いページに、スクロール後に右下へ出す）
#   https://www.nngroup.com/articles/back-to-top/ と「In-Page Links」 https://www.nngroup.com/articles/in-page-links/

import html as _html
import re as _re

TOC_MIN = 4  # 目次を作る見出しの数
NO_ENHANCE = {"play.html", "index.html"}  # 対戦ページは画面そのものが道具なので入れない

# 学ぶ順（前後のリンク）。ほかのページはおすすめの次のページだけ出す
PATH = ["rules.html", "strategy.html", "ai_tips.html", "quiz.html", "play.html"]
NEXT_EXTRA = {"stats.html": "games.html", "games.html": "play.html", "terms.html": "games.html"}
BLURB = {
    "ja": {
        "rules.html": "手番の流れと点の数え方を、図で順に覚える。",
        "strategy.html": "何を考えて置くか。序盤・中盤・終盤の方針とよくある失敗。",
        "ai_tips.html": "強いAIの打ち方を数字で確かめたコツ。",
        "quiz.html": "この局面ならどこに置く？AIの答えつきの練習問題。",
        "play.html": "ブラウザでそのまま強いAIと対戦する。",
        "stats.html": "先手有利・得点源・逆転など、AIどうしの対局の集計。",
        "games.html": "人とAIの対局を再生して、悪手の傾向を見る。",
    },
    "en": {
        "rules.html": "Learn turn flow and scoring step by step, with diagrams.",
        "strategy.html": "What to think about: plans for each phase and common mistakes.",
        "ai_tips.html": "How the strong AI plays, checked with numbers.",
        "quiz.html": "Where would you place it? Practice positions with the AI's answer.",
        "play.html": "Play the strong AI right in your browser.",
        "stats.html": "First-player edge, scoring sources and comebacks, from AI games.",
        "games.html": "Replay human-vs-AI games and see common mistakes.",
    },
}
WORDS = {
    "ja": {"toc": "このページの目次", "top": "目次へ", "next": "次へ", "prev": "前へ",
           "nav": "前後のページ"},
    "en": {"toc": "On this page", "top": "Contents", "next": "Next", "prev": "Previous",
           "nav": "Previous and next pages"},
}  # fmt: skip

ENHANCE_CSS = """<style id="page-aids">
nav.pagetoc { margin: 18px 0 8px; padding: 12px 0; border-block: 1px solid var(--line); }
nav.pagetoc .h { font-size: 12.5px; font-weight: 700; letter-spacing: .08em; color: var(--muted); margin: 0 0 8px; }
nav.pagetoc ol { display: flex; flex-wrap: wrap; gap: 6px 8px; margin: 0; padding: 0; list-style: none; font-size: 14px; }
nav.pagetoc a { display: inline-flex; align-items: center; min-height: 32px; padding: 2px 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--paper); color: var(--ink); text-decoration: none; }
nav.pagetoc a:hover, nav.pagetoc a:focus-visible { border-color: var(--field); outline: none; }
@media (pointer: coarse) { nav.pagetoc a { min-height: 44px; } }
section[id], [id="page-toc"] { scroll-margin-top: 12px; }
a.totop { position: fixed; right: max(16px, env(safe-area-inset-right)); bottom: max(16px, env(safe-area-inset-bottom)); z-index: 50; display: inline-flex; align-items: center; gap: 4px; min-height: 44px; padding: 0 16px; border: 1px solid var(--line); border-radius: 999px; background: var(--paper); color: var(--ink); font-size: 14px; font-weight: 600; text-decoration: none; box-shadow: 0 2px 10px rgba(0,0,0,.15); opacity: 0; visibility: hidden; transform: translateY(8px); transition: opacity .2s, transform .2s, visibility .2s; }
a.totop.on { opacity: 1; visibility: visible; transform: none; }
a.totop:hover, a.totop:focus-visible { border-color: var(--field); outline: none; }
@media print { a.totop { display: none; } }
@media (prefers-reduced-motion: reduce) { a.totop { transition: none; } html { scroll-behavior: auto; } }
nav.nextread { margin-top: 40px; display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
nav.nextread a { display: block; padding: 14px 16px; border: 1px solid var(--line); border-radius: 12px; background: var(--paper); color: var(--ink); text-decoration: none; }
nav.nextread a:hover, nav.nextread a:focus-visible { border-color: var(--field); outline: none; }
nav.nextread .k { display: block; font-size: 12.5px; font-weight: 700; letter-spacing: .06em; color: var(--muted); }
nav.nextread .t { display: block; font-size: 17px; font-weight: 700; margin: 2px 0 4px; }
nav.nextread .d { display: block; font-size: 14px; color: var(--muted); }
nav.nextread a.next { border-color: var(--field); }
</style>"""

# 目次のあるページだけ: 1画面以上下がったら「目次へ」を出す（JS が無くてもリンクとして動く）
TOTOP_JS = (
    "<script>(function(){var b=document.querySelector('a.totop');if(!b)return;"
    "function f(){b.classList.toggle('on',window.scrollY>window.innerHeight)}"
    "addEventListener('scroll',f,{passive:true});f()})()</script>"
)

_SECTION_H2 = _re.compile(
    r'<section\b[^>]*\bid="([^"]+)"[^>]*>\s*<h2\b[^>]*>(.*?)</h2>', _re.DOTALL
)


def _plain(fragment: str) -> str:
    """見出しの HTML から文字だけにする（番号の <span class="no">1</span> は「1. 」にする）。"""
    fragment = _re.sub(r'<span class="no">\s*(\d+)\s*</span>', r"\1. ", fragment)
    text = _html.unescape(_re.sub(r"<[^>]+>", "", fragment))
    return _html.escape(" ".join(text.split()), quote=False)


def page_sections(html: str) -> list[tuple[str, str]]:
    """(id, 見出しの文字) の一覧。"""
    return [(sid, _plain(h)) for sid, h in _SECTION_H2.findall(html)]


def _title(page: str, lang: str) -> str:
    return dict(PAGES if lang == "ja" else PAGES_EN)[page]


def _card(page: str, lang: str, key: str, cls: str) -> str:
    w = WORDS[lang]
    return (
        f'<a class="{cls}" href="{page}"><span class="k">{w[key]}</span>'
        f'<span class="t">{_title(page, lang)}</span><span class="d">{BLURB[lang][page]}</span></a>'
    )


def next_read_html(page: str, lang: str) -> str:
    """ページ下の「次に読む」。学ぶ順の前後（次を目立たせる）。"""
    cards = []
    if page in PATH:
        i = PATH.index(page)
        if i > 0:
            cards.append(_card(PATH[i - 1], lang, "prev", "prev"))
        if i + 1 < len(PATH):
            cards.append(_card(PATH[i + 1], lang, "next", "next"))
    elif page in NEXT_EXTRA:
        cards.append(_card(NEXT_EXTRA[page], lang, "next", "next"))
    if not cards:
        return ""
    aria = WORDS[lang]["nav"]
    return f'<nav class="nextread" aria-label="{aria}">' + "".join(cards) + "</nav>"


def enhance(html: str, page: str, lang: str) -> str:
    """長いページに目次・「目次へ」ボタン・「次に読む」を足す。何度かけても同じ結果になる。"""
    if page in NO_ENHANCE or 'id="page-aids"' in html:
        return html
    w = WORDS[lang]
    secs = page_sections(html)
    has_toc = False
    m = _re.search(r'<(nav|ul|ol)\b([^>]*)\bclass="toc"', html)
    if m:  # 手書きの目次に飛び先の id を付ける
        has_toc = True
        if "id=" not in m.group(2):
            html = html[: m.end()] + ' id="page-toc"' + html[m.end() :]
    elif len(secs) >= TOC_MIN:
        if html.count("</header>") != 1:
            raise SystemExit(f"{page}: 目次を入れる </header> が1つではありません")
        items = "".join(f'<li><a href="#{sid}">{t}</a></li>' for sid, t in secs)
        toc = (
            f'<nav class="pagetoc" id="page-toc" aria-labelledby="page-toc-h">'
            f'<p class="h" id="page-toc-h">{w["toc"]}</p><ol>{items}</ol></nav>'
        )
        html = html.replace("</header>", "</header>\n" + toc, 1)
        has_toc = True
    nr = next_read_html(page, lang)
    if nr:
        if '<div class="support">' not in html:
            raise SystemExit(f"{page}: 「次に読む」を入れる支援リンクが見つかりません")
        html = html.replace('<div class="support">', nr + '\n<div class="support">', 1)
    if has_toc:
        btn = f'<a class="totop" href="#page-toc"><span aria-hidden="true">↑</span>{w["top"]}</a>'
        if html.count("</body>") != 1:
            raise SystemExit(f"{page}: </body> が1つではありません")
        html = html.replace("</body>", btn + TOTOP_JS + "</body>", 1)
    if html.count("</head>") != 1:
        raise SystemExit(f"{page}: </head> が1つではありません")
    return html.replace("</head>", ENHANCE_CSS + "</head>", 1)
