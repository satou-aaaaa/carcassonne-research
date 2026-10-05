"""Numba版の高速エンジン（ロールアウト・探索用）。

`state.py` のPythonエンジンと同じルールを配列ベースで再実装する。正しさは
`tests/test_fast.py` で、同一の手順列をPythonエンジンに再生した結果（得点・手持ち・終局）との
一致で検証する。ルールの正本は docs/RULES.md。

状態は配列のタプル `S`。盤は 145x145 のグリッド（開始タイルが中央）で、各マスには「置かれた順番+1」
（0は空）を持つ。断片ノードのIDは `順番*P + 断片index`。Union-Findと集計は根でのみ有効。
"""

from __future__ import annotations

import numpy as np
from numba import njit

from .tiles import CITY, FIELD, MONASTERY, ROAD, TileSet, load_tileset

G = 145  # グリッド一辺
C0 = 72  # 開始タイルの座標オフセット
NT = 72  # タイル総数
MEEPLES = 7
KIND = {CITY: 0, ROAD: 1, FIELD: 2, MONASTERY: 3}

# sc（スカラー）配列の添字
SC_N, SC_PL, SC_S0, SC_S1, SC_SUP0, SC_SUP1, SC_OVER, SC_DRAW, SC_CUR, SC_DISC = range(10)
SC_LEN = 10


def build_tables(ts: TileSet) -> tuple:
    """TileSet を数値テーブルに変換する。"""
    gids = [(ti, vi) for ti, t in enumerate(ts.types) for vi in range(len(t.variants))]
    ng = len(gids)
    P = max(len(v.pieces) for t in ts.types for v in t.variants)
    edge = np.zeros((ng, 4), np.int8)
    npc = np.zeros(ng, np.int8)
    pkind = np.full((ng, P), -1, np.int8)
    psides = np.zeros((ng, P), np.int8)
    phalves = np.zeros((ng, P), np.int16)
    ppen = np.zeros((ng, P), np.int8)
    padj = np.zeros((ng, P), np.int16)
    cadj = np.zeros((ng, P), np.int16)
    sidepc = np.full((ng, 4), -1, np.int8)
    halfpc = np.full((ng, 8), -1, np.int8)
    mpiece = np.full(ng, -1, np.int8)
    vbase = np.zeros(len(ts.types), np.int32)
    nvar = np.zeros(len(ts.types), np.int32)
    g = 0
    for ti, t in enumerate(ts.types):
        vbase[ti] = g
        nvar[ti] = len(t.variants)
        for v in t.variants:
            kmap = {CITY: 0, ROAD: 1, FIELD: 2, MONASTERY: 3}
            for s in range(4):
                edge[g, s] = {CITY: 0, ROAD: 1, FIELD: 2}[v.edges[s]]
                sp = v.side_piece[s]
                sidepc[g, s] = -1 if sp is None else sp
            for h in range(8):
                hp = v.half_piece[h]
                halfpc[g, h] = -1 if hp is None else hp
            npc[g] = len(v.pieces)
            for i, p in enumerate(v.pieces):
                pkind[g, i] = kmap[p.kind]
                psides[g, i] = sum(1 << s for s in p.sides)
                phalves[g, i] = sum(1 << h for h in p.halves)
                ppen[g, i] = 1 if p.pennant else 0
                padj[g, i] = sum(1 << c for c in p.city_adj)
                if p.kind == MONASTERY:
                    mpiece[g] = i
                for c in p.city_adj:
                    cadj[g, c] |= 1 << i
            g += 1
    return (
        edge,
        npc,
        pkind,
        psides,
        phalves,
        ppen,
        padj,
        cadj,
        sidepc,
        halfpc,
        mpiece,
        vbase,
        nvar,
    )


def make_state(P: int) -> tuple:
    NN = NT * P
    return (
        np.zeros(G * G, np.int16),  # grid: 順番+1
        np.zeros(NT, np.int16),  # tg: 順番 -> 向きの全体ID
        np.zeros(NT, np.int32),  # tcell: 順番 -> マス
        np.arange(NN, dtype=np.int16),  # parent
        np.full(NN, -1, np.int8),  # kind
        np.zeros(NN, np.int8),  # open_ends
        np.zeros(NN, np.int8),  # pennants
        np.zeros(NN, np.int64),  # tiles lo（順番0..35）
        np.zeros(NN, np.int64),  # tiles hi（順番36..71）
        np.zeros(NN * 2, np.int8),  # meeples[node*2+player]
        np.zeros(SC_LEN, np.int32),  # sc
        np.zeros(NT, np.int8),  # deck（山札: 開始タイルを除く71枚の種別index）
    )


@njit(cache=True)
def copy_state(S):
    return (
        S[0].copy(),
        S[1].copy(),
        S[2].copy(),
        S[3].copy(),
        S[4].copy(),
        S[5].copy(),
        S[6].copy(),
        S[7].copy(),
        S[8].copy(),
        S[9].copy(),
        S[10].copy(),
        S[11].copy(),
    )


@njit(cache=True)
def popcnt(x):
    c = 0
    while x:
        x &= x - 1
        c += 1
    return c


@njit(cache=True)
def dircell(s):
    if s == 0:
        return 1
    if s == 1:
        return G
    if s == 2:
        return -1
    return -G


@njit(cache=True)
def find(parent, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


@njit(cache=True)
def union(S, a, b):
    """根を統合して集計をマージ（open_endsは単純加算。呼び出し側で閉じた分を引く）。"""
    parent, opn, pen, tlo, thi, meep = S[3], S[5], S[6], S[7], S[8], S[9]
    ra = find(parent, a)
    rb = find(parent, b)
    if ra == rb:
        return ra
    parent[rb] = ra
    opn[ra] += opn[rb]
    pen[ra] += pen[rb]
    tlo[ra] |= tlo[rb]
    thi[ra] |= thi[rb]
    meep[ra * 2] += meep[rb * 2]
    meep[ra * 2 + 1] += meep[rb * 2 + 1]
    return ra


@njit(cache=True)
def tile_of(S, cell):
    return S[0][cell] - 1


@njit(cache=True)
def place_tile(S, T, P, cell, g):
    """タイルを置いてノード生成と隣接との連結を行う（得点処理はしない）。"""
    grid, tg, tcell, parent, kind, opn, pen, tlo, thi, meep = (
        S[0],
        S[1],
        S[2],
        S[3],
        S[4],
        S[5],
        S[6],
        S[7],
        S[8],
        S[9],
    )
    sc = S[10]
    npc, pkind, psides, ppen, sidepc, halfpc = T[1], T[2], T[3], T[5], T[8], T[9]
    t = sc[SC_N]
    sc[SC_N] = t + 1
    grid[cell] = t + 1
    tg[t] = g
    tcell[t] = cell
    base = t * P
    for i in range(npc[g]):
        n = base + i
        parent[n] = n
        kind[n] = pkind[g, i]
        meep[n * 2] = 0
        meep[n * 2 + 1] = 0
        pen[n] = 0
        tlo[n] = 0
        thi[n] = 0
        opn[n] = 0
        if pkind[g, i] <= 1:
            opn[n] = popcnt(np.int64(psides[g, i]))
            if t < 36:
                tlo[n] = np.int64(1) << t
            else:
                thi[n] = np.int64(1) << (t - 36)
            pen[n] = ppen[g, i]
    for s in range(4):
        ncell = cell + dircell(s)
        nt = grid[ncell] - 1
        if nt < 0:
            continue
        ng = tg[nt]
        nbase = nt * P
        os_ = (s + 2) % 4
        a = sidepc[g, s]
        b = sidepc[ng, os_]
        if a >= 0 and b >= 0:
            ra = find(parent, base + a)
            rb = find(parent, nbase + b)
            if ra == rb:
                opn[ra] -= 2
            else:
                r = union(S, ra, rb)
                opn[r] -= 2
        for h in range(2):
            fa = halfpc[g, s * 2 + h]
            fb = halfpc[ng, os_ * 2 + 1 - h]
            if fa >= 0 and fb >= 0:
                union(S, base + fa, nbase + fb)


@njit(cache=True)
def req_at(S, T, cell, out):
    """マス cell の4辺の要求辺種別（隣接なしは -1）を out に書き、隣接数を返す。"""
    grid, tg = S[0], S[1]
    edge = T[0]
    cnt = 0
    for s in range(4):
        nt = grid[cell + dircell(s)] - 1
        if nt < 0:
            out[s] = -1
        else:
            out[s] = edge[tg[nt], (s + 2) % 4]
            cnt += 1
    return cnt


@njit(cache=True)
def gen_placements(S, T, ti, stamp, stamp_val, out_cell, out_g, limit_first):
    """タイル種別 ti の合法配置を列挙して件数を返す。limit_first=Trueなら最初の1件で打ち切る。"""
    grid, tcell = S[0], S[2]
    edge, vbase, nvar = T[0], T[11], T[12]
    n_placed = S[10][SC_N]
    req = np.empty(4, np.int8)
    k = 0
    for t in range(n_placed):
        c0 = tcell[t]
        for s in range(4):
            c = c0 + dircell(s)
            if grid[c] != 0 or stamp[c] == stamp_val:
                continue
            stamp[c] = stamp_val
            req_at(S, T, c, req)
            for vi in range(nvar[ti]):
                g = vbase[ti] + vi
                ok = True
                for d in range(4):
                    if req[d] >= 0 and req[d] != edge[g, d]:
                        ok = False
                        break
                if ok:
                    out_cell[k] = c
                    out_g[k] = g
                    k += 1
                    if limit_first:
                        return k
    return k


@njit(cache=True)
def piece_free(S, T, P, cell, g, pi):
    """cell に向き g で置いたとき、断片 pi が連結する特徴に既にミープルがいなければ True。"""
    grid, tg, parent, meep = S[0], S[1], S[3], S[9]
    pkind, psides, phalves, sidepc, halfpc = T[2], T[3], T[4], T[8], T[9]
    k = pkind[g, pi]
    if k == 3:
        return True
    if k <= 1:
        for s in range(4):
            if (psides[g, pi] >> s) & 1:
                nt = grid[cell + dircell(s)] - 1
                if nt < 0:
                    continue
                nb = sidepc[tg[nt], (s + 2) % 4]
                r = find(parent, nt * P + nb)
                if meep[r * 2] + meep[r * 2 + 1] > 0:
                    return False
        return True
    for hh in range(8):
        if (phalves[g, pi] >> hh) & 1:
            s = hh // 2
            h = hh % 2
            nt = grid[cell + dircell(s)] - 1
            if nt < 0:
                continue
            fp = halfpc[tg[nt], ((s + 2) % 4) * 2 + 1 - h]
            if fp >= 0:
                r = find(parent, nt * P + fp)
                if meep[r * 2] + meep[r * 2 + 1] > 0:
                    return False
    return True


@njit(cache=True)
def award(S, r, points):
    sc, meep = S[10], S[9]
    m0 = meep[r * 2]
    m1 = meep[r * 2 + 1]
    top = max(m0, m1)
    if top > 0:
        if m0 == top:
            sc[SC_S0] += points
        if m1 == top:
            sc[SC_S1] += points
    sc[SC_SUP0] += m0
    sc[SC_SUP1] += m1
    meep[r * 2] = 0
    meep[r * 2 + 1] = 0


@njit(cache=True)
def surrounded(S, cell):
    grid = S[0]
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            if dx == 0 and dy == 0:
                continue
            if grid[cell + dx * G + dy] == 0:
                return False
    return True


@njit(cache=True)
def score_after_placement(S, T, P, cell, g):
    grid, tg, parent, opn, tlo, thi, pen, meep = S[0], S[1], S[3], S[5], S[7], S[8], S[6], S[9]
    npc, pkind, mpiece = T[1], T[2], T[10]
    t = grid[cell] - 1
    base = t * P
    done = np.full(P, -1, np.int32)
    nd = 0
    for i in range(npc[g]):
        k = pkind[g, i]
        if k > 1:
            continue
        r = find(parent, base + i)
        if opn[r] != 0:
            continue
        seen = False
        for j in range(nd):
            if done[j] == r:
                seen = True
        if seen:
            continue
        done[nd] = r
        nd += 1
        ntiles = popcnt(tlo[r]) + popcnt(thi[r])
        if k == 0:
            award(S, r, 2 * (ntiles + pen[r]))
        else:
            award(S, r, ntiles)
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            c = cell + dx * G + dy
            nt = grid[c] - 1
            if nt < 0:
                continue
            mp = mpiece[tg[nt]]
            if mp < 0:
                continue
            r = find(parent, nt * P + mp)
            if meep[r * 2] + meep[r * 2 + 1] > 0 and surrounded(S, c):
                award(S, r, 9)


@njit(cache=True)
def end_points(S, T, P, pts):
    """今終局した場合の各根の得点を pts[root] に書く（ミープルのいる特徴のみ。状態は変更しない）。"""
    grid, tg, tcell, parent, opn, tlo, thi, pen, meep = (
        S[0],
        S[1],
        S[2],
        S[3],
        S[5],
        S[7],
        S[8],
        S[6],
        S[9],
    )
    n_placed = S[10][SC_N]
    npc, pkind, cadj = T[1], T[2], T[7]
    for t in range(n_placed):
        g = tg[t]
        for i in range(npc[g]):
            n = t * P + i
            r = find(parent, n)
            if meep[r * 2] + meep[r * 2 + 1] == 0:
                continue
            k = pkind[g, i]
            if k == 0:
                pts[r] = popcnt(tlo[r]) + popcnt(thi[r]) + pen[r]
            elif k == 1:
                pts[r] = popcnt(tlo[r]) + popcnt(thi[r])
            elif k == 3:
                around = 0
                c = tcell[t]
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        if (dx != 0 or dy != 0) and grid[c + dx * G + dy] != 0:
                            around += 1
                pts[r] = 1 + around
    # 農民: 隣接する完成都市（別々の根）の数 × 3
    pair_c = np.empty(NT * P, np.int32)
    pair_f = np.empty(NT * P, np.int32)
    npairs = 0
    for t in range(n_placed):
        g = tg[t]
        for i in range(npc[g]):
            if pkind[g, i] != 0:
                continue
            cr = find(parent, t * P + i)
            if opn[cr] != 0:
                continue
            for j in range(npc[g]):
                if (cadj[g, i] >> j) & 1:
                    fr = find(parent, t * P + j)
                    if meep[fr * 2] + meep[fr * 2 + 1] == 0:
                        continue
                    dup = False
                    for q in range(npairs):
                        if pair_c[q] == cr and pair_f[q] == fr:
                            dup = True
                            break
                    if not dup:
                        pair_c[npairs] = cr
                        pair_f[npairs] = fr
                        npairs += 1
                        pts[fr] += 3
    return 0


@njit(cache=True)
def finish(S, T, P):
    sc = S[10]
    sc[SC_OVER] = 1
    NN = NT * P
    pts = np.zeros(NN, np.int32)
    end_points(S, T, P, pts)
    parent = S[3]
    n_placed = sc[SC_N]
    tg, npc, meep = S[1], T[1], S[9]
    # 各根を1回だけ得点（根のノード番号が小さい順に）
    for t in range(n_placed):
        for i in range(npc[tg[t]]):
            n = t * P + i
            r = find(parent, n)
            if r == n and meep[r * 2] + meep[r * 2 + 1] > 0:
                award(S, r, pts[r])


@njit(cache=True)
def projected(S, T, P):
    """今終局した場合の得点 (s0, s1)。状態は変更しない。"""
    sc = S[10]
    s0 = sc[SC_S0]
    s1 = sc[SC_S1]
    if sc[SC_OVER] == 1:
        return s0, s1
    NN = NT * P
    pts = np.zeros(NN, np.int32)
    end_points(S, T, P, pts)
    parent, meep, tg, npc = S[3], S[9], S[1], T[1]
    for t in range(sc[SC_N]):
        for i in range(npc[tg[t]]):
            n = t * P + i
            r = find(parent, n)
            if r == n:
                m0 = meep[r * 2]
                m1 = meep[r * 2 + 1]
                top = max(m0, m1)
                if top > 0:
                    if m0 == top:
                        s0 += pts[r]
                    if m1 == top:
                        s1 += pts[r]
    return s0, s1


@njit(cache=True)
def draw(S, T, P, stamp, stamp_box, out_cell, out_g):
    """置ける次のタイルを引く（置けないものは捨てる）。山札切れなら終局処理。"""
    sc, deck = S[10], S[11]
    ndeck = NT - 1
    while sc[SC_DRAW] < ndeck:
        ti = deck[sc[SC_DRAW]]
        sc[SC_DRAW] += 1
        stamp_box[0] += 1
        if gen_placements(S, T, ti, stamp, stamp_box[0], out_cell, out_g, True) > 0:
            sc[SC_CUR] = ti
            return
        sc[SC_DISC] += 1
    sc[SC_CUR] = -1
    finish(S, T, P)


@njit(cache=True)
def apply_move(S, T, P, cell, g, piece, stamp, stamp_box, out_cell, out_g):
    """配置＋ミープルを適用する（合法性は呼び出し側が保証）。"""
    sc = S[10]
    player = sc[SC_PL]
    place_tile(S, T, P, cell, g)
    if piece >= 0:
        t = S[0][cell] - 1
        r = find(S[3], t * P + piece)
        S[9][r * 2 + player] += 1
        sc[SC_SUP0 + player] -= 1
    score_after_placement(S, T, P, cell, g)
    sc[SC_PL] = 1 - player
    draw(S, T, P, stamp, stamp_box, out_cell, out_g)


@njit(cache=True)
def init_game(S, T, P, deck, start_ti, stamp, stamp_box, out_cell, out_g):
    sc = S[10]
    sc[SC_SUP0] = MEEPLES
    sc[SC_SUP1] = MEEPLES
    for i in range(NT - 1):
        S[11][i] = deck[i]
    place_tile(S, T, P, C0 * G + C0, T[11][start_ti])
    draw(S, T, P, stamp, stamp_box, out_cell, out_g)


@njit(cache=True)
def random_move(S, T, P, meeple_prob, stamp, stamp_box, out_cell, out_g, free):
    """ロールアウト用: 配置は一様、ミープルは確率 meeple_prob で置ける断片から一様。"""
    sc = S[10]
    ti = sc[SC_CUR]
    stamp_box[0] += 1
    k = gen_placements(S, T, ti, stamp, stamp_box[0], out_cell, out_g, False)
    j = np.random.randint(0, k)
    cell = out_cell[j]
    g = out_g[j]
    piece = -1
    if sc[SC_SUP0 + sc[SC_PL]] > 0 and np.random.random() < meeple_prob:
        nf = 0
        for pi in range(T[1][g]):
            if piece_free(S, T, P, cell, g, pi):
                free[nf] = pi
                nf += 1
        if nf > 0:
            piece = free[np.random.randint(0, nf)]
    return cell, g, piece


@njit(cache=True)
def rollout(S, T, P, meeple_prob, max_steps, stamp, stamp_box, out_cell, out_g, free, rec):
    """S を破壊的に進める。max_steps<0で終局まで。戻り値は（予測）得点 (s0, s1)。

    rec[k] = (マス, 向きID, 断片) として着手を記録する（検証用。rec は NT 行以上）。
    """
    sc = S[10]
    steps = 0
    while sc[SC_OVER] == 0:
        if max_steps >= 0 and steps >= max_steps:
            return projected(S, T, P)
        cell, g, piece = random_move(S, T, P, meeple_prob, stamp, stamp_box, out_cell, out_g, free)
        rec[steps, 0] = cell
        rec[steps, 1] = g
        rec[steps, 2] = piece
        apply_move(S, T, P, cell, g, piece, stamp, stamp_box, out_cell, out_g)
        steps += 1
    return sc[SC_S0], sc[SC_S1]


@njit(cache=True)
def seed_rng(seed):
    np.random.seed(seed)


class Scratch:
    """スレッド/プロセスごとの作業用バッファ（状態には含めない）。"""

    def __init__(self) -> None:
        self.stamp = np.zeros(G * G, np.int32)
        self.stamp_box = np.zeros(1, np.int32)
        self.out_cell = np.zeros(G * G // 4, np.int32)
        self.out_g = np.zeros(G * G // 4, np.int16)
        self.free = np.zeros(16, np.int32)
        self.rec = np.zeros((NT, 3), np.int32)


class Fast:
    """テーブルと作業用バッファを束ねたラッパ。"""

    def __init__(self, ts: TileSet | None = None) -> None:
        self.ts = ts or load_tileset()
        self.T = build_tables(self.ts)
        self.P = int(self.T[2].shape[1])
        self.scratch = Scratch()

    def new_game(self, deck: list[int]):
        """山札（開始タイルを除く71枚の種別index）から初期状態を作る。"""
        S = make_state(self.P)
        sc = self.scratch
        init_game(
            S,
            self.T,
            self.P,
            np.array(deck, np.int8),
            self.ts.start,
            sc.stamp,
            sc.stamp_box,
            sc.out_cell,
            sc.out_g,
        )
        return S

    def apply(self, S, x: int, y: int, ti: int, vi: int, piece: int | None) -> None:
        sc = self.scratch
        cell = (x + C0) * G + (y + C0)
        g = int(self.T[11][ti]) + vi
        apply_move(
            S,
            self.T,
            self.P,
            cell,
            g,
            -1 if piece is None else piece,
            sc.stamp,
            sc.stamp_box,
            sc.out_cell,
            sc.out_g,
        )

    def rollout(self, S, meeple_prob: float = 0.3, max_steps: int = -1):
        sc = self.scratch
        return rollout(
            S,
            self.T,
            self.P,
            meeple_prob,
            max_steps,
            sc.stamp,
            sc.stamp_box,
            sc.out_cell,
            sc.out_g,
            sc.free,
            sc.rec,
        )
