"""scripts/crosscheck_wingedsheep.py（別実装との得点の突き合わせ）のこちら側の部分を確かめる。

別実装そのものは Actions（scripts/sweeps/r004_crosscheck.sh）でだけ動かす。ここでは、こちらの対局づくりと
終局の数えの種類分けが、実際の得点と合っていることを見る。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import crosscheck_wingedsheep as cc

from carcassonne.tiles import load_tileset


def test_final_breakdown_adds_up():
    (g,) = cc.make_games(1, 40000, 50)  # ランダムな手の対局
    before = g["trace"][-2]
    for p in (0, 1):
        assert before[p] + sum(g["final"][k][p] for k in "CRFM") == g["scores"][p]


def test_shapes_are_distinct_per_tile_type():
    # 向きの違う形は別の署名になる（別実装のタイルと1対1で対応づけられる）
    ts = load_tileset()
    for tt in ts.types:
        sigs = [cc.piece_sig(v) for v in tt.variants]
        assert len(set(sigs)) == len(sigs), tt.id
