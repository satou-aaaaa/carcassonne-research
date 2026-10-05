"""タイル定義の読み込み。

`data/tiles.json`（回転同値・絵柄違いを統合した24種・計72枚）を読み、回転ごとの
`Variant` を事前計算する。辺の順序は N,E,S,W = 0,1,2,3（時計回り）。半辺は
`side*2 + h`（h=0,1 は辺の上を時計回りに進む順）。隣接タイルとは、自分の
(side, h) が相手の ((side+2)%4, 1-h) に接する。

出典（ルール・タイル構成）: docs/RULES.md、docs/RELATED_WORK.md を参照。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CITY, ROAD, FIELD, MONASTERY = "C", "R", "F", "M"

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "tiles.json"


@dataclass(frozen=True)
class Piece:
    """1タイル内の地形の断片。盤面全体では隣接タイルの同種断片と連結して1つの特徴になる。"""

    kind: str  # CITY / ROAD / FIELD / MONASTERY
    sides: tuple[int, ...] = ()  # CITY/ROAD: 接する辺
    halves: tuple[int, ...] = ()  # FIELD: 接する半辺
    pennant: bool = False  # CITY: 盾の有無
    city_adj: tuple[int, ...] = ()  # FIELD: 隣接する都市断片の（Variant内）index


@dataclass(frozen=True)
class Variant:
    """あるタイルの1つの向き。"""

    pieces: tuple[Piece, ...]
    edges: tuple[str, str, str, str]  # 各辺の種別（CITY/ROAD/FIELD）
    side_piece: tuple[int | None, ...]  # 辺 -> CITY/ROAD断片のindex（FIELD辺はNone）
    half_piece: tuple[int | None, ...]  # 半辺 -> FIELD断片のindex（CITY辺の半辺はNone）


@dataclass(frozen=True)
class TileType:
    id: str
    count: int
    variants: tuple[Variant, ...]  # 回転で重複する向きは除いてある


def _rotate(raw: dict, r: int) -> dict:
    """生定義を時計回りに90度×r回転した定義を、正規化（ソート）して返す。"""

    def rs(s: int) -> int:
        return (s + r) % 4

    def rh(h: int) -> int:
        return rs(h // 2) * 2 + h % 2

    cities = [
        {"sides": sorted(rs(s) for s in c["sides"]), "pennant": c["pennant"]} for c in raw["cities"]
    ]
    order = sorted(range(len(cities)), key=lambda i: cities[i]["sides"])
    remap = {old: new for new, old in enumerate(order)}
    cities = [cities[i] for i in order]
    roads = sorted(sorted(rs(s) for s in road) for road in raw["roads"])
    fields = sorted(
        (
            {
                "halves": sorted(rh(h) for h in f["halves"]),
                "cities": sorted(remap[c] for c in f["cities"]),
            }
            for f in raw["fields"]
        ),
        key=lambda f: f["halves"],
    )
    return {"monastery": raw["monastery"], "cities": cities, "roads": roads, "fields": fields}


def _build_variant(d: dict) -> Variant:
    pieces: list[Piece] = []
    side_piece: list[int | None] = [None] * 4
    half_piece: list[int | None] = [None] * 8
    edges = [FIELD] * 4
    for c in d["cities"]:
        idx = len(pieces)
        pieces.append(Piece(CITY, sides=tuple(c["sides"]), pennant=c["pennant"]))
        for s in c["sides"]:
            side_piece[s] = idx
            edges[s] = CITY
    for road in d["roads"]:
        idx = len(pieces)
        pieces.append(Piece(ROAD, sides=tuple(road)))
        for s in road:
            side_piece[s] = idx
            edges[s] = ROAD
    for f in d["fields"]:
        idx = len(pieces)
        pieces.append(Piece(FIELD, halves=tuple(f["halves"]), city_adj=tuple(f["cities"])))
        for h in f["halves"]:
            half_piece[h] = idx
    if d["monastery"]:
        pieces.append(Piece(MONASTERY))
    return Variant(tuple(pieces), tuple(edges), tuple(side_piece), tuple(half_piece))  # type: ignore[arg-type]


@dataclass(frozen=True)
class TileSet:
    types: tuple[TileType, ...]
    start: int  # 開始タイルの種別index
    index: dict  # id -> 種別index

    @property
    def total(self) -> int:
        return sum(t.count for t in self.types)


@lru_cache(maxsize=1)
def load_tileset(path: str | None = None) -> TileSet:
    data = json.loads(Path(path or DATA_PATH).read_text(encoding="utf-8"))
    types = []
    for raw in data["tiles"]:
        seen: dict[str, Variant] = {}
        for r in range(4):
            d = _rotate(raw, r)
            seen.setdefault(json.dumps(d, sort_keys=True), _build_variant(d))
        types.append(TileType(raw["id"], raw["count"], tuple(seen.values())))
    index = {t.id: i for i, t in enumerate(types)}
    return TileSet(tuple(types), index[data["start_tile"]], index)
