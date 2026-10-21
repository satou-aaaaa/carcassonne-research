"""ブラウザだけでAIと対戦できる公開ページ（docs/play.html）を作る。

    py scripts/build_play_page.py

AIは Python 版（src/carcassonne/fast*.py）を JavaScript に移したもの（web/carcassonne_engine.js）で、
ブラウザの中で計算する（サーバー不要）。画面はローカル対戦用の web/play.html を共用し、
サーバーへの問い合わせの代わりに web/play_local.js がブラウザ内で対局を進める。

書き出すもの:
- docs/play.html            web/play.html にブラウザ内対局用のスクリプトを差し込んだもの
- docs/play_data.js         タイル定義・エンジン用テーブル・評価関数の重み
- docs/carcassonne_engine.js, docs/play_features.js, docs/play_local.js, docs/play_worker.js
                            web/ からの複写

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

from carcassonne.fast import build_tables
from carcassonne.fast_eval import NF, load_eval
from carcassonne.tiles import load_tileset
from carcassonne.webplay import tile_library

DOCS = ROOT / "docs"
WEB = ROOT / "web"
EVAL = "models/eval_champion.npy"  # 自己対戦ループの最新チャンピオン（selfplay-state の loop/models/ から複写）
CHAMPION = "models/eval_champion.json"  # その世代名・採用日（画面の表示用）
COPIES = ["carcassonne_engine.js", "play_features.js", "play_local.js", "play_worker.js"]
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
INJECT = """<style>.server-only { display: none !important; } .local-only { display: block !important; }</style>
<script src="play_data.js"></script>
<script src="carcassonne_engine.js"></script>
<script src="play_local.js"></script>
"""


def play_data() -> dict:
    ts = load_tileset()
    T = build_tables(ts)
    w, mode = load_eval(str(ROOT / EVAL))
    if mode != 1 or len(w) != NF:
        raise SystemExit(f"{EVAL} は線形の評価関数ではありません（JavaScript 版は線形のみ対応）")
    info = json.loads((ROOT / CHAMPION).read_text(encoding="utf-8"))
    levels = json.loads(json.dumps(LEVELS))
    adopted = f"、{info['date']} 採用" if info.get("date") else ""
    levels["strong"]["label"] = f"最強（自己対戦で学んだ最新AI {info['name']}{adopted}。1手1〜数秒）"
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


def build() -> None:
    data = json.dumps(play_data(), ensure_ascii=False, separators=(",", ":"))
    (DOCS / "play_data.js").write_text(
        "// scripts/build_play_page.py が生成（手で直さない）\n"
        f"var PLAY_DATA = {data};\n"
        'if (typeof module !== "undefined" && module.exports) module.exports = PLAY_DATA;\n',
        encoding="utf-8",
    )
    for name in COPIES:
        (DOCS / name).write_text((WEB / name).read_text(encoding="utf-8"), encoding="utf-8")
    html = (WEB / "play.html").read_text(encoding="utf-8")
    marker = "<script>\n"
    if html.count(marker) != 1:
        raise SystemExit("web/play.html の本体スクリプトの位置が分かりません")
    html = html.replace(marker, INJECT + marker)
    html = html.replace(
        "<title>カルカソンヌ 人間 vs AI</title>", "<title>AIと対戦 | カルカソンヌ入門</title>"
    )
    (DOCS / "play.html").write_text(html, encoding="utf-8")
    print("wrote docs/play.html and its scripts")


if __name__ == "__main__":
    build()
