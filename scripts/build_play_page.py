"""ブラウザだけでAIと対戦できる公開ページ（docs/play.html）を作る。

    py scripts/build_play_page.py

AIは Python 版（src/carcassonne/fast*.py）を JavaScript に移したもの（web/carcassonne_engine.js）で、
ブラウザの中で計算する（サーバー不要）。画面はローカル対戦用の web/play.html を共用し、
サーバーへの問い合わせの代わりに web/play_local.js がブラウザ内で対局を進める。

書き出すもの:
- docs/play.html            web/play.html にブラウザ内対局用のスクリプトを差し込んだもの
- docs/play_data.js         タイル定義・エンジン用テーブル・評価関数の重み
- docs/carcassonne_engine.js, docs/play_features.js, docs/play_local.js, docs/play_worker.js, docs/tile_art.js
                            web/ からの複写
- docs/en/ に同じものの英語版（画面の文は web/i18n/en/play.json・play_local.json で訳す）

評価関数は EVAL（自己対戦ループの最新チャンピオンの複写）を使う。models/best.json は追わない
（JavaScript 版は線形の評価関数しか扱えないため）。新しいチャンピオンが採用されると、
.github/workflows/selfplay.yml が EVAL と CHAMPION を差し替えてこのスクリプトで作り直し、main に入れる。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from i18n import lang_link, leftover, translate, write_pair

from carcassonne.fast import build_tables
from carcassonne.fast_eval import NF, load_eval
from carcassonne.tiles import load_tileset
from carcassonne.webplay import tile_library

DOCS = ROOT / "docs"
WEB = ROOT / "web"
EVAL = "models/eval_champion.npy"  # 自己対戦ループの最新チャンピオン（selfplay-state の loop/models/ から複写）
CHAMPION = "models/eval_champion.json"  # その世代名・採用日（画面の表示用）
COPIES = [
    "carcassonne_engine.js",
    "play_features.js",
    "play_local.js",
    "play_worker.js",
    "tile_art.js",
]
TABLE_NAMES = [
    "edge", "npc", "pkind", "psides", "phalves", "ppen", "padj", "cadj",
    "sidepc", "halfpc", "mpiece", "vbase", "nvar",
]  # fmt: skip
# 強さ（ブラウザ版）。sims・depth は Python 版の webplay.make_agent と同じ
LEVELS = {
    "strong": {
        "label": "最強（自己対戦で学んだ最新AI。1手1〜数秒）",
        "sims": 12000,
        "depth": 10,
    },
    "standard": {"label": "標準（探索を減らした版。すぐ指す）", "sims": 2000, "depth": 0},
    "greedy": {"label": "やさしい（目先の点だけを見る練習相手）"},
}
LABELS_EN = {
    "strong": "Strongest (latest self-play AI {name}{adopted}; 1 to a few seconds per move)",
    "standard": "Standard (lighter search; moves instantly)",
    "greedy": "Easy (practice opponent that only looks at immediate points)",
}
INJECT = """<style>.server-only { display: none !important; } .local-only { display: block !important; }</style>
<script src="play_data.js"></script>
<script src="carcassonne_engine.js"></script>
<script src="play_local.js"></script>
"""


def play_data(lang: str = "ja") -> dict:
    ts = load_tileset()
    T = build_tables(ts)
    w, mode = load_eval(str(ROOT / EVAL))
    if mode != 1 or len(w) != NF:
        raise SystemExit(f"{EVAL} は線形の評価関数ではありません（JavaScript 版は線形のみ対応）")
    info = json.loads((ROOT / CHAMPION).read_text(encoding="utf-8"))
    levels = json.loads(json.dumps(LEVELS))
    adopted = f"、{info['date']} 採用" if info.get("date") else ""
    levels["strong"]["label"] = (
        f"最強（自己対戦で学んだ最新AI {info['name']}{adopted}。1手1〜数秒）"
    )
    if lang == "en":
        adopted = f", adopted {info['date']}" if info.get("date") else ""
        for k, v in LABELS_EN.items():
            levels[k]["label"] = v.format(name=info["name"], adopted=adopted)
    tables = {name: arr.reshape(-1).tolist() for name, arr in zip(TABLE_NAMES, T)}
    return {
        "tables": {
            **tables,
            "P": int(T[2].shape[1]),
            "start": ts.start,
            "counts": [t.count for t in ts.types],
        },
        "tiles": tile_library(),
        "eval": {"path": EVAL, "champion": info, "w": [round(float(x), 12) for x in w]},
        "levels": levels,
    }


def write_scripts(out: Path, lang: str) -> None:
    out.mkdir(exist_ok=True)
    data = json.dumps(play_data(lang), ensure_ascii=False, separators=(",", ":"))
    (out / "play_data.js").write_text(
        "// scripts/build_play_page.py が生成（手で直さない）\n"
        f"var PLAY_DATA = {data};\n"
        'if (typeof module !== "undefined" && module.exports) module.exports = PLAY_DATA;\n',
        encoding="utf-8",
    )
    for name in COPIES:
        js = (WEB / name).read_text(encoding="utf-8")
        if lang == "en":
            if name == "play_local.js":
                js = translate(js, "play_local", "js")
            elif leftover(js, "js"):
                raise SystemExit(
                    f"web/{name} に日本語の文があります（英語版の対訳表を用意してください）"
                )
        (out / name).write_text(js, encoding="utf-8")


def page(lang: str) -> str:
    html = (WEB / "play.html").read_text(encoding="utf-8")
    marker = "<script>\n"
    if html.count(marker) != 1:
        raise SystemExit("web/play.html の本体スクリプトの位置が分かりません")
    html = html.replace(marker, INJECT + marker)
    html = html.replace(
        "<title>カルカソンヌ 人間 vs AI</title>", "<title>AIと対戦 | カルカソンヌ入門</title>"
    )
    # 画面上部のページ一覧の最後に、もう一方の言語へのリンク
    nav_end = "</a></nav>AIはこのブラウザの中で考えます。"
    if html.count(nav_end) != 1:
        raise SystemExit("web/play.html のページ一覧の位置が分かりません")
    html = html.replace(nav_end, "</a>__LANG__</nav>AIはこのブラウザの中で考えます。")
    if lang == "en":
        html = html.replace('<html lang="ja">', '<html lang="en">', 1)
        html = translate(html, "play")
    return html.replace("__LANG__", lang_link("play.html", lang, "lang"))


def build() -> None:
    write_scripts(DOCS, "ja")
    write_scripts(DOCS / "en", "en")
    write_pair("play.html", page("ja"), page("en"))
    print("wrote docs/play.html, docs/en/play.html and their scripts")


if __name__ == "__main__":
    build()
