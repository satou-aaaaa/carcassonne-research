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
    aggw1,
    aggw2,
    rp_cell,
    rp_g,
    nrp,
    eval_w,
    eval_mode,
    fbuf,
    late,
    fpu,
    prior_visits,
    root_allow,
):
    """1本の木を `sims` 回反復し、根の訪問数を agg1/agg2 に、報酬和を aggw1/aggw2 に加算する。

    fpu<0 なら、子をすべて1回ずつ試してから UCT で選ぶ（従来）。fpu>=0 なら、未展開の子を
    「既存の子の平均報酬−fpu を1回観測した子」とみなし、既存の子の UCT 値がそれ以上なら
    展開せずに既存の子へ進む（first-play urgency）。良い手が見つかった節点では、残りの手を
    すべて試す前にその手を深く読む。

    prior_visits>0 なら、配置の節点の訪問数がこの値に達した時点で、残りの未展開の配置を
    「ミープルなしで置いた直後の評価値」の高い順に並べ、以後は良さそうな手から展開する
    （手の事前確率の代わり。評価関数があるときだけ）。fpu と組み合わせて使う。

    root_allow が空でなければ、根では `マス*256+向きID` がこの中にある配置だけを試す
    （方策ネットの上位の手に絞る）。
    """
    N = sims + 2
    POOL = N * 160
    par = np.full(N, -1, np.int32)
    fch = np.full(N, -1, np.int32)
    nxt = np.full(N, -1, np.int32)
    ntype = np.zeros(N, np.int8)
    kcell = np.zeros(N, np.int32)
    kg = np.zeros(N, np.int16)
    kpiece = np.full(N, -1, np.int16)
    vis = np.zeros(N, np.int32)
    wsum = np.zeros(N, np.float64)
    mover = np.full(N, -1, np.int8)
    ostart = np.zeros(N, np.int32)
    ocnt = np.full(N, -1, np.int32)
    opt_a = np.zeros(POOL, np.int32)
    opt_b = np.zeros(POOL, np.int16)
    opt_p = np.zeros(POOL, np.float64)
    ranked = np.zeros(N, np.bool_)
    X = copy_state(root)
    pool_used = 0
    n_nodes = 1
    path = np.zeros(NT * 2 + 4, np.int32)
    wsc = W[10]
    for _ in range(sims):
        copy_into(W, root)
        node = 0
        path[0] = 0
        plen = 1
        while True:
            t = ntype[node]
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
                            if node == 0 and len(root_allow) > 0:
                                code = out_cell[j] * 256 + out_g[j]
                                ok = False
                                for q in range(len(root_allow)):
                                    if root_allow[q] == code:
                                        ok = True
                                        break
                                if not ok:
                                    continue
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
            expand = ocnt[node] > 0
            if expand and fpu >= 0.0 and fch[node] >= 0:
                # 既存の子の最良 UCT 値と、未展開の子の見込み値を比べる
                ln = np.log(vis[node] + 1.0)
                sw = 0.0
                sv = 0
                bv = -1e30
                ch = fch[node]
                while ch >= 0:
                    sw += wsum[ch]
                    sv += vis[ch]
                    v = wsum[ch] / vis[ch] + c * np.sqrt(ln / vis[ch])
                    bv = max(bv, v)
                    ch = nxt[ch]
                if bv >= sw / sv - fpu + c * np.sqrt(ln):
                    expand = False
            if expand:  # 展開
                cnt = ocnt[node]
                o = ostart[node]
                if t == 0 and not ranked[node] and 0 < prior_visits <= vis[node] and eval_mode >= 1:
                    # 残りの配置を、ミープルなしで置いた直後の評価値（手番側視点）で採点する
                    me = wsc[SC_PL]
                    for j in range(cnt):
                        copy_into(X, W)
                        apply_move(
                            X, T, P, opt_a[o + j], opt_b[o + j], -1, stamp, stamp_box,
                            out_cell, out_g,
                        )  # fmt: skip
                        features(X, T, P, me, fbuf)
                        opt_p[o + j] = eval_value(eval_w, eval_mode, fbuf)
                    ranked[node] = True
                if ranked[node]:
                    idx = 0
                    for j in range(1, cnt):
                        if opt_p[o + j] > opt_p[o + idx]:
                            idx = j
                else:
                    idx = np.random.randint(0, cnt)
                a = opt_a[o + idx]
                b = opt_b[o + idx]
                opt_a[o + idx] = opt_a[o + cnt - 1]
                opt_b[o + idx] = opt_b[o + cnt - 1]
                opt_p[o + idx] = opt_p[o + cnt - 1]
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
                    ntype[new] = 0
                    kpiece[new] = a
                    apply_move(W, T, P, kcell[node], kg[node], a, stamp, stamp_box, out_cell, out_g)
                path[plen] = new
                plen += 1
                node = new
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
        use_eval = eval_mode >= 1 and (NT - 1 - wsc[SC_DRAW]) > late
        if use_eval and wsc[SC_OVER] == 0:
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
                # 評価関数を使わない葉（終盤の late 枚以下、または評価関数なし）は終局までロールアウト
                rd = -1 if eval_mode >= 1 else depth
                s0, s1 = rollout(
                    W, T, P, meeple_prob, rd, stamp, stamp_box, out_cell, out_g, free, rec
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
                aggw1[k] += wsum[ch]
                gc = fch[ch]
                while gc >= 0:
                    agg2[k, kpiece[gc] + 1] += vis[gc]
                    aggw2[k, kpiece[gc] + 1] += wsum[gc]
                    gc = nxt[gc]
                break
        ch = nxt[ch]
    return 0


@njit(cache=True)
def search_stats(
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
    late,
    fpu,
    prior_visits,
    root_allow,
):
    """根局面 S から決定化MCTSを行い、根の候補ごとの訪問数と報酬和を返す。

    戻り値は (マス, 向きID, 配置の訪問数, 配置の報酬和, 断片別の訪問数, 断片別の報酬和)。
    断片別の配列の列 q は断片 q-1（列0はミープルなし）。報酬は手番側視点。
    """
    sc = S[10]
    stamp_box[0] += 1
    k = gen_placements(S, T, sc[SC_CUR], stamp, stamp_box[0], out_cell, out_g, False)
    rp_cell = out_cell[:k].copy()
    rp_g = out_g[:k].copy()
    agg1 = np.zeros(k, np.int64)
    agg2 = np.zeros((k, P + 1), np.int64)
    aggw1 = np.zeros(k, np.float64)
    aggw2 = np.zeros((k, P + 1), np.float64)
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
            out_cell, out_g, free, rec, W, agg1, agg2, aggw1, aggw2, rp_cell, rp_g, k,
            eval_w, eval_mode, fbuf, late, fpu, prior_visits, root_allow,
        )  # fmt: skip
    return rp_cell, rp_g, agg1, aggw1, agg2, aggw2


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
    late,
    fpu,
    prior_visits,
    root_allow,
):
    """根局面 S から決定化MCTSを行い、(マス, 向きID, 断片) を返す。"""
    rp_cell, rp_g, agg1, _, agg2, _ = search_stats(
        S, T, P, n_sims, n_det, c, scale, meeple_prob, depth, stamp, stamp_box,
        out_cell, out_g, free, rec, eval_w, eval_mode, fbuf, late, fpu, prior_visits,
        root_allow,
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
        late: int = 0,
        fpu: float = -1.0,
        prior_visits: int = 0,
        nn_path: str | None = None,
        nn_topk: int = 8,
    ) -> None:
        """eval_path に線形評価関数の重み(.npy)を渡すと、葉をその評価関数で評価する。

        その場合 rollout_depth は評価前に進めるランダム手数（未指定は0=評価のみ）。
        """
        self.n_sims = n_sims
        self.n_det = n_det
        self.c = c
        self.reward_scale = reward_scale
        self.meeple_prob = meeple_prob
        self.rollout_depth = rollout_depth
        self.eval_path = eval_path
        # 残りタイルがこの枚数以下の局面は、評価関数でなく終局までのロールアウトで評価する
        self.late = late
        # 0以上で first-play urgency を使う（`run_tree` を参照）。負なら従来どおり全手を一度ずつ試す
        self.fpu = fpu
        # 0より大きいと、訪問数がこの値に達した配置の節点で未展開の手を評価値順に並べる
        self.prior_visits = prior_visits
        # 方策ネット（`nn_model.py`）があれば、根を方策の上位 nn_topk 手に絞る
        self.nn = None
        self.nn_topk = nn_topk
        if nn_path:
            from .nn_model import PolicyValueNet

            self.nn = PolicyValueNet(nn_path)
        self.eval_w, self.eval_mode = load_eval(eval_path) if eval_path else (np.zeros(NF), 0)
        self.fbuf = np.zeros(NF)
        self.fast = Fast()
        tag = f",eval={eval_path.replace(chr(92), '/').split('/')[-1]}" if eval_path else ""
        self.name = (
            f"fastmcts(sims={n_sims},det={n_det},c={c:g},scale={reward_scale},"
            f"mp={meeple_prob:g},depth={rollout_depth}{tag}"
            + (f",late={late}" if late else "")
            + (f",fpu={fpu:g}" if fpu >= 0 else "")
            + (f",pv={prior_visits}" if prior_visits else "")
            + (
                f",nn={nn_path.replace(chr(92), '/').split('/')[-1]},topk={nn_topk}"
                if nn_path
                else ""
            )
            + ")"
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
            self.late,
            self.fpu,
            self.prior_visits,
            self.root_allow(S),
        )
        return int(cell), int(g), int(piece)

    def root_allow(self, S) -> np.ndarray:
        """方策ネットの上位 nn_topk 手（`マス*256+向きID`）。ネットが無ければ空（全手を試す）。"""
        if self.nn is None:
            return np.zeros(0, np.int64)
        from .nn_encode import NC, NG, R, encode

        sc = self.fast.scratch
        planes = np.zeros((NC, R, R), np.float32)
        glob = np.zeros(NG, np.float32)
        x0, y0, k = encode(
            S, self.fast.T, self.fast.P, sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g,
            planes, glob, np.zeros(NF),
        )  # fmt: skip
        logits, _ = self.nn.forward(planes[None], glob[None])
        logits = logits[0]
        ti = int(S[10][SC_CUR])
        vb = int(self.fast.T[11][ti])
        codes = []
        outside = []
        for j in range(k):
            cell, g = int(sc.out_cell[j]), int(sc.out_g[j])
            x, y = cell // G - x0, cell % G - y0
            if 0 <= x < R and 0 <= y < R:
                codes.append((logits[(g - vb) * R * R + x * R + y], cell * 256 + g))
            else:
                outside.append(cell * 256 + g)  # 切り出しの外の手は方策が無いので残す
        codes.sort(reverse=True)
        return np.array([c for _, c in codes[: self.nn_topk]] + outside, np.int64)

    def act(self, state: State, rng: random.Random) -> Move:
        moves = state.legal_moves()
        if len(moves) == 1:
            return moves[0]
        seed_rng(rng.getrandbits(31))
        cell, g, piece = self.choose(self.to_fast(state))
        vi = g - int(self.fast.T[11][state.current])
        return Move(cell // G - C0, cell % G - C0, vi, None if piece < 0 else piece)
