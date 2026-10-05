"""エンジンとは独立な、素朴（遅いが単純）な得点計算オラクル。

Union-Find を使わず、毎手、盤面全体から特徴をBFSで求め直して得点する。
エンジンの増分管理（連結・開放端・得点・ミープル回収）の検証にだけ使う。
タイル定義（Variantの解釈）は共有するため、データ自体の正しさは test_tiles.py で別途検証する。
"""

from __future__ import annotations

from carcassonne.state import AROUND, DIRS, FARM_POINTS_PER_CITY
from carcassonne.tiles import CITY, FIELD, MONASTERY, ROAD, TileSet


class Oracle:
    def __init__(self, ts: TileSet) -> None:
        self.ts = ts
        self.board: dict[tuple[int, int], tuple[int, int]] = {}
        self.meeples: list[tuple[int, tuple[int, int], int]] = []  # (player, pos, piece)
        self.scores = [0, 0]

    def variant(self, pos):
        ti, vi = self.board[pos]
        return self.ts.types[ti].variants[vi]

    def components(self):
        """(kind, [(pos, piece_idx)...]) の一覧を返す。"""
        adj: dict[tuple, list[tuple]] = {}
        for pos in self.board:
            v = self.variant(pos)
            for i in range(len(v.pieces)):
                adj.setdefault((pos, i), [])
            for s, (dx, dy) in enumerate(DIRS):
                npos = (pos[0] + dx, pos[1] + dy)
                if npos not in self.board:
                    continue
                nv = self.variant(npos)
                os_ = (s + 2) % 4
                a, b = v.side_piece[s], nv.side_piece[os_]
                if a is not None and b is not None:
                    adj[(pos, a)].append((npos, b))
                for h in (0, 1):
                    fa, fb = v.half_piece[s * 2 + h], nv.half_piece[os_ * 2 + 1 - h]
                    if fa is not None and fb is not None:
                        adj[(pos, fa)].append((npos, fb))
        seen, comps = set(), []
        for start in adj:
            if start in seen:
                continue
            stack, comp = [start], []
            seen.add(start)
            while stack:
                n = stack.pop()
                comp.append(n)
                for m in adj[n]:
                    if m not in seen:
                        seen.add(m)
                        stack.append(m)
            kind = self.variant(start[0]).pieces[start[1]].kind
            comps.append((kind, comp))
        return comps

    def _open_ends(self, comp) -> int:
        n = 0
        for pos, i in comp:
            for s in self.variant(pos).pieces[i].sides:
                dx, dy = DIRS[s]
                if (pos[0] + dx, pos[1] + dy) not in self.board:
                    n += 1
        return n

    def _info(self, kind, comp):
        tiles = {pos for pos, _ in comp}
        pennants = sum(1 for pos, i in comp if kind == CITY and self.variant(pos).pieces[i].pennant)
        return tiles, pennants

    def _award(self, comp, points) -> bool:
        members = set(comp)
        mine = [m for m in self.meeples if (m[1], m[2]) in members]
        if not mine:
            return False
        count = [sum(1 for m in mine if m[0] == p) for p in (0, 1)]
        for p in (0, 1):
            if count[p] == max(count):
                self.scores[p] += points
        self.meeples = [m for m in self.meeples if m not in mine]
        return True

    def place(self, pos, ti, vi, player, piece) -> None:
        self.board[pos] = (ti, vi)
        if piece is not None:
            self.meeples.append((player, pos, piece))
        for kind, comp in self.components():
            if kind in (CITY, ROAD) and self._open_ends(comp) == 0:
                tiles, pennants = self._info(kind, comp)
                self._award(comp, 2 * (len(tiles) + pennants) if kind == CITY else len(tiles))
            elif kind == MONASTERY:
                ((pos_m, _),) = comp
                if all((pos_m[0] + dx, pos_m[1] + dy) in self.board for dx, dy in AROUND):
                    self._award(comp, 9)

    def finish(self) -> None:
        comps = self.components()
        city_done = {}
        for kind, comp in comps:
            if kind == CITY:
                done = self._open_ends(comp) == 0
                for n in comp:
                    city_done[n] = done
        for kind, comp in comps:
            tiles, pennants = self._info(kind, comp)
            if kind == CITY:
                self._award(comp, len(tiles) + pennants)
            elif kind == ROAD:
                self._award(comp, len(tiles))
            elif kind == MONASTERY:
                ((pos_m, _),) = comp
                around = sum(1 for dx, dy in AROUND if (pos_m[0] + dx, pos_m[1] + dy) in self.board)
                self._award(comp, 1 + around)
            elif kind == FIELD:
                adj_cities = set()
                for pos, i in comp:
                    for ci in self.variant(pos).pieces[i].city_adj:
                        adj_cities.add((pos, ci))
                # 隣接する都市断片を連結成分ごとにまとめ、完成した都市の数を数える
                city_comp = {}
                for k2, c2 in comps:
                    if k2 == CITY:
                        for n in c2:
                            city_comp[n] = id(c2)
                done_ids = {city_comp[n] for n in adj_cities if city_done[n]}
                self._award(comp, FARM_POINTS_PER_CITY * len(done_ids))
