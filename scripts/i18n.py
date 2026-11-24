"""公開ページの多言語化（日本語＋英語）。

- 日本語ページは docs/、英語ページは docs/en/ に同じファイル名で置く（言語ごとに別のURL）。
- 英語ページは、日本語ページ（またはその元のテンプレート）の文を、対訳表 web/i18n/en/<名前>.json で
  置き換えて作る。対訳表は {日本語: 英語}。数値などが変わる部分は、組み立てスクリプトが英語の文を直接作る。
- 書き出す前に、英語ページに日本語が残っていないか確かめ、残っていたら止める（訳し漏れを公開しない）。
  対訳表にあって元の文に無い項目も止める（元の文が変わったのに訳が古いまま、を防ぐ）。

訳し漏れの一覧（対訳表に足す項目のひな形）を出す:
    py scripts/i18n.py todo rules docs/rules.html
    py scripts/i18n.py todo play web/play.html

言語の切り替え（各ページの <head> に入れる。lang_head）:
- 初めて来た人は、ブラウザの言語設定（navigator.languages の先頭）が日本語なら日本語、それ以外は英語のページへ移す。
- 切り替えのリンクを押すと、その言語を localStorage に覚え、以後はそちらを出す。
- 検索エンジンのクローラーは移さない（Google は言語による自動転送を避けるよう勧めているため）。
  代わりに hreflang で各言語版の対応を伝える。
  https://developers.google.com/search/docs/specialty/international/managing-multi-regional-sites
  https://developers.google.com/search/docs/specialty/international/localized-versions
"""

from __future__ import annotations

import json
import posixpath
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "web" / "i18n" / "en"
SITE = "https://satou-aaaaa.github.io/carcassonne-research/"
LANGS = ("ja", "en")
STORE_KEY = "site-lang"

# 日本語の文字（ひらがな・カタカナ・漢字・全角の記号と英数字）
JA = re.compile(r"[　-〿぀-ヿ㐀-䶿一-鿿！-｠～]")
INLINE = {
    "a", "abbr", "b", "br", "code", "em", "i", "kbd", "mark", "small", "span", "strong", "sub",
    "sup", "u", "wbr", "s", "q", "time", "var",
}  # fmt: skip


# ---------- ページの置き場所（2026-11-24 構造の整理） ----------
# サイトは「講座」learn/・「研究」research/・「対戦」play.html の3部。組み立てスクリプトとテンプレートは
# 今までどおり "rules.html" のような論理名で書き、書き出すときに relocate() で実際の置き場所への相対リンクに直す。
# 古い置き場所（docs/rules.html など）は scripts/build_redirects.py が転送ページにする。
LOC = {
    "learn/index.html": "learn/index.html",
    "rules.html": "learn/rules.html",
    "strategy.html": "learn/strategy.html",
    "ai_tips.html": "learn/ai_tips.html",
    "quiz.html": "learn/quiz.html",
    "research/index.html": "research/index.html",
    "stats.html": "research/stats.html",
    "games.html": "research/games.html",
}
MOVED = [k for k, v in LOC.items() if k != v]  # 古い URL に転送ページを置くもの
LOGICAL = ["index.html", "play.html", "terms.html", *LOC]
# ページから相対で読むデータ（置き場所が深くなったら ../ を足す）
ASSETS = ("human_games/", "human_games.json", "human_findings.json")
_LINK = re.compile(
    r"(?<=[\"'`])("
    + "|".join(re.escape(x) for x in sorted(LOGICAL, key=len, reverse=True))
    + r")(?=[#?\"'`])"
)
_ASSET = re.compile(r"(?<=[\"'`])((?:\.\./)*)(" + "|".join(re.escape(x) for x in ASSETS) + ")")


def out_path(page: str) -> str:
    """論理名（"rules.html"）から、言語の根からの置き場所（"learn/rules.html"）。"""
    return LOC.get(page, page)


def _rel(target: str, start_dir: str) -> str:
    """start_dir（"" か "learn"）から target（"learn/index.html" など）への相対リンク。index.html は省く。"""
    r = posixpath.relpath(target, start_dir or ".")
    if r == "index.html":
        return "./"
    if r.endswith("/index.html"):
        return r[: -len("index.html")]
    return r


def page_link(target: str, from_page: str) -> str:
    """同じ言語の中で、from_page から target（どちらも論理名）への相対リンク。"""
    return _rel(out_path(target), posixpath.dirname(out_path(from_page)))


def relocate(html: str, page: str) -> str:
    """論理名で書いたページ間リンクとデータの読み込み先を、page の実際の置き場所からの相対リンクに直す。"""
    html = _LINK.sub(lambda m: page_link(m.group(1), page), html)
    depth = out_path(page).count("/")
    if depth:
        html = _ASSET.sub(lambda m: "../" * depth + m.group(1) + m.group(2), html)
    return html


def page_url(page: str, lang: str) -> str:
    """公開URL。page は "rules.html" などの論理名。"""
    name = out_path(page)
    if name == "index.html" or name.endswith("/index.html"):
        name = name[: -len("index.html")]
    return SITE + ("en/" if lang == "en" else "") + name


def rel_href(page: str, from_lang: str, to_lang: str) -> str:
    """from_lang のページから見た、to_lang の同じページへの相対リンク。"""
    path = out_path(page)
    here = ("en/" if from_lang == "en" else "") + path
    there = ("en/" if to_lang == "en" else "") + path
    return _rel(there, posixpath.dirname(here))


def lang_link(page: str, lang: str, cls: str = "") -> str:
    """もう一方の言語へ切り替えるリンク。"""
    other = "en" if lang == "ja" else "ja"
    label = "English" if other == "en" else "日本語"
    title = "日本語に切り替え" if other == "ja" else "Switch to English"
    c = f' class="{cls}"' if cls else ""
    return (
        f'<a{c} href="{rel_href(page, lang, other)}" hreflang="{other}" lang="{other}"'
        f' data-lang="{other}" title="{title}">{label}</a>'
    )


def lang_head(page: str, lang: str) -> str:
    """<head> に入れる: 各言語版の対応（hreflang）と、言語の自動切り替え・選択の保存。"""
    alts = "".join(
        f'<link rel="alternate" hreflang="{lg}" href="{page_url(page, lg)}">' for lg in LANGS
    )
    alts += f'<link rel="alternate" hreflang="x-default" href="{page_url(page, "en")}">'
    other = "en" if lang == "ja" else "ja"
    js = (
        "(function(){var K=__K__,cur=__CUR__,alt=__ALT__,s=null;"
        "try{s=localStorage.getItem(K)}catch(e){}"
        "if(!/bot|crawl|spider|slurp|lighthouse/i.test(navigator.userAgent)){"
        "var l=(navigator.languages&&navigator.languages[0])||navigator.language||'';"
        "var want=s||(/^ja\\b/i.test(l)?'ja':'en');"
        "if(want!==cur){location.replace(alt+location.search+location.hash);return}}"
        "document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('a[data-lang]');"
        "if(a)try{localStorage.setItem(K,a.getAttribute('data-lang'))}catch(e){}})})();"
    )
    js = (
        js.replace("__K__", json.dumps(STORE_KEY))
        .replace("__CUR__", json.dumps(lang))
        .replace("__ALT__", json.dumps(rel_href(page, lang, other)))
    )
    return f"{alts}\n<script>{js}</script>\n"


# ---------- 文の切り出し ----------


def _strip_comments(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"(?<![:\\\"'\w/])//[^\n]*", "", text)


def _js_segments(js: str) -> list[str]:
    """JavaScript の中の日本語（引用符・<>で区切った文の単位）。"""
    out = []
    for m in re.finditer(r"[^\"'`<>\n]+", _strip_comments(js)):
        s = m.group(0).strip()
        if JA.search(s):
            out.append(s)
    return out


def _html_segments(html: str) -> list[str]:
    """HTML の中の日本語。インラインのタグ（b, a, span など）はまとめて1つの文にする。"""
    out: list[str] = []
    group: list[str] = []

    def flush():
        s = "".join(group).strip()
        if JA.search(s):
            # 前後のインラインタグだけの部分は外す（中身の文だけを対訳の単位にする）
            out.append(s)
        group.clear()

    for tok in re.findall(r"<[^>]*>|[^<]+", html):
        if tok.startswith("<"):
            m = re.match(r"</?\s*([a-zA-Z0-9-]+)", tok)
            name = m.group(1).lower() if m else ""
            if name in INLINE:
                group.append(tok)
                continue
            flush()
            for v in re.findall(r'"([^"]*)"', tok):
                if JA.search(v):
                    out.append(v)
        else:
            group.append(tok)
    flush()
    return out


def segments(text: str, kind: str = "html") -> list[str]:
    """訳す単位の一覧（出てくる順・重複なし）。kind は "html" か "js"。"""
    if kind == "js":
        segs = _js_segments(text)
    else:
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        text = re.sub(r"<style\b.*?</style\b[^>]*>", "", text, flags=re.DOTALL | re.IGNORECASE)
        segs = []
        pos = 0
        for m in re.finditer(
            r"(<script\b[^>]*>)(.*?)(</script\b[^>]*>)", text, flags=re.DOTALL | re.IGNORECASE
        ):
            segs += _html_segments(text[pos : m.start()] + m.group(1))
            segs += _js_segments(m.group(2))
            pos = m.end(2)
        segs += _html_segments(text[pos:])
    return list(dict.fromkeys(segs))


# ---------- 置き換えと検査 ----------


def load_table(name: str) -> dict[str, str]:
    p = TABLES / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def leftover(text: str, kind: str = "html") -> list[str]:
    """英語ページに残った日本語（コメントと lang="ja" の要素は除く）。"""
    text = re.sub(
        r'<(\w+)\b[^>]*\blang="ja"[^>]*>.*?</\1>', "", text, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(r"<style\b.*?</style\b[^>]*>", "", text, flags=re.DOTALL | re.IGNORECASE)
    if not JA.search(_strip_comments(text)):
        return []
    segs = segments(text, kind)
    return segs or [s for s in _strip_comments(text).splitlines() if JA.search(s)][:20]


def translate(text: str, name: str, kind: str = "html", extra: dict | None = None) -> str:
    """対訳表 name で text を英語にする。訳し漏れ・古い訳があれば止める。"""
    table = {**load_table(name), **(extra or {})}
    unused = [k for k in table if k not in text]
    for k in sorted(table, key=len, reverse=True):
        text = text.replace(k, table[k])
    left = leftover(text, kind)
    msgs = []
    if left:
        todo = json.dumps({s: "" for s in left}, ensure_ascii=False, indent=1)
        msgs.append(
            f"英語ページに日本語が残っています。web/i18n/en/{name}.json に訳を足してください:\n{todo}"
        )
    if unused:
        msgs.append(
            f"web/i18n/en/{name}.json に、元の文に無い項目があります（元の文が変わった？）:\n  "
            + "\n  ".join(unused[:20])
        )
    if msgs:
        raise SystemExit("\n".join(msgs))
    return text


def to_english_page(html: str, page: str, name: str, nav_ja: str = "", nav_en: str = "") -> str:
    """日本語ページの HTML を英語ページにする（lang・ナビ・対訳表・相対パス）。"""
    if nav_ja:
        if nav_ja not in html:
            raise SystemExit(f"{page}: ナビが見つかりません")
        html = html.replace(nav_ja, nav_en)
    html = html.replace('<html lang="ja">', '<html lang="en">', 1)
    from site_nav import support_html  # site_nav が i18n を使うので、ここで読み込む

    html = html.replace(support_html("ja"), support_html("en"))
    return translate(html, name)


def add_head(html: str, page: str, lang: str) -> str:
    if html.count("</head>") != 1:
        raise SystemExit(f"{page}: </head> が1つではありません")
    return html.replace("</head>", lang_head(page, lang) + "</head>", 1)


def write_pair(page: str, html_ja: str, html_en: str) -> None:
    """docs/<置き場所> と docs/en/<置き場所> を書き出す（置き場所は out_path）。"""
    from site_nav import enhance  # 長いページの目次・「目次へ」・「次に読む」（全ページ共通）

    html_ja, html_en = enhance(html_ja, page, "ja"), enhance(html_en, page, "en")
    if leftover(html_en):
        raise SystemExit(f"en/{page} に日本語が残っています: {leftover(html_en)[:5]}")
    html_ja, html_en = relocate(html_ja, page), relocate(html_en, page)
    for root, html, lang in ((ROOT / "docs", html_ja, "ja"), (ROOT / "docs" / "en", html_en, "en")):
        out = root / out_path(page)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(add_head(html, page, lang), encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 4 or sys.argv[1] != "todo":
        raise SystemExit(__doc__)
    name, path = sys.argv[2], Path(sys.argv[3])
    kind = "js" if path.suffix == ".js" else "html"
    table = load_table(name)
    segs = [s for s in segments(path.read_text(encoding="utf-8"), kind) if s not in table]
    print(json.dumps({s: "" for s in segs}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
