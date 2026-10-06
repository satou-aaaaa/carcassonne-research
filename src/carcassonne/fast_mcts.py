"""Numba上で動く決定化MCTS（配置→ミープルの2段木、根並列の決定化）。

`mcts.py` の `MCTSAgent(factored=True)` と同じアルゴリズムを、木・状態・ロールアウトすべて
配列で実装して高速化したもの。木の節点は状態を持たず、各反復で根の状態を複製して選択経路の
着手を再生する（メモリ軽量）。

参考: Ameneyro et al. (2020) https://arxiv.org/abs/2009.12974 、
Jappert (2022) https://ai.dmi.unibas.ch/papers/theses/jappert-bachelor-22.pdf
"""

from __future__ import annotations

import random

import numpy as np
from numba import njit

from .fast import (
    C0,
    NT,
    SC_CUR,
    SC_DRAW,
    SC_OVER,
    SC_PL,
    SC_S0,
    SC_S1,
    SC_SUP0,
    Fast,
    G,
    apply_move,
    copy_state,
    gen_placements,
    piece_free,
    rollout,
    seed_rng,
)
from .fast_eval import NF, eval_value, features, load_eval
from .state import Move, State


@njit(cache=True)
def copy_into(dst, src):
    # 異種タプルは実行時の添字で引けないため、展開して書く
    dst[0][:] = src[0]
    dst[1][:] = src[1]
    dst[2][:] = src[2]
    dst[3][:] = src[3]
    dst[4][:] = src[4]
    dst[5][:] = src[5]
    dst[6][:] = src[6]
    dst[7][:] = src[7]
    dst[8][:] = src[8]
    dst[9][:] = src[9]
    dst[10][:] = src[10]
    dst[11][:] = src[11]


@njit(cache=True)
def shuffle_rest(S):
    """山札の未公開部分（引き済みの手元タイルを除く残り）をその場でシャッフルする。"""
    deck = S[11]
    lo = S[10][SC_DRAW]
    for i in range(NT - 2, lo, -1):
        j = np.random.randint(lo, i + 1)
        tmp = deck[i]
        deck[i] = deck[j]
        deck[j] = tmp


@njit(cache=True)
def reward_of(diff, scale):
    """mover視点の（予測）得点差 diff を [0,1] の報酬に変換する。scale<=0 なら勝敗報酬。"""
    if scale <= 0.0:
        if diff > 0:
            return 1.0
        if diff == 0:
            return 0.5
        return 0.0
    return 0.5 + 0.5 * np.tanh(diff / scale)


@njit(cache=True)
def run_tree(
    root,
    T,
    P,
    sims,
    c,
    scale,
    meeple_prob,
    depth,
    stamp,
    stamp_box,
    out_cell,
    out_g,
    free,
    rec,
    W,
    agg1,
    agg2,
    rp_cell,
    rp_g,
    nrp,
    eval_w,
    eval_mode,
    fbuf,
    chance,
):
    """1本の木を `sims` 回反復し、根の訪問数を agg1/agg2 に加算する。

    chance=1 のときは確率節点（タイル引き）を持つ木にする: 反復ごとに山札の未公開部分を
    引き直し、ミープル節点の次に「引いたタイル種別」を鍵とする確率節点を挟む。
    chance=0 は従来どおり、木ごとに固定した1つの山札並びで進める（将来のタイルが木に漏れる）。
    """
    N = 2 * sims + 4
    POOL = (sims + 2) * 160
    par = np.full(N, -1, np.int32)
    fch = np.full(N, -1, np.int32)
    nxt = np.full(N, -1, np.int32)
    ntype = np.zeros(N, np.int8)
    kcell = np.zeros(N, np.int32)
    kg = np.zeros(N, np.int16)
    kpiece = np.full(N, -1, np.int16)
    ktile = np.full(N, -1, np.int16)
    vis = np.zeros(N, np.int32)
    wsum = np.zeros(N, np.float64)
    mover = np.full(N, -1, np.int8)
    ostart = np.zeros(N, np.int32)
    ocnt = np.full(N, -1, np.int32)
    opt_a = np.zeros(POOL, np.int32)
    opt_b = np.zeros(POOL, np.int16)
    pool_used = 0
    n_nodes = 1
    path = np.zeros(NT * 2 + 4, np.int32)
    wsc = W[10]
    for _ in range(sims):
        copy_into(W, root)
        if chance == 1:
            shuffle_rest(W)
        node = 0
        path[0] = 0
        plen = 1
        while True:
            t = ntype[node]
            if t == 2:  # 確率節点: 実際に引いたタイル種別の子へ進む（なければ作って葉にする）
                tile = wsc[SC_CUR]
                ch = fch[node]
                while ch >= 0 and ktile[ch] != tile:
                    ch = nxt[ch]
                if ch >= 0:
                    node = ch
                    path[plen] = node
                    plen += 1
                    continue
                new = n_nodes
                n_nodes += 1
                par[new] = node
                nxt[new] = fch[node]
                fch[node] = new
                mover[new] = wsc[SC_PL]
                ntype[new] = 0
                ktile[new] = tile
                path[plen] = new
                plen += 1
                node = new
                break
            if ocnt[node] < 0:  # 選択肢の初期化
                ostart[node] = pool_used
                cnt = 0
                if t == 0:
                    if wsc[SC_OVER] == 0:
                        stamp_box[0] += 1
                        k = gen_placements(
                            W, T, wsc[SC_CUR], stamp, stamp_box[0], out_cell, out_g, False
                        )
                        for j in range(k):
                            if pool_used + cnt < POOL:
                                opt_a[pool_used + cnt] = out_cell[j]
                                opt_b[pool_used + cnt] = out_g[j]
                                cnt += 1
                else:
                    opt_a[pool_used + cnt] = -1
                    cnt += 1
                    if wsc[SC_SUP0 + wsc[SC_PL]] > 0:  # 断片数は高々9なのでプールは溢れない
                        for pi in range(T[1][kg[node]]):
                            if piece_free(W, T, P, kcell[node], kg[node], pi):
                                opt_a[pool_used + cnt] = pi
                                cnt += 1
                pool_used += cnt
                ocnt[node] = cnt
            if ocnt[node] > 0:  # 展開
                cnt = ocnt[node]
                idx = np.random.randint(0, cnt)
                a = opt_a[ostart[node] + idx]
                b = opt_b[ostart[node] + idx]
                opt_a[ostart[node] + idx] = opt_a[ostart[node] + cnt - 1]
                opt_b[ostart[node] + idx] = opt_b[ostart[node] + cnt - 1]
                ocnt[node] = cnt - 1
                new = n_nodes
                n_nodes += 1
                par[new] = node
                nxt[new] = fch[node]
                fch[node] = new
                mover[new] = wsc[SC_PL]
                if t == 0:
                    ntype[new] = 1
                    kcell[new] = a
                    kg[new] = b
                else:
                    ntype[new] = 2 if chance == 1 else 0
                    kpiece[new] = a
                    apply_move(W, T, P, kcell[node], kg[node], a, stamp, stamp_box, out_cell, out_g)
                path[plen] = new
                plen += 1
                node = new
                if t == 1 and chance == 1:
                    continue  # 確率節点を解決して、その先の葉まで進める
                break
            if fch[node] < 0:  # 終端（選択肢なし）
                break
            # 選択（UCT）
            best = -1
            bv = -1e30
            ln = np.log(vis[node] + 1.0)
            ch = fch[node]
            while ch >= 0:
                v = wsum[ch] / vis[ch] + c * np.sqrt(ln / vis[ch])
                if v > bv:
                    bv = v
                    best = ch
                ch = nxt[ch]
            if t == 1:
                apply_move(
                    W, T, P, kcell[node], kg[node], kpiece[best], stamp, stamp_box, out_cell, out_g
                )
            node = best
            path[plen] = node
            plen += 1
        # 評価
        if ntype[node] == 1:  # ミープル節点が葉: ミープルなしで置いた後を評価
            apply_move(W, T, P, kcell[node], kg[node], -1, stamp, stamp_box, out_cell, out_g)
        v0 = 0.0
        if eval_mode >= 1 and wsc[SC_OVER] == 0:
            # 学習型評価関数: depth手のロールアウトで進めた後の局面を線形モデルで評価する
            if depth > 0:
                rollout(W, T, P, meeple_prob, depth, stamp, stamp_box, out_cell, out_g, free, rec)
            if wsc[SC_OVER] == 0:
                features(W, T, P, 0, fbuf)
                v0 = eval_value(eval_w, eval_mode, fbuf)
                features(W, T, P, 1, fbuf)
                v1m = eval_value(eval_w, eval_mode, fbuf)
            else:
                v0 = float(wsc[SC_S0] - wsc[SC_S1])
                v1m = -v0
        else:
            if wsc[SC_OVER] == 1:
                s0 = wsc[SC_S0]
                s1 = wsc[SC_S1]
            else:
                s0, s1 = rollout(
                    W, T, P, meeple_prob, depth, stamp, stamp_box, out_cell, out_g, free, rec
                )
            v0 = float(s0 - s1)
            v1m = -v0
        for q in range(plen):
            nd = path[q]
            vis[nd] += 1
            if mover[nd] >= 0:
                wsum[nd] += reward_of(v0 if mover[nd] == 0 else v1m, scale)
    # 根の訪問数を集計
    ch = fch[0]
    while ch >= 0:
        for k in range(nrp):
            if rp_cell[k] == kcell[ch] and rp_g[k] == kg[ch]:
                agg1[k] += vis[ch]
                gc = fch[ch]
                while gc >= 0:
                    agg2[k, kpiece[gc] + 1] += vis[gc]
                    gc = nxt[gc]
                break
        ch = nxt[ch]
    return 0


@njit(cache=True)
def search(
    S,
    T,
    P,
    n_sims,
    n_det,
    c,
    scale,
    meeple_prob,
    depth,
    stamp,
    stamp_box,
    out_cell,
    out_g,
    free,
    rec,
    eval_w,
    eval_mode,
    fbuf,
    chance,
):
    """根局面 S から決定化MCTSを行い、(マス, 向きID, 断片) を返す。"""
    sc = S[10]
    stamp_box[0] += 1
    k = gen_placements(S, T, sc[SC_CUR], stamp, stamp_box[0], out_cell, out_g, False)
    rp_cell = out_cell[:k].copy()
    rp_g = out_g[:k].copy()
    agg1 = np.zeros(k, np.int64)
    agg2 = np.zeros((k, P + 1), np.int64)
    sims = max(1, n_sims // n_det)
    W = copy_state(S)
    D = copy_state(S)
    for _ in range(n_det):
        copy_into(D, S)
        # 山札の未公開部分（引き済みの手元タイルを除く残り）をシャッフル
        deck = D[11]
        lo = D[10][SC_DRAW]
        for i in range(NT - 2, lo, -1):
            j = np.random.randint(lo, i + 1)
            tmp = deck[i]
            deck[i] = deck[j]
            deck[j] = tmp
        run_tree(
            D, T, P, sims, c, scale, meeple_prob, depth, stamp, stamp_box,
            out_cell, out_g, free, rec, W, agg1, agg2, rp_cell, rp_g, k,
            eval_w, eval_mode, fbuf, chance,
        )  # fmt: skip
    top = agg1.max()
    cands = np.where(agg1 == top)[0]
    bk = cands[np.random.randint(0, len(cands))]
    bp = -1
    best2 = 0
    for q in range(P + 1):
        if agg2[bk, q] > best2:
            best2 = agg2[bk, q]
            bp = q - 1
    return rp_cell[bk], rp_g[bk], bp


class FastMCTSAgent:
    """`MCTSAgent` と同じ探索をNumbaで行うエージェント（Pythonの `State` に着手を返す）。"""

    def __init__(
        self,
        n_sims: int = 1000,
        n_det: int = 1,
        c: float = 0.5,
        reward_scale: float | None = 30.0,
        meeple_prob: float = 0.3,
        rollout_depth: int | None = None,
        eval_path: str | None = None,
        chance: bool = True,
    ) -> None:
        """eval_path に線形評価関数の重み(.npy)を渡すと、葉をその評価関数で評価する。

        その場合 rollout_depth は評価前に進めるランダム手数（未指定は0=評価のみ）。
        chance=True で、タイル引きを確率節点としてモデル化する（False は従来の固定山札）。
        """
        self.chance = chance
        self.n_sims = n_sims
        self.n_det = n_det
        self.c = c
        self.reward_scale = reward_scale
        self.meeple_prob = meeple_prob
        self.rollout_depth = rollout_depth
        self.eval_path = eval_path
        self.eval_w, self.eval_mode = load_eval(eval_path) if eval_path else (np.zeros(NF), 0)
        self.fbuf = np.zeros(NF)
        self.fast = Fast()
        tag = f",eval={eval_path.replace(chr(92), '/').split('/')[-1]}" if eval_path else ""
        self.name = (
            f"fastmcts(sims={n_sims},det={n_det},c={c:g},scale={reward_scale},"
            f"mp={meeple_prob:g},depth={rollout_depth}{tag}{'' if chance else ',nochance'})"
        )

    def to_fast(self, state: State):
        """Pythonの State を、着手履歴の再生でNumba状態へ変換する。"""
        S = self.fast.new_game(state.deck)
        for x, y, ti, vi, piece in state.history:
            self.fast.apply(S, x, y, ti, vi, piece)
        return S

    def choose(self, S):
        """Numba状態 S（手番側が指す局面）から (マス, 向きID, 断片) を返す。乱数は seed_rng 済みとする。"""
        depth = (
            self.rollout_depth if self.rollout_depth is not None else (0 if self.eval_path else -1)
        )
        sc = self.fast.scratch
        cell, g, piece = search(
            S,
            self.fast.T,
            self.fast.P,
            self.n_sims,
            self.n_det,
            self.c,
            -1.0 if self.reward_scale is None else self.reward_scale,
            self.meeple_prob,
            depth,
            sc.stamp,
            sc.stamp_box,
            sc.out_cell,
            sc.out_g,
            sc.free,
            sc.rec,
            self.eval_w,
            self.eval_mode,
            self.fbuf,
            1 if self.chance else 0,
        )
        return int(cell), int(g), int(piece)

    def act(self, state: State, rng: random.Random) -> Move:
        moves = state.legal_moves()
        if len(moves) == 1:
            return moves[0]
        seed_rng(rng.getrandbits(31))
        cell, g, piece = self.choose(self.to_fast(state))
        vi = g - int(self.fast.T[11][state.current])
        return Move(cell // G - C0, cell % G - C0, vi, None if piece < 0 else piece)
