"""タイルの色と形（都市の輪郭・城壁・道）が、対戦ページ・クイズ（web/tile_art.js）と解説ページの図（scripts/board_svg.py）でそろっている。"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pytest
from board_svg import COL, city_anchor, city_shape, road_line


def test_tile_colors_match_js():
    js = (ROOT / "web" / "tile_art.js").read_text(encoding="utf-8")
    block = js[js.index("const COL = {") : js.index("};", js.index("const COL = {"))]
    js_col = dict(re.findall(r'(\w+): "([^"]+)"', block))
    for k, v in COL.items():
        assert js_col.get(k) == v, f"{k}: tile_art.js={js_col.get(k)} board_svg.py={v}"


ALL_SIDES = [
    [0], [1], [2], [3], [0, 1], [1, 2], [2, 3], [0, 3], [0, 2], [1, 3],
    [0, 1, 2], [1, 2, 3], [0, 2, 3], [0, 1, 3], [0, 1, 2, 3],
]  # fmt: skip


def _js_geometry():
    node = shutil.which("node")
    if not node:
        pytest.skip("node がない")
    code = (
        "global.self = global;"
        f"require({json.dumps(str(ROOT / 'web' / 'tile_art.js'))});"
        f"const S = {json.dumps(ALL_SIDES)};"
        "console.log(JSON.stringify({"
        " city: S.map(s => { const [p] = TileArt.cityShapes(s); return {poly: p, walls: p.walls}; }),"
        " anchor: S.map(s => TileArt.cityAnchor(s)),"
        " road: [[0,2],[1,3],[0,1],[1,2],[2,3],[0,3],[0]].map(s => TileArt.roadLine(s, 1)).concat([TileArt.roadLine([1], 3)]),"
        "}));"
    )
    out = subprocess.run([node, "-e", code], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def _close(a, b):
    assert len(a) == len(b)
    for p, q in zip(a, b):
        assert abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9, (p, q)


def test_tile_shapes_match_js():
    """都市の輪郭・城壁の線・盾の位置・道の線が、対戦ページ（JS）と解説ページの図（Python）で同じ。"""
    js = _js_geometry()
    for s, c, a in zip(ALL_SIDES, js["city"], js["anchor"]):
        poly, walls = city_shape(s)
        _close(poly, c["poly"])
        assert len(walls) == len(c["walls"])
        for w, jw in zip(walls, c["walls"]):
            _close(w, jw)
        _close([city_anchor(s)], [a])
    road_sides = [[0, 2], [1, 3], [0, 1], [1, 2], [2, 3], [0, 3], [0]]
    py_roads = [road_line(s, 1) for s in road_sides] + [road_line([1], 3)]
    for r, jr in zip(py_roads, js["road"]):
        _close(r, jr)


def test_city_shapes_are_simple():
    """見やすさの決まり: 1つの都市は多角形1つ。隣り合う2辺の都市は、別々の2都市（1辺ずつ）より十分大きい。"""

    def area(poly):
        return abs(sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(poly, poly[1:] + poly[:1]))) / 2

    one = area(city_shape([0])[0])
    joined = area(city_shape([0, 1])[0])
    assert joined > 2 * one * 1.3, (joined, one)
    # 城壁はタイルのふち（継ぎ目）を通らない: 両端以外の点はタイルの内側
    for s in ALL_SIDES[:-1]:
        for w in city_shape(s)[1]:
            for x, y in w[1:-1]:
                assert 0 < x < 1 and 0 < y < 1, (s, x, y)
