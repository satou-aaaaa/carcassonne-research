"""タイルの色が、対戦ページ・クイズ（web/tile_art.js）と解説ページの図（scripts/board_svg.py）でそろっている。"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from board_svg import COL


def test_tile_colors_match_js():
    js = (ROOT / "web" / "tile_art.js").read_text(encoding="utf-8")
    block = js[js.index("const COL = {") : js.index("};", js.index("const COL = {"))]
    js_col = dict(re.findall(r'(\w+): "([^"]+)"', block))
    for k, v in COL.items():
        assert js_col.get(k) == v, f"{k}: tile_art.js={js_col.get(k)} board_svg.py={v}"
