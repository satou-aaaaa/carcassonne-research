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
    SC_END,
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
    chance,
    farm=True,
    rshuf=0,
    puct=0.0,
    pply=1,
    ptau=3.0,
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

    chance=1 のときは確率節点（タイル引き）を持つ木にする: 反復ごとに山札の未公開部分を
    引き直し、ミープル節点の次に「引いたタイル種別」を鍵とする確率節点を挟む。
    chance=0 は従来どおり、木ごとに固定した1つの山札並びで進める（将来のタイルが木に漏れる）。

    farm=False なら、ロールアウトでは草原にミープルを置かない。

    rshuf=1 なら、木の中（chance=0 の固定山札）はそのままに、葉から先のロールアウトの前に山札の未公開部分を
    引き直す。木ごとに1つの山札並びに合わせて手を選ぶ偏りを、木の統計を分散させずに減らす。

    puct>0 なら、根から pply 手番ぶんの配置の節点で PUCT（Silver et al. 2017 の式）を使う。選択肢を
    初めて作るときに各配置を「ミープルなしで置いた直後の評価値（手番側視点、点）」で採点し、softmax(値/ptau)
    を事前確率 P にする。子の選択は Q + puct*P*sqrt(N)/(1+n)。未展開の手は事前確率の一番高いものを
    「既存の子の平均報酬−max(fpu,0)」を見込み値として同じ式で比べ、勝てば展開する。評価関数があり
    chance=0 のときだけ。それ以外の節点は従来の UCT のまま。
    """
    # 確率節点ありでは1反復で最大2節点（ミープル節点の子の確率節点＋その先の配置節点）増える
    N = 2 * sims + 4 if chance == 1 else sims + 2
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
    opt_p = np.zeros(POOL, np.float64)
    ranked = np.zeros(N, np.bool_)
    pnode = np.zeros(N, np.bool_)  # PUCT で選ぶ配置の節点
    pdep = np.zeros(N, np.int32)  # 根からの経路上の深さ（配置・ミープルの節点を数える）
    cpri = np.zeros(N, np.float64)  # PUCT の節点の子の事前確率
    use_puct = puct > 0.0 and eval_mode != 0 and chance == 0
    X = copy_state(root)
    pool_used = 0
    n_nodes = 1
    path = np.zeros(NT * 3 + 4, np.int32)  # 1手あたり 配置・ミープル・確率節点の高々3段
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
                if use_puct and t == 0 and cnt > 0 and pdep[node] <= 2 * (pply - 1):
                    # 事前確率: ミープルなしで置いた直後の評価値（手番側視点）の softmax
                    me = wsc[SC_PL]
                    o = ostart[node]
                    vmax = -1e30
                    for j in range(cnt):
                        copy_into(X, W)
                        apply_move(
                            X, T, P, opt_a[o + j], opt_b[o + j], -1, stamp, stamp_box,
                            out_cell, out_g,
                        )  # fmt: skip
                        features(X, T, P, me, fbuf)
                        opt_p[o + j] = eval_value(eval_w, eval_mode, fbuf)
                        vmax = max(vmax, opt_p[o + j])
                    zs = 0.0
                    for j in range(cnt):
                        opt_p[o + j] = np.exp((opt_p[o + j] - vmax) / ptau)
                        zs += opt_p[o + j]
                    for j in range(cnt):
                        opt_p[o + j] /= zs
                    ranked[node] = True
                    pnode[node] = True
            expand = ocnt[node] > 0
            pbest = -1
            if pnode[node]:
                if fch[node] >= 0:
                    sq = np.sqrt(vis[node] + 0.0)
                    sw = 0.0
                    sv = 0
                    bv = -1e30
                    ch = fch[node]
                    while ch >= 0:
                        sw += wsum[ch]
                        sv += vis[ch]
                        v = wsum[ch] / vis[ch] + puct * cpri[ch] * sq / (1.0 + vis[ch])
                        if v > bv:
                            bv = v
                            pbest = ch
                        ch = nxt[ch]
                    if expand:
                        o = ostart[node]
                        pm = 0.0
                        for j in range(ocnt[node]):
                            pm = max(pm, opt_p[o + j])
                        if bv >= sw / sv - max(fpu, 0.0) + puct * pm * sq:
                            expand = False
            elif expand and fpu >= 0.0 and fch[node] >= 0:
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
                if t == 0 and not ranked[node] and 0 < prior_visits <= vis[node] and eval_mode != 0:
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
                pa = opt_p[o + idx]
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
                pdep[new] = pdep[node] + 1
                if pnode[node]:
                    cpri[new] = pa
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
            # 選択（PUCT の節点は上で選んだ子、それ以外は UCT）
            best = pbest
            if best < 0:
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
        if rshuf == 1 and chance == 0:
            shuffle_rest(W)
        v0 = 0.0
        use_eval = eval_mode != 0 and (wsc[SC_END] - wsc[SC_DRAW]) > late
        if use_eval and wsc[SC_OVER] == 0:
            # 学習型評価関数: depth手のロールアウトで進めた後の局面を線形モデルで評価する
            if depth > 0:
                rollout(
                    W, T, P, meeple_prob, depth, stamp, stamp_box, out_cell, out_g, free, rec, farm
                )
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
                rd = -1 if eval_mode != 0 else depth
                s0, s1 = rollout(
                    W, T, P, meeple_prob, rd, stamp, stamp_box, out_cell, out_g, free, rec, farm
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
    chance=0,
    farm=True,
    rshuf=0,
    puct=0.0,
    pply=1,
    ptau=3.0,
):
    """根局面 S から決定化MCTSを行い、根の候補ごとの訪問数と報酬和を返す。

    戻り値は (マス, 向きID, 配置の訪問数, 配置の報酬和, 断片別の訪問数, 断片別の報酬和)。
    断片別の配列の列 q は断片 q-1（列0はミープルなし）。報酬は手番側視点。
    chance=1 で確率節点版の木にする（`run_tree` を参照）。
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
        shuffle_rest(D)
        run_tree(
            D, T, P, sims, c, scale, meeple_prob, depth, stamp, stamp_box,
            out_cell, out_g, free, rec, W, agg1, agg2, aggw1, aggw2, rp_cell, rp_g, k,
            eval_w, eval_mode, fbuf, late, fpu, prior_visits, root_allow, chance, farm, rshuf,
            puct, pply, ptau,
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
    chance=0,
    farm=True,
    rshuf=0,
    puct=0.0,
    pply=1,
    ptau=3.0,
):
    """根局面 S から決定化MCTSを行い、(マス, 向きID, 断片) を返す。"""
    rp_cell, rp_g, agg1, _, agg2, _ = search_stats(
        S, T, P, n_sims, n_det, c, scale, meeple_prob, depth, stamp, stamp_box,
        out_cell, out_g, free, rec, eval_w, eval_mode, fbuf, late, fpu, prior_visits,
        root_allow, chance, farm, rshuf, puct, pply, ptau,
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


@njit(cache=True)
def next_tile_value(
    S, T, P, cells, gs, pieces, eval_w, eval_mode, fbuf, stamp, stamp_box, out_cell, out_g
):
    """候補手ごとに、着手後に相手が引くタイル種別で平均した評価値（手番側視点の得点差）を返す。

    未公開タイルの種別ごとに、その種別を次に引いた局面を作り、相手視点の評価値の符号を反転して
    未公開の枚数で重み付け平均する。置けない種別（捨てられる）は省く。山札が尽きる手は実際の得点差。
    実際の山札の並び（`S[11]`）は使わない（次のタイルは種別ごとに入れ替えて作る）。
    """
    me = S[10][SC_PL]
    lo = S[10][SC_DRAW]
    out = np.zeros(len(cells))
    X = copy_state(S)
    seen = np.zeros(128, np.bool_)
    for ci in range(len(cells)):
        if lo >= S[10][SC_END]:  # この手で終局
            copy_into(X, S)
            apply_move(X, T, P, cells[ci], gs[ci], pieces[ci], stamp, stamp_box, out_cell, out_g)
            d = float(X[10][SC_S0] - X[10][SC_S1])
            out[ci] = d if me == 0 else -d
            continue
        seen[:] = False
        tot = 0.0
        wsum = 0.0
        for j in range(lo, NT - 1):
            t = S[11][j]
            if seen[t]:
                continue
            seen[t] = True
            n = 0
            for q in range(lo, NT - 1):
                if S[11][q] == t:
                    n += 1
            copy_into(X, S)
            X[11][lo] = t
            X[11][j] = S[11][lo]
            apply_move(X, T, P, cells[ci], gs[ci], pieces[ci], stamp, stamp_box, out_cell, out_g)
            if X[10][SC_OVER] != 0 or X[10][SC_CUR] != t or X[10][SC_DRAW] != lo + 1:
                continue
            features(X, T, P, 1 - me, fbuf)
            tot -= n * eval_value(eval_w, eval_mode, fbuf)
            wsum += n
        out[ci] = tot / wsum if wsum > 0 else np.nan
    return out


@njit(cache=True)
def next_tile_reply_value(
    S, T, P, cells, gs, pieces, eval_w, eval_mode, fbuf, stamp, stamp_box, out_cell, out_g
):
    """`next_tile_value` の2手版: 次に相手が引くタイル種別ごとに、相手の一番良い返し手（評価値で選ぶ）
    まで進めた局面の評価値（手番側視点の得点差）を、未公開の枚数で平均する。

    相手の返し手は配置×（ミープルなし＋置ける断片）をすべて試す。実際の山札の並びは使わない。
    """
    me = S[10][SC_PL]
    lo = S[10][SC_DRAW]
    out = np.zeros(len(cells))
    X = copy_state(S)
    Y = copy_state(S)
    seen = np.zeros(128, np.bool_)
    rc = np.zeros(len(out_cell), np.int32)
    rg = np.zeros(len(out_cell), np.int16)
    for ci in range(len(cells)):
        if lo >= S[10][SC_END]:  # この手で終局
            copy_into(X, S)
            apply_move(X, T, P, cells[ci], gs[ci], pieces[ci], stamp, stamp_box, out_cell, out_g)
            d = float(X[10][SC_S0] - X[10][SC_S1])
            out[ci] = d if me == 0 else -d
            continue
        seen[:] = False
        tot = 0.0
        wsum = 0.0
        for j in range(lo, NT - 1):
            t = S[11][j]
            if seen[t]:
                continue
            seen[t] = True
            n = 0
            for q in range(lo, NT - 1):
                if S[11][q] == t:
                    n += 1
            copy_into(X, S)
            X[11][lo] = t
            X[11][j] = S[11][lo]
            apply_move(X, T, P, cells[ci], gs[ci], pieces[ci], stamp, stamp_box, out_cell, out_g)
            if X[10][SC_OVER] != 0 or X[10][SC_CUR] != t or X[10][SC_DRAW] != lo + 1:
                continue
            opp = X[10][SC_PL]
            stamp_box[0] += 1
            k = gen_placements(X, T, t, stamp, stamp_box[0], out_cell, out_g, False)
            for q in range(k):
                rc[q] = out_cell[q]
                rg[q] = out_g[q]
            best = 1e30  # 手番側視点の値の最小（相手にとって最良）
            for q in range(k):
                npc = T[1][rg[q]] if X[10][SC_SUP0 + opp] > 0 else 0
                for pi in range(-1, npc):
                    if pi >= 0 and not piece_free(X, T, P, rc[q], rg[q], pi):
                        continue
                    copy_into(Y, X)
                    apply_move(Y, T, P, rc[q], rg[q], pi, stamp, stamp_box, out_cell, out_g)
                    if Y[10][SC_OVER] != 0:
                        d = float(Y[10][SC_S0] - Y[10][SC_S1])
                        v = d if me == 0 else -d
                    else:
                        features(Y, T, P, me, fbuf)
                        v = eval_value(eval_w, eval_mode, fbuf)
                    best = min(best, v)
            if best < 1e29:
                tot += n * best
                wsum += n
        out[ci] = tot / wsum if wsum > 0 else np.nan
    return out


@njit(cache=True)
def _side_best(Y, Z, T, P, me, eval_w, eval_mode, fbuf, stamp, stamp_box, out_cell, out_g, rc, rg):
    """局面 Y で手番の人が指せる全部の手（配置×ミープルなし・置ける断片）を評価関数で採点し、
    手番の人にとって一番良い値を、me 視点の得点差で返す（手番が me なら最大、相手なら最小）。
    終局する手は実際の得点差。合法手が無ければ nan。Z は作業用。"""
    mover = Y[10][SC_PL]
    t = Y[10][SC_CUR]
    stamp_box[0] += 1
    k = gen_placements(Y, T, t, stamp, stamp_box[0], out_cell, out_g, False)
    for q in range(k):
        rc[q] = out_cell[q]
        rg[q] = out_g[q]
    best = -1e30 if mover == me else 1e30
    found = False
    for q in range(k):
        npc = T[1][rg[q]] if Y[10][SC_SUP0 + mover] > 0 else 0
        for pi in range(-1, npc):
            if pi >= 0 and not piece_free(Y, T, P, rc[q], rg[q], pi):
                continue
            copy_into(Z, Y)
            apply_move(Z, T, P, rc[q], rg[q], pi, stamp, stamp_box, out_cell, out_g)
            if Z[10][SC_OVER] != 0:
                d = float(Z[10][SC_S0] - Z[10][SC_S1])
                v = d if me == 0 else -d
            else:
                features(Z, T, P, me, fbuf)
                v = eval_value(eval_w, eval_mode, fbuf)
            found = True
            if mover == me:
                best = max(best, v)
            else:
                best = min(best, v)
    return best if found else np.nan


@njit(cache=True)
def next_tile_reply2_value(
    S, T, P, cells, gs, pieces, eval_w, eval_mode, fbuf, stamp, stamp_box, out_cell, out_g, beam
):
    """`next_tile_reply_value` の3手版: 相手が引くタイル種別ごとに、相手の返し手のうち1手読みで良い
    上位 beam 手について、そのあと自分が引くタイル種別ごとの自分の一番良い手まで読み、
    自分のタイル種別で平均した値（手番側視点の得点差）を返し手の値とする。相手はその値が最小の
    返し手を選び、相手のタイル種別で平均する。実際の山札の並びは使わない（期待値を取る expectimax）。
    """
    me = S[10][SC_PL]
    lo = S[10][SC_DRAW]
    out = np.zeros(len(cells))
    X = copy_state(S)
    Y = copy_state(S)
    Z = copy_state(S)
    seen = np.zeros(128, np.bool_)
    seen2 = np.zeros(128, np.bool_)
    n_out = len(out_cell)
    rc = np.zeros(n_out, np.int32)
    rg = np.zeros(n_out, np.int16)
    rc2 = np.zeros(n_out, np.int32)
    rg2 = np.zeros(n_out, np.int16)
    m_cell = np.zeros(n_out * 6, np.int32)
    m_g = np.zeros(n_out * 6, np.int16)
    m_pi = np.zeros(n_out * 6, np.int32)
    m_v = np.zeros(n_out * 6)
    m_end = np.zeros(n_out * 6, np.bool_)
    for ci in range(len(cells)):
        if lo >= S[10][SC_END]:  # この手で終局
            copy_into(X, S)
            apply_move(X, T, P, cells[ci], gs[ci], pieces[ci], stamp, stamp_box, out_cell, out_g)
            d = float(X[10][SC_S0] - X[10][SC_S1])
            out[ci] = d if me == 0 else -d
            continue
        seen[:] = False
        tot = 0.0
        wsum = 0.0
        for j in range(lo, NT - 1):
            t = S[11][j]
            if seen[t]:
                continue
            seen[t] = True
            n = 0
            for q in range(lo, NT - 1):
                if S[11][q] == t:
                    n += 1
            copy_into(X, S)
            X[11][lo] = t
            X[11][j] = S[11][lo]
            apply_move(X, T, P, cells[ci], gs[ci], pieces[ci], stamp, stamp_box, out_cell, out_g)
            if X[10][SC_OVER] != 0 or X[10][SC_CUR] != t or X[10][SC_DRAW] != lo + 1:
                continue
            opp = X[10][SC_PL]
            # 相手の返し手を全部1手読みで採点する
            stamp_box[0] += 1
            k = gen_placements(X, T, t, stamp, stamp_box[0], out_cell, out_g, False)
            for q in range(k):
                rc[q] = out_cell[q]
                rg[q] = out_g[q]
            nm = 0
            for q in range(k):
                npc = T[1][rg[q]] if X[10][SC_SUP0 + opp] > 0 else 0
                for pi in range(-1, npc):
                    if pi >= 0 and not piece_free(X, T, P, rc[q], rg[q], pi):
                        continue
                    if nm >= len(m_v):
                        continue
                    copy_into(Y, X)
                    apply_move(Y, T, P, rc[q], rg[q], pi, stamp, stamp_box, out_cell, out_g)
                    if Y[10][SC_OVER] != 0:
                        d = float(Y[10][SC_S0] - Y[10][SC_S1])
                        m_v[nm] = d if me == 0 else -d
                        m_end[nm] = True
                    else:
                        features(Y, T, P, me, fbuf)
                        m_v[nm] = eval_value(eval_w, eval_mode, fbuf)
                        m_end[nm] = False
                    m_cell[nm] = rc[q]
                    m_g[nm] = rg[q]
                    m_pi[nm] = pi
                    nm += 1
            if nm == 0:
                continue
            order = np.argsort(
                m_v[:nm], kind="mergesort"
            )  # 相手に良い（me 視点で小さい）順。同じ値は列挙順
            best = 1e30
            for b in range(min(beam, nm)):
                r = order[b]
                if m_end[r]:
                    v3 = m_v[r]
                else:
                    # 自分が次に引くタイル種別で平均した、自分の一番良い手の値
                    seen2[:] = False
                    t2 = 0.0
                    w2 = 0.0
                    for j2 in range(lo + 1, NT - 1):
                        u = X[11][j2]
                        if seen2[u]:
                            continue
                        seen2[u] = True
                        n2 = 0
                        for q in range(lo + 1, NT - 1):
                            if X[11][q] == u:
                                n2 += 1
                        copy_into(Y, X)
                        Y[11][lo + 1] = u
                        Y[11][j2] = X[11][lo + 1]
                        apply_move(
                            Y, T, P, m_cell[r], m_g[r], m_pi[r], stamp, stamp_box, out_cell, out_g
                        )
                        if Y[10][SC_OVER] != 0:
                            d = float(Y[10][SC_S0] - Y[10][SC_S1])
                            t2 += n2 * (d if me == 0 else -d)
                            w2 += n2
                            continue
                        if Y[10][SC_CUR] != u or Y[10][SC_DRAW] != lo + 2:
                            continue
                        v = _side_best(
                            Y, Z, T, P, me, eval_w, eval_mode, fbuf, stamp, stamp_box,
                            out_cell, out_g, rc2, rg2,
                        )  # fmt: skip
                        if not np.isnan(v):
                            t2 += n2 * v
                            w2 += n2
                    v3 = t2 / w2 if w2 > 0 else m_v[r]
                best = min(best, v3)
            tot += n * best
            wsum += n
        out[ci] = tot / wsum if wsum > 0 else np.nan
    return out


@njit(cache=True)
def _mix32(x):
    """32ビットの整数を混ぜる（ブラウザ版 `mix32` と同じ値）。4手目のタイルの抽選に使う。"""
    x = np.int64(x) & 0xFFFFFFFF
    x = (x ^ (x >> 16)) & 0xFFFFFFFF
    x = (x * 0x45D9F3B) & 0xFFFFFFFF
    x = (x ^ (x >> 16)) & 0xFFFFFFFF
    x = (x * 0x45D9F3B) & 0xFFFFFFFF
    x = (x ^ (x >> 16)) & 0xFFFFFFFF
    return x


@njit(cache=True)
def _rank_moves(X, T, P, me, eval_w, eval_mode, fbuf, stamp, stamp_box, out_cell, out_g, rc, rg,
                Y, m_cell, m_g, m_pi, m_v, m_end):  # fmt: skip
    """局面 X で手番の人の全部の手（配置×ミープルなし・置ける断片）を1手読み（me 視点の評価値、
    終局する手は実際の得点差）で採点して m_* に入れ、手の数を返す。Y は作業用。"""
    mover = X[10][SC_PL]
    t = X[10][SC_CUR]
    stamp_box[0] += 1
    k = gen_placements(X, T, t, stamp, stamp_box[0], out_cell, out_g, False)
    for q in range(k):
        rc[q] = out_cell[q]
        rg[q] = out_g[q]
    nm = 0
    for q in range(k):
        npc = T[1][rg[q]] if X[10][SC_SUP0 + mover] > 0 else 0
        for pi in range(-1, npc):
            if pi >= 0 and not piece_free(X, T, P, rc[q], rg[q], pi):
                continue
            if nm >= len(m_v):
                continue
            copy_into(Y, X)
            apply_move(Y, T, P, rc[q], rg[q], pi, stamp, stamp_box, out_cell, out_g)
            if Y[10][SC_OVER] != 0:
                d = float(Y[10][SC_S0] - Y[10][SC_S1])
                m_v[nm] = d if me == 0 else -d
                m_end[nm] = True
            else:
                features(Y, T, P, me, fbuf)
                m_v[nm] = eval_value(eval_w, eval_mode, fbuf)
                m_end[nm] = False
            m_cell[nm] = rc[q]
            m_g[nm] = rg[q]
            m_pi[nm] = pi
            nm += 1
    return nm


@njit(cache=True)
def next_tile_reply3_value(
    S, T, P, cells, gs, pieces, eval_w, eval_mode, fbuf, stamp, stamp_box, out_cell, out_g,
    beam, beam2, samples,
):  # fmt: skip
    """`next_tile_reply2_value` の4手版: 相手の返し手（上位 beam 手）→自分の次の手（タイル種別ごとに
    1手読みの上位 beam2 手）→相手の次の返し手（相手の一番良い手）まで読む expectimax。

    4手目で相手が引くタイルは、samples が0なら未公開の全種別で平均し、1以上なら未公開の残りから
    samples 枚を抽選して平均する（抽選は局面と手から決まる疑似乱数で、実際の山札の並びは使わない）。
    """
    me = S[10][SC_PL]
    lo = S[10][SC_DRAW]
    out = np.zeros(len(cells))
    X = copy_state(S)
    Y = copy_state(S)
    Z = copy_state(S)
    W = copy_state(S)
    seen = np.zeros(128, np.bool_)
    seen2 = np.zeros(128, np.bool_)
    seen4 = np.zeros(128, np.bool_)
    n_out = len(out_cell)
    rc = np.zeros(n_out, np.int32)
    rg = np.zeros(n_out, np.int16)
    rc2 = np.zeros(n_out, np.int32)
    rg2 = np.zeros(n_out, np.int16)
    m_cell = np.zeros(n_out * 6, np.int32)
    m_g = np.zeros(n_out * 6, np.int16)
    m_pi = np.zeros(n_out * 6, np.int32)
    m_v = np.zeros(n_out * 6)
    m_end = np.zeros(n_out * 6, np.bool_)
    s_cell = np.zeros(n_out * 6, np.int32)
    s_g = np.zeros(n_out * 6, np.int16)
    s_pi = np.zeros(n_out * 6, np.int32)
    s_v = np.zeros(n_out * 6)
    s_end = np.zeros(n_out * 6, np.bool_)
    for ci in range(len(cells)):
        if lo >= S[10][SC_END]:  # この手で終局
            copy_into(X, S)
            apply_move(X, T, P, cells[ci], gs[ci], pieces[ci], stamp, stamp_box, out_cell, out_g)
            d = float(X[10][SC_S0] - X[10][SC_S1])
            out[ci] = d if me == 0 else -d
            continue
        seen[:] = False
        tot = 0.0
        wsum = 0.0
        for j in range(lo, NT - 1):
            t = S[11][j]
            if seen[t]:
                continue
            seen[t] = True
            n = 0
            for q in range(lo, NT - 1):
                if S[11][q] == t:
                    n += 1
            copy_into(X, S)
            X[11][lo] = t
            X[11][j] = S[11][lo]
            apply_move(X, T, P, cells[ci], gs[ci], pieces[ci], stamp, stamp_box, out_cell, out_g)
            if X[10][SC_OVER] != 0 or X[10][SC_CUR] != t or X[10][SC_DRAW] != lo + 1:
                continue
            nm = _rank_moves(X, T, P, me, eval_w, eval_mode, fbuf, stamp, stamp_box, out_cell,
                             out_g, rc, rg, Y, m_cell, m_g, m_pi, m_v, m_end)  # fmt: skip
            if nm == 0:
                continue
            order = np.argsort(m_v[:nm], kind="mergesort")  # 相手に良い（me 視点で小さい）順
            best = 1e30
            for b in range(min(beam, nm)):
                r = order[b]
                if m_end[r]:
                    best = min(best, m_v[r])
                    continue
                # 自分が次に引くタイル種別ごとに、自分の上位 beam2 手を4手目まで読んで一番良い値
                seen2[:] = False
                t2 = 0.0
                w2 = 0.0
                for j2 in range(lo + 1, NT - 1):
                    u = X[11][j2]
                    if seen2[u]:
                        continue
                    seen2[u] = True
                    n2 = 0
                    for q in range(lo + 1, NT - 1):
                        if X[11][q] == u:
                            n2 += 1
                    copy_into(Y, X)
                    Y[11][lo + 1] = u
                    Y[11][j2] = X[11][lo + 1]
                    apply_move(
                        Y, T, P, m_cell[r], m_g[r], m_pi[r], stamp, stamp_box, out_cell, out_g
                    )
                    if Y[10][SC_OVER] != 0:
                        d = float(Y[10][SC_S0] - Y[10][SC_S1])
                        t2 += n2 * (d if me == 0 else -d)
                        w2 += n2
                        continue
                    if Y[10][SC_CUR] != u or Y[10][SC_DRAW] != lo + 2:
                        continue
                    ns = _rank_moves(Y, T, P, me, eval_w, eval_mode, fbuf, stamp, stamp_box,
                                     out_cell, out_g, rc, rg, Z, s_cell, s_g, s_pi, s_v, s_end)  # fmt: skip
                    if ns == 0:
                        continue
                    order2 = np.argsort(-s_v[:ns], kind="mergesort")  # 自分に良い順
                    mine = -1e30
                    for b2 in range(min(beam2, ns)):
                        r2 = order2[b2]
                        if s_end[r2] or lo + 2 >= NT - 1:
                            v4 = s_v[r2]
                        else:
                            t4 = 0.0
                            w4 = 0.0
                            if samples <= 0:
                                seen4[:] = False
                                for j4 in range(lo + 2, NT - 1):
                                    x4 = Y[11][j4]
                                    if seen4[x4]:
                                        continue
                                    seen4[x4] = True
                                    n4 = 0
                                    for q in range(lo + 2, NT - 1):
                                        if Y[11][q] == x4:
                                            n4 += 1
                                    copy_into(Z, Y)
                                    Z[11][lo + 2] = x4
                                    Z[11][j4] = Y[11][lo + 2]
                                    apply_move(Z, T, P, s_cell[r2], s_g[r2], s_pi[r2], stamp,
                                               stamp_box, out_cell, out_g)  # fmt: skip
                                    if Z[10][SC_OVER] != 0:
                                        d = float(Z[10][SC_S0] - Z[10][SC_S1])
                                        t4 += n4 * (d if me == 0 else -d)
                                        w4 += n4
                                        continue
                                    if Z[10][SC_CUR] != x4 or Z[10][SC_DRAW] != lo + 3:
                                        continue
                                    v = _side_best(Z, W, T, P, me, eval_w, eval_mode, fbuf, stamp,
                                                   stamp_box, out_cell, out_g, rc2, rg2)  # fmt: skip
                                    if not np.isnan(v):
                                        t4 += n4 * v
                                        w4 += n4
                            else:
                                nrest = NT - 1 - (lo + 2)
                                h = (np.int64(lo) * 7919 + np.int64(ci) * 104729
                                     + np.int64(t) * 1299709 + np.int64(b) * 15485863
                                     + np.int64(u) * 32452843 + np.int64(b2) * 49979687) & 0xFFFFFFFF  # fmt: skip
                                for k4 in range(samples):
                                    h = _mix32((h + k4 * 0x9E3779B9) & 0xFFFFFFFF)
                                    j4 = lo + 2 + (h % nrest)
                                    x4 = Y[11][j4]
                                    copy_into(Z, Y)
                                    Z[11][lo + 2] = x4
                                    Z[11][j4] = Y[11][lo + 2]
                                    apply_move(Z, T, P, s_cell[r2], s_g[r2], s_pi[r2], stamp,
                                               stamp_box, out_cell, out_g)  # fmt: skip
                                    if Z[10][SC_OVER] != 0:
                                        d = float(Z[10][SC_S0] - Z[10][SC_S1])
                                        t4 += d if me == 0 else -d
                                        w4 += 1
                                        continue
                                    if Z[10][SC_CUR] != x4 or Z[10][SC_DRAW] != lo + 3:
                                        continue
                                    v = _side_best(Z, W, T, P, me, eval_w, eval_mode, fbuf, stamp,
                                                   stamp_box, out_cell, out_g, rc2, rg2)  # fmt: skip
                                    if not np.isnan(v):
                                        t4 += v
                                        w4 += 1
                            v4 = t4 / w4 if w4 > 0 else s_v[r2]
                        mine = max(mine, v4)
                    t2 += n2 * mine
                    w2 += n2
                v3 = t2 / w2 if w2 > 0 else m_v[r]
                best = min(best, v3)
            if best < 1e29:
                tot += n * best
                wsum += n
        out[ci] = tot / wsum if wsum > 0 else np.nan
    return out


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
        chance: bool = False,
        rollout_farm: bool = True,
        rollout_reshuffle: bool = False,
        reselect: float = 0.0,
        reselect_late: float = -1.0,
        reselect_k: int = 6,
        reselect_reply: int = 0,
        reply_beam: int = 3,
        reply_beam2: int = 1,
        reply_samples: int = 0,
        scale_decay: float = 0.0,
        scale_min: float = 5.0,
        endgame: int = 0,
        puct: float = 0.0,
        puct_ply: int = 1,
        puct_tau: float = 3.0,
    ) -> None:
        """eval_path に線形評価関数の重み(.npy)を渡すと、葉をその評価関数で評価する。

        その場合 rollout_depth は評価前に進めるランダム手数（未指定は0=評価のみ）。
        chance=True で、タイル引きを確率節点としてモデル化する。既定の False は従来の固定山札で、
        EXPERIMENTS.md の既存の結果はすべてこの条件。確率節点版は同回数で優位を示せていないため既定にしない。
        """
        self.chance = chance
        # False なら、ロールアウトでは草原（農民）にミープルを置かない
        self.rollout_farm = rollout_farm
        # True なら、葉から先のロールアウトの前に山札の未公開部分を引き直す（`run_tree` の rshuf）
        self.rollout_reshuffle = rollout_reshuffle
        # 0より大きいと、探索の上位 reselect_k 候補を「次に相手が引くタイルで平均した評価値」と
        # この重みで混ぜて選び直す（`choose_reselect`）。評価関数があるときだけ
        self.reselect = reselect if eval_path else 0.0
        # 0以上なら、選び直しの重みを山札の残りで変える: 最初は reselect、山札が尽きるころ reselect_late（間は線形）。
        # 負なら reselect のまま（R-022）
        self.reselect_late = float(reselect_late)
        self.reselect_k = max(1, int(reselect_k))
        # True なら選び直しの1手先評価を、相手の一番良い返し手まで読んだ値にする（`next_tile_reply_value`）
        # 2 なら相手の返し手のあと自分の次の手まで読む（`next_tile_reply2_value`、相手の返し手は上位 reply_beam 手）
        self.reselect_reply = int(reselect_reply)
        self.reply_beam = max(1, int(reply_beam))
        # 3 なら相手の次の返し手まで読む（`next_tile_reply3_value`）。自分の次の手は上位 reply_beam2 手、
        # 4手目で相手が引くタイルは reply_samples 枚の抽選（0 なら全種別で平均）
        self.reply_beam2 = max(1, int(reply_beam2))
        self.reply_samples = max(0, int(reply_samples))
        # 0より大きいと、報酬の尺度を残りタイルの割合の scale_decay 乗で縮める（下限 scale_min）。
        # 終盤ほど点差より勝ち負けを重く見る
        self.scale_decay = scale_decay
        self.scale_min = scale_min
        # 1以上なら、山札の残りがこの枚数以下の局面は終局まで読み切った勝率最大の手（GTO）で指す
        # （`endgame.best_move`。探索の手が最善なら、それをそのまま使う）
        self.endgame = int(endgame)
        # 0より大きいと、根から puct_ply 手番ぶんの配置の節点を PUCT で選ぶ（`run_tree` の puct）。
        # 事前確率は置いた直後の評価値の softmax（温度 puct_tau 点）。評価関数があるときだけ
        self.puct = puct if eval_path else 0.0
        self.puct_ply = max(1, int(puct_ply))
        self.puct_tau = puct_tau
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
            + (",chance" if chance else "")
            + ("" if rollout_farm else ",rf=0")
            + (",rs=1" if rollout_reshuffle else "")
            + (f",rsel={reselect:g},rk={reselect_k}" if self.reselect > 0 else "")
            + (f",rsl={reselect_late:g}" if self.reselect > 0 and reselect_late >= 0 else "")
            + (f",rr={self.reselect_reply}" if self.reselect > 0 and self.reselect_reply else "")
            + (f",rb={self.reply_beam}" if self.reselect > 0 and self.reselect_reply >= 2 else "")
            + (
                f",rb2={self.reply_beam2},rsm={self.reply_samples}"
                if self.reselect > 0 and self.reselect_reply >= 3
                else ""
            )
            + (f",sd={scale_decay:g},smin={scale_min:g}" if scale_decay > 0 else "")
            + (f",eg={self.endgame}" if self.endgame > 0 else "")
            + (
                f",puct={self.puct:g},pply={self.puct_ply},ptau={puct_tau:g}"
                if self.puct > 0
                else ""
            )
            + (
                f",nn={nn_path.replace(chr(92), '/').split('/')[-1]},topk={nn_topk}"
                if nn_path
                else ""
            )
            + ")"
        )

    def to_fast(self, state: State):
        """Pythonの State を、着手履歴の再生でNumba状態へ変換する。"""
        S = self.fast.new_game(state.deck, getattr(state, "komi", 0))
        for x, y, ti, vi, piece in state.history:
            self.fast.apply(S, x, y, ti, vi, piece)
        return S

    def reselect_weight(self, S) -> float:
        """この局面の選び直しの重み（先読みの値をどれだけ信じるか）。"""
        if self.reselect_late < 0:
            return self.reselect
        sc = S[10]
        frac = max(0, int(sc[SC_END]) - int(sc[SC_DRAW]) + 1) / (NT - 1)
        return self.reselect_late + (self.reselect - self.reselect_late) * min(1.0, frac)

    def scale_for(self, S) -> float:
        """この局面で使う報酬の尺度（負なら勝敗報酬）。"""
        scale = -1.0 if self.reward_scale is None else float(self.reward_scale)
        if scale > 0 and self.scale_decay > 0:
            sc = S[10]
            frac = max(0, int(sc[SC_END]) - int(sc[SC_DRAW]) + 1) / (NT - 1)
            scale = max(self.scale_min, scale * frac**self.scale_decay)
        return scale

    def choose(self, S):
        """Numba状態 S（手番側が指す局面）から (マス, 向きID, 断片) を返す。乱数は seed_rng 済みとする。"""
        move = self.choose_search(S)
        if self.endgame > 0 and int(S[10][SC_END]) - int(S[10][SC_DRAW]) <= self.endgame:
            from .endgame import best_move

            move, _ = best_move(self.fast, S, prefer=move)
        return move

    def choose_search(self, S):
        """探索だけで選んだ手（終盤の読み切りなし）。"""
        depth = (
            self.rollout_depth if self.rollout_depth is not None else (0 if self.eval_path else -1)
        )
        sc = self.fast.scratch
        if self.reselect > 0:
            return self.choose_reselect(S, depth)
        cell, g, piece = search(
            S,
            self.fast.T,
            self.fast.P,
            self.n_sims,
            self.n_det,
            self.c,
            self.scale_for(S),
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
            1 if self.chance else 0,
            bool(self.rollout_farm),
            1 if self.rollout_reshuffle else 0,
            self.puct,
            self.puct_ply,
            self.puct_tau,
        )
        return int(cell), int(g), int(piece)

    def choose_reselect(self, S, depth: int):
        """探索の訪問数の上位候補（配置×ミープル）を、探索の平均報酬を得点差に戻した値と
        `next_tile_value` を (1-reselect):reselect で混ぜた値で選び直す。"""
        f = self.fast
        sc = f.scratch
        scale = self.scale_for(S)
        cells, gs, a1, _, a2, w2 = search_stats(
            S, f.T, f.P, self.n_sims, self.n_det, self.c, scale, self.meeple_prob, depth,
            sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g, sc.free, sc.rec, self.eval_w,
            self.eval_mode, self.fbuf, self.late, self.fpu, self.prior_visits, self.root_allow(S),
            1 if self.chance else 0, bool(self.rollout_farm), 1 if self.rollout_reshuffle else 0,
            self.puct, self.puct_ply, self.puct_tau,
        )  # fmt: skip
        ks, qs = np.nonzero(a2)
        if len(ks) == 0:
            # 探索が少なくミープルの節点まで届いていない: 訪問数最多の配置をミープルなしで
            return int(cells[np.argmax(a1)]), int(gs[np.argmax(a1)]), -1
        order = np.argsort(-a2[ks, qs], kind="stable")[: self.reselect_k]
        ks, qs = ks[order], qs[order]
        if len(ks) == 1 or scale <= 0:
            return int(cells[ks[0]]), int(gs[ks[0]]), int(qs[0]) - 1
        args = (
            S, f.T, f.P, cells[ks].astype(np.int64), gs[ks].astype(np.int64),
            (qs - 1).astype(np.int64), self.eval_w, self.eval_mode, self.fbuf,
            sc.stamp, sc.stamp_box, sc.out_cell, sc.out_g,
        )  # fmt: skip
        if self.reselect_reply >= 3:
            val = next_tile_reply3_value(
                *args, self.reply_beam, self.reply_beam2, self.reply_samples
            )
        elif self.reselect_reply >= 2:
            val = next_tile_reply2_value(*args, self.reply_beam)
        elif self.reselect_reply:
            val = next_tile_reply_value(*args)
        else:
            val = next_tile_value(*args)
        q = w2[ks, qs] / a2[ks, qs]
        dm = scale * np.arctanh(np.clip(2 * q - 1, -0.999, 0.999))
        dn = np.where(np.isnan(val), dm, val)
        w = self.reselect_weight(S)
        b = int(np.argmax((1 - w) * dm + w * dn))
        return int(cells[ks[b]]), int(gs[ks[b]]), int(qs[b]) - 1

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
