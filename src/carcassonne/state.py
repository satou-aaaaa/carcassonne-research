"""カルカソンヌ（基本セット・2人対戦）のルールエンジン。

ルールの正本は docs/RULES.md。得点は完成時（都市=タイル数×2+盾×2、道=タイル数、
修道院=9）と終了時（未完成の都市/道=タイル数(+盾)、修道院=1+周囲、農民=隣接する
完成都市1つにつき3点）。出典は docs/RULES.md と docs/RELATED_WORK.md を参照。

特徴（都市・道・草原・修道院）は盤面全体の Union-Find で管理する。手番は
「タイルを置く＋ミープルを最大1個置く」を1つの `Move` として扱う。
"""

from __future__ import annotations

import random
from typing import NamedTuple

from .tiles import CITY, FIELD, MONASTERY, ROAD, TileSet, load_tileset

# 辺 N,E,S,W に対応する座標差（y は北が正）
DIRS = ((0, 1), (1, 0), (0, -1), (-1, 0))
AROUND = tuple((dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0))

MEEPLES_PER_PLAYER = 7
NO_REQ = ("-", "-", "-", "-")
FARM_POINTS_PER_CITY = 3


class Move(NamedTuple):
    """1手: タイル配置とミープル配置。`piece` はVariant内の断片index、置かないならNone。"""

    x: int
    y: int
    variant: int
    piece: int | None


class State:
    """ゲーム状態。`copy()` で複製でき、`apply()` は自身を破壊的に更新する。"""

    def __init__(self, deck: list[int], tileset: TileSet | None = None) -> None:
        self.ts = tileset or load_tileset()
        self.deck = list(deck)  # 引く順に並べた種別index（開始タイルを除く）
        self.draw_pos = 0
        self.board: dict[tuple[int, int], tuple[int, int]] = {}
        # 空きマス（盤面に隣接）-> 4辺それぞれが隣接タイルから要求する辺種別（未接なら '-'）
        self.req: dict[tuple[int, int], tuple[str, str, str, str]] = {}
        self.tile_nodes: dict[tuple[int, int], tuple[int, ...]] = {}
        # Union-Find と特徴ごとの集計（根でのみ有効）
        self.parent: list[int] = []
        self.kind: list[str] = []
        self.open_ends: list[int] = []
        self.tiles: list[set | None] = []
        self.pennants: list[int] = []
        self.meeples: list[list[int]] = []
        self.field_cities: list[set | None] = []
        self.monasteries: dict[tuple[int, int], int] = {}
        self.supply = [MEEPLES_PER_PLAYER, MEEPLES_PER_PLAYER]
        self.scores = [0, 0]
        self.player = 0
        self.current: int | None = None  # 手番プレイヤーが引いて置くタイル
        self.over = False
        self.discarded: list[int] = []
        self.history: list[tuple[int, int, int, int, int | None]] = []  # (x, y, 種別, 向き, 断片)
        self._place_start()
        self._draw()

    # ---- 生成 ------------------------------------------------------------

    @classmethod
    def new_game(cls, seed: int) -> State:
        ts = load_tileset()
        deck = [i for i, t in enumerate(ts.types) for _ in range(t.count)]
        deck.remove(ts.start)  # 開始タイル1枚を除く
        random.Random(seed).shuffle(deck)
        return cls(deck, ts)

    def copy(self) -> State:
        c = State.__new__(State)
        c.ts = self.ts
        c.deck = self.deck  # 不変として共有（再決定化時は置き換える）
        c.draw_pos = self.draw_pos
        c.board = dict(self.board)
        c.req = dict(self.req)
        c.tile_nodes = dict(self.tile_nodes)
        c.parent = list(self.parent)
        c.kind = list(self.kind)
        c.open_ends = list(self.open_ends)
        c.tiles = [None if s is None else set(s) for s in self.tiles]
        c.pennants = list(self.pennants)
        c.meeples = [list(m) for m in self.meeples]
        c.field_cities = [None if s is None else set(s) for s in self.field_cities]
        c.monasteries = dict(self.monasteries)
        c.supply = list(self.supply)
        c.scores = list(self.scores)
        c.player = self.player
        c.current = self.current
        c.over = self.over
        c.discarded = list(self.discarded)
        c.history = list(self.history)
        return c

    # ---- Union-Find ------------------------------------------------------

    def _find(self, x: int) -> int:
        p = self.parent
        while p[x] != x:
            p[x] = p[p[x]]
            x = p[x]
        return x

    def _new_node(self, kind: str) -> int:
        n = len(self.parent)
        self.parent.append(n)
        self.kind.append(kind)
        self.open_ends.append(0)
        self.tiles.append(None)
        self.pennants.append(0)
        self.meeples.append([0, 0])
        self.field_cities.append(None)
        return n

    def _union(self, a: int, b: int) -> int:
        """根を統合して集計をマージし、新しい根を返す（ra != rb 前提）。"""
        ra, rb = self._find(a), self._find(b)
        if ra == rb:
            return ra
        self.parent[rb] = ra
        self.open_ends[ra] += self.open_ends[rb]
        self.pennants[ra] += self.pennants[rb]
        self.meeples[ra][0] += self.meeples[rb][0]
        self.meeples[ra][1] += self.meeples[rb][1]
        if self.tiles[ra] is not None and self.tiles[rb] is not None:
            self.tiles[ra] |= self.tiles[rb]
        if self.field_cities[ra] is not None and self.field_cities[rb] is not None:
            self.field_cities[ra] |= self.field_cities[rb]
        return ra

    # ---- 配置 ------------------------------------------------------------

    def _place_start(self) -> None:
        pos = (0, 0)
        self._put_tile(pos, self.ts.start, 0)

    def _put_tile(self, pos: tuple[int, int], ti: int, vi: int) -> None:
        """タイルを置き、断片ノードの生成と隣接タイルとの連結を行う（得点処理はしない）。"""
        v = self.ts.types[ti].variants[vi]
        self.board[pos] = (ti, vi)
        self.req.pop(pos, None)
        nodes: list[int] = []
        for p in v.pieces:
            n = self._new_node(p.kind)
            nodes.append(n)
            if p.kind in (CITY, ROAD):
                self.open_ends[n] = len(p.sides)
                self.tiles[n] = {pos}
                self.pennants[n] = 1 if p.pennant else 0
            elif p.kind == FIELD:
                self.field_cities[n] = {nodes[c] for c in p.city_adj}
            elif p.kind == MONASTERY:
                self.monasteries[pos] = n
        self.tile_nodes[pos] = tuple(nodes)
        for s, (dx, dy) in enumerate(DIRS):
            npos = (pos[0] + dx, pos[1] + dy)
            nb = self.board.get(npos)
            if nb is None:
                r = list(self.req.get(npos, NO_REQ))
                r[(s + 2) % 4] = v.edges[s]
                self.req[npos] = tuple(r)  # type: ignore[assignment]
                continue
            nv = self.ts.types[nb[0]].variants[nb[1]]
            nnodes = self.tile_nodes[npos]
            os_ = (s + 2) % 4
            mine, theirs = v.side_piece[s], nv.side_piece[os_]
            if mine is not None and theirs is not None:
                ra, rb = self._find(nodes[mine]), self._find(nnodes[theirs])
                if ra == rb:
                    self.open_ends[ra] -= 2
                else:
                    r = self._union(ra, rb)
                    self.open_ends[r] -= 2
            for h in (0, 1):
                fm, ft = v.half_piece[s * 2 + h], nv.half_piece[os_ * 2 + (1 - h)]
                if fm is not None and ft is not None:
                    self._union(nodes[fm], nnodes[ft])

    # ---- 手番・山札 --------------------------------------------------------

    def remaining_counts(self) -> list[int]:
        """山札（現在引いているタイルを除く）に残る各種別の枚数。公開情報として扱える。"""
        counts = [t.count for t in self.ts.types]
        for ti, _ in self.board.values():
            counts[ti] -= 1
        for ti in self.discarded:
            counts[ti] -= 1
        if self.current is not None:
            counts[self.current] -= 1
        return counts

    def _draw(self) -> None:
        """置けるタイルが引けるまで引き、置けないタイルは捨てる。山札切れなら終局処理。"""
        while self.draw_pos < len(self.deck):
            t = self.deck[self.draw_pos]
            self.draw_pos += 1
            if self._has_placement(t):
                self.current = t
                return
            self.discarded.append(t)
        self.current = None
        self._finish()

    def _fits(self, pos: tuple[int, int], edges: tuple[str, ...]) -> bool:
        req = self.req.get(pos)
        return req is not None and all(r == "-" or r == e for r, e in zip(req, edges))

    def _fitting_variants(self, ti: int, pos: tuple[int, int]) -> tuple[int, ...]:
        """タイル種別 ti を pos に置ける向き（variant index）。要求パターンごとにメモ化する。"""
        key = (ti, self.req[pos])
        cache = self.ts.fit_cache
        hit = cache.get(key)
        if hit is None:
            hit = tuple(
                vi
                for vi, v in enumerate(self.ts.types[ti].variants)
                if all(r == "-" or r == e for r, e in zip(key[1], v.edges))
            )
            cache[key] = hit
        return hit

    def _has_placement(self, ti: int) -> bool:
        return any(self._fitting_variants(ti, pos) for pos in self.req)

    def placements(self) -> list[tuple[int, int, int]]:
        """現在のタイルの合法な配置 (x, y, variant) の一覧。"""
        if self.current is None:
            return []
        return [
            (pos[0], pos[1], vi)
            for pos in sorted(self.req)
            for vi in self._fitting_variants(self.current, pos)
        ]

    def random_move(self, rng: random.Random, meeple_prob: float = 0.3) -> Move:
        """ロールアウト用の高速な乱択。配置は一様、ミープルは確率 meeple_prob で置く（置ける断片から一様）。

        全手を列挙する `legal_moves()` と違い、ミープル配置を列挙しないため速い。
        Jappert (2022) のランダムロールアウト（ミープル確率30%）に倣う。
        """
        x, y, vi = rng.choice(
            [
                (pos[0], pos[1], vi)
                for pos in self.req
                for vi in self._fitting_variants(self.current, pos)
            ]
        )
        piece = None
        if self.supply[self.player] > 0 and rng.random() < meeple_prob:
            v = self.ts.types[self.current].variants[vi]
            free = [pi for pi in range(len(v.pieces)) if not self._occupied((x, y), v, pi)]
            if free:
                piece = rng.choice(free)
        return Move(x, y, vi, piece)

    def _occupied(self, pos: tuple[int, int], v, piece_idx: int) -> bool:
        """pos にvの向きで置いた場合、その断片が連結する特徴に既にミープルがいるか。"""
        p = v.pieces[piece_idx]
        if p.kind == MONASTERY:
            return False
        if p.kind in (CITY, ROAD):
            for s in p.sides:
                dx, dy = DIRS[s]
                nb = self.board.get((pos[0] + dx, pos[1] + dy))
                if nb is None:
                    continue
                nv = self.ts.types[nb[0]].variants[nb[1]]
                node = self.tile_nodes[(pos[0] + dx, pos[1] + dy)][nv.side_piece[(s + 2) % 4]]
                if any(self.meeples[self._find(node)]):
                    return True
            return False
        for hh in p.halves:
            s, h = divmod(hh, 2)
            dx, dy = DIRS[s]
            npos = (pos[0] + dx, pos[1] + dy)
            nb = self.board.get(npos)
            if nb is None:
                continue
            nv = self.ts.types[nb[0]].variants[nb[1]]
            fp = nv.half_piece[((s + 2) % 4) * 2 + (1 - h)]
            if fp is not None and any(self.meeples[self._find(self.tile_nodes[npos][fp])]):
                return True
        return False

    def legal_moves(self) -> list[Move]:
        if self.over or self.current is None:
            return []
        moves = []
        can_meeple = self.supply[self.player] > 0
        for x, y, vi in self.placements():
            moves.append(Move(x, y, vi, None))
            if not can_meeple:
                continue
            v = self.ts.types[self.current].variants[vi]
            for pi in range(len(v.pieces)):
                if not self._occupied((x, y), v, pi):
                    moves.append(Move(x, y, vi, pi))
        return moves

    # ---- 着手と得点 --------------------------------------------------------

    def apply(self, move: Move) -> None:
        if self.over or self.current is None:
            raise ValueError("ゲームは終了している")
        pos = (move.x, move.y)
        ti = self.current
        v = self.ts.types[ti].variants[move.variant]
        if pos in self.board or pos not in self.req or not self._fits(pos, v.edges):
            raise ValueError(f"不正な配置: {move}")
        if move.piece is not None:
            if self.supply[self.player] <= 0:
                raise ValueError("ミープルが残っていない")
            if not (0 <= move.piece < len(v.pieces)) or self._occupied(pos, v, move.piece):
                raise ValueError(f"不正なミープル配置: {move}")
        self.history.append((move.x, move.y, ti, move.variant, move.piece))
        self._put_tile(pos, ti, move.variant)
        if move.piece is not None:
            root = self._find(self.tile_nodes[pos][move.piece])
            self.meeples[root][self.player] += 1
            self.supply[self.player] -= 1
        self._score_after_placement(pos, v)
        self.player = 1 - self.player
        self._draw()

    def _award(self, root: int, points: int) -> None:
        """多数派（同数なら全員）に得点し、ミープルを回収する。"""
        m = self.meeples[root]
        top = max(m)
        if top > 0:
            for p in (0, 1):
                if m[p] == top:
                    self.scores[p] += points
        for p in (0, 1):
            self.supply[p] += m[p]
            m[p] = 0

    def _score_after_placement(self, pos: tuple[int, int], v) -> None:
        done: set[int] = set()
        for n, p in zip(self.tile_nodes[pos], v.pieces):
            if p.kind not in (CITY, ROAD):
                continue
            r = self._find(n)
            if r in done or self.open_ends[r] != 0:
                continue
            done.add(r)
            n_tiles = len(self.tiles[r])
            if p.kind == CITY:
                self._award(r, 2 * (n_tiles + self.pennants[r]))
            else:
                self._award(r, n_tiles)
        for dx, dy in ((0, 0), *AROUND):
            mpos = (pos[0] + dx, pos[1] + dy)
            node = self.monasteries.get(mpos)
            if node is None:
                continue
            r = self._find(node)
            if any(self.meeples[r]) and self._surrounded(mpos):
                self._award(r, 9)

    def _surrounded(self, pos: tuple[int, int]) -> bool:
        return all((pos[0] + dx, pos[1] + dy) in self.board for dx, dy in AROUND)

    def _end_awards(self) -> list[tuple[int, int]]:
        """今ゲームが終わった場合の (根, 得点) 一覧。ミープルのいる特徴のみ。状態は変更しない。"""
        out: list[tuple[int, int]] = []
        seen: set[int] = set()
        for n in range(len(self.parent)):
            r = self._find(n)
            if r in seen or not any(self.meeples[r]):
                continue
            seen.add(r)
            k = self.kind[r]
            if k == CITY:
                out.append((r, len(self.tiles[r]) + self.pennants[r]))
            elif k == ROAD:
                out.append((r, len(self.tiles[r])))
            elif k == FIELD:
                cities = {self._find(c) for c in self.field_cities[r]}
                done = sum(1 for c in cities if self.open_ends[c] == 0)
                out.append((r, FARM_POINTS_PER_CITY * done))
        for mpos, n in self.monasteries.items():
            r = self._find(n)
            if any(self.meeples[r]):
                around = sum(1 for dx, dy in AROUND if (mpos[0] + dx, mpos[1] + dy) in self.board)
                out.append((r, 1 + around))
        return out

    def _finish(self) -> None:
        """終局処理: 未完成の特徴と農民の得点。"""
        self.over = True
        for r, points in self._end_awards():
            self._award(r, points)

    def projected_scores(self) -> list[int]:
        """今終局した場合の得点（評価関数・探索の打ち切り用）。終局後は確定得点。"""
        out = list(self.scores)
        if self.over:
            return out
        for r, points in self._end_awards():
            m = self.meeples[r]
            top = max(m)
            for p in (0, 1):
                if m[p] == top:
                    out[p] += points
        return out

    # ---- 結果 ------------------------------------------------------------

    @property
    def winner(self) -> int | None:
        """勝者（0/1）。終局前・引き分けはNone。"""
        if not self.over or self.scores[0] == self.scores[1]:
            return None
        return 0 if self.scores[0] > self.scores[1] else 1
