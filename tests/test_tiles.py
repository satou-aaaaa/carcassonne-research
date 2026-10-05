from carcassonne.tiles import CITY, FIELD, MONASTERY, ROAD, load_tileset


def test_total_is_72_and_24_types():
    ts = load_tileset()
    assert ts.total == 72
    assert len(ts.types) == 24


def test_known_counts():
    ts = load_tileset()
    count = {t.id: t.count for t in ts.types}
    assert count["chapel"] == 4
    assert count["chapel_with_road"] == 2
    assert count["crossroads"] == 1
    assert count["three_split_road"] == 4
    # 盾付きタイルは全部で10枚（基本セット）
    pennants = sum(
        t.count for t in ts.types if any(p.pennant for p in t.variants[0].pieces if p.kind == CITY)
    )
    assert pennants == 10
    # 修道院は6枚
    monasteries = sum(
        t.count for t in ts.types if any(p.kind == MONASTERY for p in t.variants[0].pieces)
    )
    assert monasteries == 6


def test_every_variant_is_well_formed():
    ts = load_tileset()
    for t in ts.types:
        assert 1 <= len(t.variants) <= 4
        for v in t.variants:
            # 都市辺の半辺は草原に属さず、それ以外の辺の2つの半辺は必ずちょうど1つの草原に属する
            for s in range(4):
                halves = (v.half_piece[s * 2], v.half_piece[s * 2 + 1])
                if v.edges[s] == CITY:
                    assert halves == (None, None), (t.id, s)
                else:
                    assert None not in halves, (t.id, s)
                    for h in (s * 2, s * 2 + 1):
                        owners = [i for i, p in enumerate(v.pieces) if h in p.halves]
                        assert len(owners) == 1
            # 辺の種別と、都市/道の断片が持つ辺が一致する
            for i, p in enumerate(v.pieces):
                if p.kind in (CITY, ROAD):
                    for s in p.sides:
                        assert v.side_piece[s] == i
                        assert v.edges[s] == p.kind
                if p.kind == FIELD:
                    assert all(v.pieces[c].kind == CITY for c in p.city_adj)


def test_symmetric_tiles_have_fewer_variants():
    ts = load_tileset()
    by_id = {t.id: t for t in ts.types}
    assert len(by_id["crossroads"].variants) == 1
    assert len(by_id["chapel"].variants) == 1
    assert len(by_id["full_city_with_shield"].variants) == 1
    assert len(by_id["straight_road"].variants) == 2
    assert len(by_id["bent_road"].variants) == 4
