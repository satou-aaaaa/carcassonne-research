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


def page_url(page: str, lang: str) -> str:
    """公開URL。page は "rules.html" など。"""
    name = "" if page == "index.html" else page
    return SITE + ("en/" if lang == "en" else "") + name


def rel_href(page: str, from_lang: str, to_lang: str) -> str:
    """from_lang のページから見た、to_lang の同じページへの相対リンク。"""
    if from_lang == to_lang:
        return page
    return f"en/{page}" if to_lang == "en" else f"../{page}"


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
        text = re.sub(r"<style\b.*?</style>", "", text, flags=re.DOTALL)
        segs = []
        pos = 0
        for m in re.finditer(r"(<script\b[^>]*>)(.*?)(</script>)", text, flags=re.DOTALL):
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
    text = re.sub(r'<(\w+)\b[^>]*\blang="ja"[^>]*>.*?</\1>', "", text, flags=re.DOTALL)
    text = re.sub(r"<style\b.*?</style>", "", text, flags=re.DOTALL)
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
    return translate(html, name)


def add_head(html: str, page: str, lang: str) -> str:
    if html.count("</head>") != 1:
        raise SystemExit(f"{page}: </head> が1つではありません")
    return html.replace("</head>", lang_head(page, lang) + "</head>", 1)


def write_pair(page: str, html_ja: str, html_en: str) -> None:
    """docs/<page> と docs/en/<page> を書き出す。"""
    if leftover(html_en):
        raise SystemExit(f"en/{page} に日本語が残っています: {leftover(html_en)[:5]}")
    (ROOT / "docs").joinpath(page).write_text(add_head(html_ja, page, "ja"), encoding="utf-8")
    en = ROOT / "docs" / "en"
    en.mkdir(exist_ok=True)
    en.joinpath(page).write_text(add_head(html_en, page, "en"), encoding="utf-8")


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
