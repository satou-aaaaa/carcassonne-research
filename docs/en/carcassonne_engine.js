// カルカソンヌのルールエンジンと評価関数付きMCTS（ブラウザ・Node 共用）。
//
// src/carcassonne/fast.py（ルール）・fast_eval.py（特徴量）・fast_mcts.py（探索）を
// そのまま JavaScript に移したもの。配列の並びと関数の分け方も Python 版に合わせてある。
// Python 版との一致は tests/test_play_js.py で確かめる（同じ着手列で得点・合法手・特徴量が一致）。
// 探索は Python 版の既定（fpu なし・評価値順の展開なし・決定化1回）のみ移植している。
//
// 状態は型付き配列の束。盤は 145x145 のグリッド（開始タイルが中央）で、各マスには「置かれた順番+1」
// （0は空）を持つ。断片ノードのIDは `順番*P + 断片index`。Union-Find と集計は根でのみ有効。
// タイル集合（int64 のビット列）は 24 枚ずつ3語の Int32 に分けて持つ。
(function (root) {
  "use strict";

  const G = 145; // グリッド一辺
  const C0 = 72; // 開始タイルの座標オフセット
  const NT = 72; // タイル総数
  const MEEPLES = 7;
  const NF = 36; // 特徴量数（fast_eval.NF）
  const HARD = 3; // fast_eval.HARD
  const SC_N = 0, SC_PL = 1, SC_S0 = 2, SC_S1 = 3, SC_SUP0 = 4, SC_OVER = 6, SC_DRAW = 7, SC_CUR = 8, SC_DISC = 9;
  const SC_LEN = 10;
  const DIRCELL = [1, G, -1, -G]; // N,E,S,W

  function popcnt(x) {
    x = x - ((x >>> 1) & 0x55555555);
    x = (x & 0x33333333) + ((x >>> 2) & 0x33333333);
    return (((x + (x >>> 4)) & 0x0f0f0f0f) * 0x01010101) >>> 24;
  }

  // 乱数（xorshift128。シードから決定的）
  class Rng {
    constructor(seed) { this.seed(seed); }
    seed(seed) {
      let s = (seed >>> 0) ^ 0x9e3779b9;
      const next = () => { s = (s + 0x6d2b79f5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return (t ^ (t >>> 14)) >>> 0; };
      this.a = next() | 1; this.b = next(); this.c = next(); this.d = next();
    }
    u32() {
      let t = this.d;
      const s = this.a;
      this.d = this.c; this.c = this.b; this.b = s;
      t ^= t << 11; t ^= t >>> 8;
      this.a = (t ^ s ^ (s >>> 19)) >>> 0;
      return this.a;
    }
    random() { return this.u32() / 4294967296; }
    randint(lo, hi) { return lo + Math.floor(this.random() * (hi - lo)); } // [lo, hi)
  }

  function makeState(P) {
    const NN = NT * P;
    const parent = new Int16Array(NN);
    for (let i = 0; i < NN; i++) parent[i] = i;
    return {
      grid: new Int16Array(G * G), // 順番+1
      tg: new Int16Array(NT), // 順番 -> 向きの全体ID
      tcell: new Int32Array(NT), // 順番 -> マス
      parent,
      kind: new Int8Array(NN).fill(-1),
      opn: new Int8Array(NN), // 開放端
      pen: new Int8Array(NN), // 盾
      t0: new Int32Array(NN), t1: new Int32Array(NN), t2: new Int32Array(NN), // タイル集合
      meep: new Int8Array(NN * 2), // meep[node*2+player]
      sc: new Int32Array(SC_LEN),
      deck: new Int8Array(NT), // 山札（開始タイルを除く71枚の種別index）
    };
  }
  const KEYS = ["grid", "tg", "tcell", "parent", "kind", "opn", "pen", "t0", "t1", "t2", "meep", "sc", "deck"];
  function copyInto(dst, src) { for (const k of KEYS) dst[k].set(src[k]); }
  function copyState(S) { const o = {}; for (const k of KEYS) o[k] = S[k].slice(); return o; }

  function find(parent, x) {
    while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; }
    return x;
  }

  class Engine {
    // data: scripts/build_play_page.py が書き出すテーブル（fast.build_tables と同じ内容）
    constructor(data) {
      const P = data.P;
      this.P = P;
      this.edge = Int8Array.from(data.edge);
      this.npc = Int8Array.from(data.npc);
      this.pkind = Int8Array.from(data.pkind);
      this.psides = Int8Array.from(data.psides);
      this.phalves = Int16Array.from(data.phalves);
      this.ppen = Int8Array.from(data.ppen);
      this.cadj = Int16Array.from(data.cadj);
      this.sidepc = Int8Array.from(data.sidepc);
      this.halfpc = Int8Array.from(data.halfpc);
      this.mpiece = Int8Array.from(data.mpiece);
      this.vbase = Int32Array.from(data.vbase);
      this.nvar = Int32Array.from(data.nvar);
      this.start = data.start;
      this.counts = data.counts;
      const ng = this.npc.length;
      this.gTi = new Int32Array(ng);
      this.gVi = new Int32Array(ng);
      for (let ti = 0; ti < this.vbase.length; ti++) {
        for (let vi = 0; vi < this.nvar[ti]; vi++) { this.gTi[this.vbase[ti] + vi] = ti; this.gVi[this.vbase[ti] + vi] = vi; }
      }
      // 作業用バッファ
      this.stamp = new Int32Array(G * G);
      this.stampVal = 0;
      this.outCell = new Int32Array((G * G) >> 2);
      this.outG = new Int16Array((G * G) >> 2);
      this.free = new Int32Array(16);
      this.req = new Int8Array(4);
      this.pts = new Int32Array(NT * P);
      this.pairC = new Int32Array(NT * P);
      this.pairF = new Int32Array(NT * P);
      this.done = new Int32Array(P);
      this.mf = new Int32Array(NT * P);
      this.fpc = new Int32Array(NT * P);
      this.fpf = new Int32Array(NT * P);
      this.cnt = new Int32Array(this.nvar.length);
      this.rng = new Rng(0);
    }

    // ---- 盤面 ------------------------------------------------------------

    union(S, a, b) {
      const parent = S.parent;
      const ra = find(parent, a), rb = find(parent, b);
      if (ra === rb) return ra;
      parent[rb] = ra;
      S.opn[ra] += S.opn[rb];
      S.pen[ra] += S.pen[rb];
      S.t0[ra] |= S.t0[rb]; S.t1[ra] |= S.t1[rb]; S.t2[ra] |= S.t2[rb];
      S.meep[ra * 2] += S.meep[rb * 2];
      S.meep[ra * 2 + 1] += S.meep[rb * 2 + 1];
      return ra;
    }

    ntiles(S, r) { return popcnt(S.t0[r]) + popcnt(S.t1[r]) + popcnt(S.t2[r]); }

    placeTile(S, cell, g) {
      const P = this.P, sc = S.sc, parent = S.parent;
      const t = sc[SC_N];
      sc[SC_N] = t + 1;
      S.grid[cell] = t + 1;
      S.tg[t] = g;
      S.tcell[t] = cell;
      const base = t * P;
      for (let i = 0; i < this.npc[g]; i++) {
        const n = base + i, k = this.pkind[g * P + i];
        parent[n] = n;
        S.kind[n] = k;
        S.meep[n * 2] = 0; S.meep[n * 2 + 1] = 0;
        S.pen[n] = 0; S.t0[n] = 0; S.t1[n] = 0; S.t2[n] = 0; S.opn[n] = 0;
        if (k <= 1) {
          S.opn[n] = popcnt(this.psides[g * P + i]);
          const bit = 1 << (t % 24);
          if (t < 24) S.t0[n] = bit; else if (t < 48) S.t1[n] = bit; else S.t2[n] = bit;
          S.pen[n] = this.ppen[g * P + i];
        }
      }
      for (let s = 0; s < 4; s++) {
        const nt = S.grid[cell + DIRCELL[s]] - 1;
        if (nt < 0) continue;
        const ng = S.tg[nt], nbase = nt * P, os = (s + 2) % 4;
        const a = this.sidepc[g * 4 + s], b = this.sidepc[ng * 4 + os];
        if (a >= 0 && b >= 0) {
          const ra = find(parent, base + a), rb = find(parent, nbase + b);
          if (ra === rb) S.opn[ra] -= 2;
          else S.opn[this.union(S, ra, rb)] -= 2;
        }
        for (let h = 0; h < 2; h++) {
          const fa = this.halfpc[g * 8 + s * 2 + h], fb = this.halfpc[ng * 8 + os * 2 + 1 - h];
          if (fa >= 0 && fb >= 0) this.union(S, base + fa, nbase + fb);
        }
      }
    }

    reqAt(S, cell, out) {
      for (let s = 0; s < 4; s++) {
        const nt = S.grid[cell + DIRCELL[s]] - 1;
        out[s] = nt < 0 ? -1 : this.edge[S.tg[nt] * 4 + (s + 2) % 4];
      }
    }

    // タイル種別 ti の合法配置を outCell/outG に列挙して件数を返す
    genPlacements(S, ti, limitFirst) {
      const grid = S.grid, tcell = S.tcell, req = this.req, stamp = this.stamp;
      const sv = ++this.stampVal;
      const nPlaced = S.sc[SC_N], vb = this.vbase[ti], nv = this.nvar[ti];
      let k = 0;
      for (let t = 0; t < nPlaced; t++) {
        const c0 = tcell[t];
        for (let s = 0; s < 4; s++) {
          const c = c0 + DIRCELL[s];
          if (grid[c] !== 0 || stamp[c] === sv) continue;
          stamp[c] = sv;
          this.reqAt(S, c, req);
          for (let vi = 0; vi < nv; vi++) {
            const g = vb + vi;
            let ok = true;
            for (let d = 0; d < 4; d++) {
              if (req[d] >= 0 && req[d] !== this.edge[g * 4 + d]) { ok = false; break; }
            }
            if (ok) {
              this.outCell[k] = c; this.outG[k] = g; k++;
              if (limitFirst) return k;
            }
          }
        }
      }
      return k;
    }

    // cell に向き g で置いたとき、断片 pi が連結する特徴に既にミープルがいなければ true
    pieceFree(S, cell, g, pi) {
      const P = this.P, grid = S.grid, tg = S.tg, parent = S.parent, meep = S.meep;
      const k = this.pkind[g * P + pi];
      if (k === 3) return true;
      if (k <= 1) {
        const sides = this.psides[g * P + pi];
        for (let s = 0; s < 4; s++) {
          if (!((sides >> s) & 1)) continue;
          const nt = grid[cell + DIRCELL[s]] - 1;
          if (nt < 0) continue;
          const r = find(parent, nt * P + this.sidepc[tg[nt] * 4 + (s + 2) % 4]);
          if (meep[r * 2] + meep[r * 2 + 1] > 0) return false;
        }
        return true;
      }
      const halves = this.phalves[g * P + pi];
      for (let hh = 0; hh < 8; hh++) {
        if (!((halves >> hh) & 1)) continue;
        const s = hh >> 1, h = hh & 1;
        const nt = grid[cell + DIRCELL[s]] - 1;
        if (nt < 0) continue;
        const fp = this.halfpc[tg[nt] * 8 + ((s + 2) % 4) * 2 + 1 - h];
        if (fp >= 0) {
          const r = find(parent, nt * P + fp);
          if (meep[r * 2] + meep[r * 2 + 1] > 0) return false;
        }
      }
      return true;
    }

    // ---- 得点 ------------------------------------------------------------

    award(S, r, points) {
      const sc = S.sc, meep = S.meep;
      const m0 = meep[r * 2], m1 = meep[r * 2 + 1], top = Math.max(m0, m1);
      if (top > 0) {
        if (m0 === top) sc[SC_S0] += points;
        if (m1 === top) sc[SC_S0 + 1] += points;
      }
      sc[SC_SUP0] += m0;
      sc[SC_SUP0 + 1] += m1;
      meep[r * 2] = 0;
      meep[r * 2 + 1] = 0;
    }

    surrounded(S, cell) {
      for (let dx = -1; dx <= 1; dx++) {
        for (let dy = -1; dy <= 1; dy++) {
          if ((dx || dy) && S.grid[cell + dx * G + dy] === 0) return false;
        }
      }
      return true;
    }

    scoreAfterPlacement(S, cell, g) {
      const P = this.P, parent = S.parent, done = this.done;
      const t = S.grid[cell] - 1, base = t * P;
      let nd = 0;
      for (let i = 0; i < this.npc[g]; i++) {
        const k = this.pkind[g * P + i];
        if (k > 1) continue;
        const r = find(parent, base + i);
        if (S.opn[r] !== 0) continue;
        let seen = false;
        for (let j = 0; j < nd; j++) if (done[j] === r) seen = true;
        if (seen) continue;
        done[nd++] = r;
        const n = this.ntiles(S, r);
        this.award(S, r, k === 0 ? 2 * (n + S.pen[r]) : n);
      }
      for (let dx = -1; dx <= 1; dx++) {
        for (let dy = -1; dy <= 1; dy++) {
          const c = cell + dx * G + dy, nt = S.grid[c] - 1;
          if (nt < 0) continue;
          const mp = this.mpiece[S.tg[nt]];
          if (mp < 0) continue;
          const r = find(parent, nt * P + mp);
          if (S.meep[r * 2] + S.meep[r * 2 + 1] > 0 && this.surrounded(S, c)) this.award(S, r, 9);
        }
      }
    }

    // 今終局した場合の各根の得点を pts[root] に書く（ミープルのいる特徴のみ。状態は変更しない）
    endPoints(S, pts) {
      const P = this.P, parent = S.parent, meep = S.meep, nPlaced = S.sc[SC_N];
      pts.fill(0);
      for (let t = 0; t < nPlaced; t++) {
        const g = S.tg[t];
        for (let i = 0; i < this.npc[g]; i++) {
          const r = find(parent, t * P + i);
          if (meep[r * 2] + meep[r * 2 + 1] === 0) continue;
          const k = this.pkind[g * P + i];
          if (k === 0) pts[r] = this.ntiles(S, r) + S.pen[r];
          else if (k === 1) pts[r] = this.ntiles(S, r);
          else if (k === 3) {
            let around = 0;
            const c = S.tcell[t];
            for (let dx = -1; dx <= 1; dx++) {
              for (let dy = -1; dy <= 1; dy++) if ((dx || dy) && S.grid[c + dx * G + dy] !== 0) around++;
            }
            pts[r] = 1 + around;
          }
        }
      }
      // 農民: 隣接する完成都市（別々の根）の数 × 3
      const pairC = this.pairC, pairF = this.pairF;
      let npairs = 0;
      for (let t = 0; t < nPlaced; t++) {
        const g = S.tg[t];
        for (let i = 0; i < this.npc[g]; i++) {
          if (this.pkind[g * P + i] !== 0) continue;
          const cr = find(parent, t * P + i);
          if (S.opn[cr] !== 0) continue;
          const adj = this.cadj[g * P + i];
          for (let j = 0; j < this.npc[g]; j++) {
            if (!((adj >> j) & 1)) continue;
            const fr = find(parent, t * P + j);
            if (meep[fr * 2] + meep[fr * 2 + 1] === 0) continue;
            let dup = false;
            for (let q = 0; q < npairs; q++) if (pairC[q] === cr && pairF[q] === fr) { dup = true; break; }
            if (!dup) { pairC[npairs] = cr; pairF[npairs] = fr; npairs++; pts[fr] += 3; }
          }
        }
      }
    }

    finish(S) {
      const P = this.P, sc = S.sc, pts = this.pts, parent = S.parent, meep = S.meep;
      sc[SC_OVER] = 1;
      this.endPoints(S, pts);
      for (let t = 0; t < sc[SC_N]; t++) {
        for (let i = 0; i < this.npc[S.tg[t]]; i++) {
          const n = t * P + i;
          if (find(parent, n) === n && meep[n * 2] + meep[n * 2 + 1] > 0) this.award(S, n, pts[n]);
        }
      }
    }

    // 今終局した場合の得点 [s0, s1]。状態は変更しない
    projected(S) {
      const P = this.P, sc = S.sc, pts = this.pts, parent = S.parent, meep = S.meep;
      let s0 = sc[SC_S0], s1 = sc[SC_S0 + 1];
      if (sc[SC_OVER] === 1) return [s0, s1];
      this.endPoints(S, pts);
      for (let t = 0; t < sc[SC_N]; t++) {
        for (let i = 0; i < this.npc[S.tg[t]]; i++) {
          const n = t * P + i;
          if (find(parent, n) !== n) continue;
          const m0 = meep[n * 2], m1 = meep[n * 2 + 1], top = Math.max(m0, m1);
          if (top > 0) {
            if (m0 === top) s0 += pts[n];
            if (m1 === top) s1 += pts[n];
          }
        }
      }
      return [s0, s1];
    }

    // ---- 進行 ------------------------------------------------------------

    // 置ける次のタイルを引く（置けないものは捨てる）。山札切れなら終局処理
    draw(S) {
      const sc = S.sc;
      while (sc[SC_DRAW] < NT - 1) {
        const ti = S.deck[sc[SC_DRAW]];
        sc[SC_DRAW]++;
        if (this.genPlacements(S, ti, true) > 0) { sc[SC_CUR] = ti; return; }
        sc[SC_DISC]++;
      }
      sc[SC_CUR] = -1;
      this.finish(S);
    }

    // 配置＋ミープルを適用する（合法性は呼び出し側が保証）
    applyMove(S, cell, g, piece) {
      const sc = S.sc, player = sc[SC_PL];
      this.placeTile(S, cell, g);
      if (piece >= 0) {
        const r = find(S.parent, (S.grid[cell] - 1) * this.P + piece);
        S.meep[r * 2 + player]++;
        sc[SC_SUP0 + player]--;
      }
      this.scoreAfterPlacement(S, cell, g);
      sc[SC_PL] = 1 - player;
      this.draw(S);
    }

    // 山札（開始タイルを除く71枚の種別index）から初期状態を作る
    newGame(deck) {
      const S = makeState(this.P);
      S.sc[SC_SUP0] = MEEPLES;
      S.sc[SC_SUP0 + 1] = MEEPLES;
      for (let i = 0; i < NT - 1; i++) S.deck[i] = deck[i];
      this.placeTile(S, C0 * G + C0, this.vbase[this.start]);
      this.draw(S);
      return S;
    }

    // シードから山札を作る（Python 版の State.new_game とは並びが異なる）
    shuffledDeck(seed) {
      const deck = [];
      this.counts.forEach((c, ti) => { for (let k = 0; k < c - (ti === this.start ? 1 : 0); k++) deck.push(ti); });
      const rng = new Rng(seed);
      for (let i = deck.length - 1; i > 0; i--) {
        const j = rng.randint(0, i + 1);
        [deck[i], deck[j]] = [deck[j], deck[i]];
      }
      return deck;
    }

    // ロールアウト用: 配置は一様、ミープルは確率 meepleProb で置ける断片から一様
    randomMove(S, meepleProb) {
      const sc = S.sc, rng = this.rng;
      const k = this.genPlacements(S, sc[SC_CUR], false);
      const j = rng.randint(0, k);
      const cell = this.outCell[j], g = this.outG[j];
      let piece = -1;
      if (sc[SC_SUP0 + sc[SC_PL]] > 0 && rng.random() < meepleProb) {
        let nf = 0;
        for (let pi = 0; pi < this.npc[g]; pi++) if (this.pieceFree(S, cell, g, pi)) this.free[nf++] = pi;
        if (nf > 0) piece = this.free[rng.randint(0, nf)];
      }
      return [cell, g, piece];
    }

    // S を破壊的に進める。maxSteps<0 で終局まで。戻り値は（予測）得点 [s0, s1]。rec があれば着手を記録する
    rollout(S, meepleProb, maxSteps, rec) {
      const sc = S.sc;
      let steps = 0;
      while (sc[SC_OVER] === 0) {
        if (maxSteps >= 0 && steps >= maxSteps) return this.projected(S);
        const [cell, g, piece] = this.randomMove(S, meepleProb);
        if (rec) rec.push([cell, g, piece]);
        this.applyMove(S, cell, g, piece);
        steps++;
      }
      return [sc[SC_S0], sc[SC_S0 + 1]];
    }

    // ---- 評価関数（fast_eval.features） -----------------------------------

    // 空きマス cell に置ける残りタイルの枚数（fast_eval.n_fit）
    nFit(S, cell, cnt) {
      const req = this.req;
      this.reqAt(S, cell, req);
      let n = 0;
      for (let ti = 0; ti < cnt.length; ti++) {
        if (cnt[ti] === 0) continue;
        for (let vi = 0; vi < this.nvar[ti]; vi++) {
          const g = this.vbase[ti] + vi;
          let ok = true;
          for (let d = 0; d < 4; d++) {
            if (req[d] >= 0 && req[d] !== this.edge[g * 4 + d]) { ok = false; break; }
          }
          if (ok) { n += cnt[ti]; break; }
        }
      }
      return n;
    }

    // 未完成の都市とミープルのいる未完成の道・修道院の根ごとに、隣の空きマスに合う残りタイル枚数の最小値（fast_eval.min_fit）
    minFit(S, out) {
      const P = this.P, sc = S.sc, grid = S.grid, parent = S.parent, meep = S.meep, cnt = this.cnt;
      cnt.fill(0);
      for (let i = sc[SC_DRAW]; i < NT - 1; i++) cnt[S.deck[i]]++;
      if (sc[SC_CUR] >= 0 && sc[SC_OVER] === 0) cnt[sc[SC_CUR]]++;
      out.fill(1 << 20);
      for (let t = 0; t < sc[SC_N]; t++) {
        const g = S.tg[t], c0 = S.tcell[t];
        for (let s = 0; s < 4; s++) {
          const c = c0 + DIRCELL[s];
          if (grid[c] !== 0) continue;
          const a = this.sidepc[g * 4 + s];
          if (a < 0) continue;
          const r = find(parent, t * P + a);
          if (S.kind[r] === 0 || meep[r * 2] + meep[r * 2 + 1] > 0) out[r] = Math.min(out[r], this.nFit(S, c, cnt));
        }
        const mp = this.mpiece[g];
        if (mp >= 0) {
          const r = find(parent, t * P + mp);
          if (meep[r * 2] + meep[r * 2 + 1] > 0) {
            for (let dx = -1; dx <= 1; dx++) {
              for (let dy = -1; dy <= 1; dy++) {
                const c = c0 + dx * G + dy;
                if (grid[c] === 0) out[r] = Math.min(out[r], this.nFit(S, c, cnt));
              }
            }
          }
        }
      }
    }

    // 自分が最多の草原に隣接する、未完成だが完成可能な都市の数×3（相手の分を引く。fast_eval.field_open_cities）
    fieldOpenCities(S, me, mf) {
      const P = this.P, parent = S.parent, meep = S.meep, pc = this.fpc, pf = this.fpf;
      let np = 0, v = 0;
      for (let t = 0; t < S.sc[SC_N]; t++) {
        const g = S.tg[t];
        for (let i = 0; i < this.npc[g]; i++) {
          if (this.pkind[g * P + i] !== 0) continue;
          const cr = find(parent, t * P + i);
          if (S.opn[cr] === 0 || mf[cr] === 0) continue;
          for (let j = 0; j < this.npc[g]; j++) {
            if (!((this.cadj[g * P + i] >> j) & 1)) continue;
            const fr = find(parent, t * P + j);
            const m0 = meep[fr * 2], m1 = meep[fr * 2 + 1];
            if (m0 + m1 === 0) continue;
            let dup = false;
            for (let q = 0; q < np; q++) if (pc[q] === cr && pf[q] === fr) { dup = true; break; }
            if (dup) continue;
            pc[np] = cr; pf[np] = fr; np++;
            const top = Math.max(m0, m1), mine = me === 0 ? m0 : m1, theirs = me === 0 ? m1 : m0;
            if (mine === top) v += 3;
            if (theirs === top) v -= 3;
          }
        }
      }
      return v;
    }

    features(S, me, out) {
      const P = this.P, sc = S.sc, pts = this.pts, parent = S.parent, meep = S.meep;
      out.fill(0);
      const sign0 = me === 0 ? 1 : -1;
      out[0] = sign0 * (sc[SC_S0] - sc[SC_S0 + 1]);
      this.endPoints(S, pts);
      const mf = this.mf;
      this.minFit(S, mf);
      out[34] = this.fieldOpenCities(S, me, mf);
      for (let t = 0; t < sc[SC_N]; t++) {
        for (let i = 0; i < this.npc[S.tg[t]]; i++) {
          const n = t * P + i;
          if (find(parent, n) !== n) continue;
          const m0 = meep[n * 2], m1 = meep[n * 2 + 1];
          if (m0 + m1 === 0) continue;
          const k = S.kind[n], top = Math.max(m0, m1), v = pts[n];
          const mine = me === 0 ? m0 : m1, theirs = me === 0 ? m1 : m0;
          if (mine === top) { out[1] += v; out[2 + k] += v; }
          if (theirs === top) { out[1] -= v; out[2 + k] -= v; }
          out[6 + k] += mine - theirs;
          if (k <= 1) {
            if (mine === top) out[14 + 2 * k] += S.opn[n];
            if (theirs === top) out[15 + 2 * k] += S.opn[n];
          }
          if (mine === top) out[18] += 1;
          if (theirs === top) out[19] += 1;
          if (k === 0 && S.opn[n] > 0) {
            const b = v / S.opn[n];
            if (mine === top) out[22] += b;
            if (theirs === top) out[22] -= b;
            const q = mf[n] === 0 ? 31 : (mf[n] <= HARD ? 32 : -1);
            if (q >= 0) {
              if (mine === top) out[q] += b;
              if (theirs === top) out[q] -= b;
            }
          }
          if (k !== 2) {
            out[24] += mine; out[25] += theirs;
            if (mf[n] === 0) { out[29] += mine; out[30] += theirs; }
          }
          if (k === 3) {
            const room = 9 - v;
            if (mine === top) out[28] += room;
            if (theirs === top) out[28] -= room;
          }
        }
      }
      const mysup = sc[SC_SUP0 + me], thsup = sc[SC_SUP0 + 1 - me];
      out[10] = mysup - thsup;
      const rem = (NT - 1 - sc[SC_DRAW]) / 71;
      out[11] = rem;
      out[13] = 1;
      out[20] = rem * rem;
      out[21] = mysup / 7;
      out[1] += out[0];
      out[12] = out[1] * rem;
      out[23] = out[10] * rem;
      out[24] *= 1 - rem;
      out[25] *= 1 - rem;
      out[26] = out[4] * rem;
      out[27] = out[2] * rem;
      out[28] *= rem;
      out[33] = (out[29] - out[30]) * rem;
      out[35] = out[34] * rem;
    }

    // ---- 探索（fast_mcts.run_tree / search_stats / search） ------------------

    // 根局面 S から決定化MCTSを1本の木で行い、根の候補ごとの訪問数と報酬和を返す。
    // opts: {sims, c, scale, meepleProb, depth, w(線形の重み), late}
    searchStats(S, opts) {
      const P = this.P, rng = this.rng;
      const sims = Math.max(1, opts.sims), c = opts.c, scale = opts.scale, mp = opts.meepleProb;
      const depth = opts.depth, ew = opts.w, late = opts.late || 0;
      const k0 = this.genPlacements(S, S.sc[SC_CUR], false);
      const rpCell = this.outCell.slice(0, k0), rpG = this.outG.slice(0, k0);
      const agg1 = new Float64Array(k0), aggw1 = new Float64Array(k0);
      const agg2 = new Float64Array(k0 * (P + 1)), aggw2 = new Float64Array(k0 * (P + 1));
      const root = copyState(S);
      // 山札の未公開部分（引き済みの手元タイルを除く残り）をシャッフル
      const deck = root.deck, lo = root.sc[SC_DRAW];
      for (let i = NT - 2; i > lo; i--) {
        const j = rng.randint(lo, i + 1);
        const tmp = deck[i]; deck[i] = deck[j]; deck[j] = tmp;
      }
      const N = sims + 2, POOL = N * 160;
      const par = new Int32Array(N).fill(-1), fch = new Int32Array(N).fill(-1), nxt = new Int32Array(N).fill(-1);
      const ntype = new Int8Array(N), kcell = new Int32Array(N), kg = new Int16Array(N), kpiece = new Int16Array(N).fill(-1);
      const vis = new Int32Array(N), wsum = new Float64Array(N), mover = new Int8Array(N).fill(-1);
      const ostart = new Int32Array(N), ocnt = new Int32Array(N).fill(-1);
      const optA = new Int32Array(POOL), optB = new Int16Array(POOL);
      const path = new Int32Array(NT * 2 + 4);
      const fbuf = new Float64Array(NF);
      const W = copyState(root), wsc = W.sc;
      const evalLin = me => { this.features(W, me, fbuf); let v = 0; for (let q = 0; q < NF; q++) v += ew[q] * fbuf[q]; return v; };
      const reward = diff => (scale <= 0 ? (diff > 0 ? 1 : diff === 0 ? 0.5 : 0) : 0.5 + 0.5 * Math.tanh(diff / scale));
      let poolUsed = 0, nNodes = 1;
      for (let it = 0; it < sims; it++) {
        copyInto(W, root);
        let node = 0, plen = 1;
        path[0] = 0;
        for (;;) {
          const t = ntype[node];
          if (ocnt[node] < 0) { // 選択肢の初期化
            ostart[node] = poolUsed;
            let cnt = 0;
            if (t === 0) {
              if (wsc[SC_OVER] === 0) {
                const k = this.genPlacements(W, wsc[SC_CUR], false);
                for (let j = 0; j < k; j++) {
                  if (poolUsed + cnt < POOL) { optA[poolUsed + cnt] = this.outCell[j]; optB[poolUsed + cnt] = this.outG[j]; cnt++; }
                }
              }
            } else {
              optA[poolUsed + cnt++] = -1;
              if (wsc[SC_SUP0 + wsc[SC_PL]] > 0) {
                for (let pi = 0; pi < this.npc[kg[node]]; pi++) {
                  if (this.pieceFree(W, kcell[node], kg[node], pi)) optA[poolUsed + cnt++] = pi;
                }
              }
            }
            poolUsed += cnt;
            ocnt[node] = cnt;
          }
          if (ocnt[node] > 0) { // 展開
            const cnt = ocnt[node], o = ostart[node];
            const idx = rng.randint(0, cnt);
            const a = optA[o + idx], b = optB[o + idx];
            optA[o + idx] = optA[o + cnt - 1];
            optB[o + idx] = optB[o + cnt - 1];
            ocnt[node] = cnt - 1;
            const nw = nNodes++;
            par[nw] = node;
            nxt[nw] = fch[node];
            fch[node] = nw;
            mover[nw] = wsc[SC_PL];
            if (t === 0) { ntype[nw] = 1; kcell[nw] = a; kg[nw] = b; }
            else { ntype[nw] = 0; kpiece[nw] = a; this.applyMove(W, kcell[node], kg[node], a); }
            path[plen++] = nw;
            node = nw;
            break;
          }
          if (fch[node] < 0) break; // 終端（選択肢なし）
          // 選択（UCT）
          let best = -1, bv = -1e30;
          const ln = Math.log(vis[node] + 1);
          for (let ch = fch[node]; ch >= 0; ch = nxt[ch]) {
            const v = wsum[ch] / vis[ch] + c * Math.sqrt(ln / vis[ch]);
            if (v > bv) { bv = v; best = ch; }
          }
          if (t === 1) this.applyMove(W, kcell[node], kg[node], kpiece[best]);
          node = best;
          path[plen++] = node;
        }
        // 評価
        if (ntype[node] === 1) this.applyMove(W, kcell[node], kg[node], -1);
        let v0, v1m;
        const useEval = ew && NT - 1 - wsc[SC_DRAW] > late;
        if (useEval && wsc[SC_OVER] === 0) {
          if (depth > 0) this.rollout(W, mp, depth, null);
          if (wsc[SC_OVER] === 0) { v0 = evalLin(0); v1m = evalLin(1); }
          else { v0 = wsc[SC_S0] - wsc[SC_S0 + 1]; v1m = -v0; }
        } else {
          let s0, s1;
          if (wsc[SC_OVER] === 1) { s0 = wsc[SC_S0]; s1 = wsc[SC_S0 + 1]; }
          else [s0, s1] = this.rollout(W, mp, ew ? -1 : depth, null);
          v0 = s0 - s1; v1m = -v0;
        }
        for (let q = 0; q < plen; q++) {
          const nd = path[q];
          vis[nd]++;
          if (mover[nd] >= 0) wsum[nd] += reward(mover[nd] === 0 ? v0 : v1m);
        }
      }
      // 根の訪問数を集計
      for (let ch = fch[0]; ch >= 0; ch = nxt[ch]) {
        for (let k = 0; k < k0; k++) {
          if (rpCell[k] !== kcell[ch] || rpG[k] !== kg[ch]) continue;
          agg1[k] += vis[ch];
          aggw1[k] += wsum[ch];
          for (let gc = fch[ch]; gc >= 0; gc = nxt[gc]) {
            agg2[k * (P + 1) + kpiece[gc] + 1] += vis[gc];
            aggw2[k * (P + 1) + kpiece[gc] + 1] += wsum[gc];
          }
          break;
        }
      }
      return { cells: rpCell, gs: rpG, agg1, aggw1, agg2, aggw2 };
    }

    // 根局面 S から [マス, 向きID, 断片(-1はなし)] を返す
    search(S, opts) {
      const P = this.P, st = this.searchStats(S, opts);
      let top = -1;
      for (const v of st.agg1) top = Math.max(top, v);
      const cands = [];
      st.agg1.forEach((v, k) => { if (v === top) cands.push(k); });
      const bk = cands[this.rng.randint(0, cands.length)];
      let bp = -1, best2 = 0;
      for (let q = 0; q <= P; q++) {
        if (st.agg2[bk * (P + 1) + q] > best2) { best2 = st.agg2[bk * (P + 1) + q]; bp = q - 1; }
      }
      return [st.cells[bk], st.gs[bk], bp];
    }

    // 候補手ごとの AI の評価（puzzles.analyze）。diff は手番側視点の予想最終点差。訪問数の多い順
    analyze(S, opts) {
      const P = this.P, st = this.searchStats(S, opts);
      const out = [];
      for (let k = 0; k < st.cells.length; k++) {
        for (let q = 0; q <= P; q++) {
          const n = st.agg2[k * (P + 1) + q];
          if (n < 1) continue;
          let r = st.aggw2[k * (P + 1) + q] / n;
          r = Math.min(Math.max(r, 1e-6), 1 - 1e-6);
          out.push({ cell: st.cells[k], g: st.gs[k], piece: q - 1, visits: n, diff: opts.scale * Math.atanh(2 * r - 1) });
        }
      }
      // Python の sort は安定なので、同じ訪問数なら列挙順のまま
      return out.map((o, i) => [o, i]).sort((a, b) => b[0].visits - a[0].visits || a[1] - b[1]).map(a => a[0]);
    }

    // 1手先の予測得点差が最大の手（agents.GreedyAgent、ミープルのコスト0.5）
    greedy(S) {
      const me = S.sc[SC_PL], moves = this.legalMoves(S), W = copyState(S);
      let best = [], bestValue = -Infinity;
      for (const m of moves) {
        copyInto(W, S);
        this.applyMove(W, m[0], m[1], m[2]);
        const s = this.projected(W);
        const value = s[me] - s[1 - me] - (m[2] >= 0 ? 0.5 : 0);
        if (value > bestValue + 1e-9) { best = [m]; bestValue = value; }
        else if (Math.abs(value - bestValue) <= 1e-9) best.push(m);
      }
      return best[this.rng.randint(0, best.length)];
    }

    // ---- 表示・検証用 --------------------------------------------------------

    // 合法手の一覧 [マス, 向きID, 断片(-1はなし)]
    legalMoves(S) {
      const sc = S.sc, out = [];
      if (sc[SC_OVER]) return out;
      const k = this.genPlacements(S, sc[SC_CUR], false);
      const cells = this.outCell.slice(0, k), gs = this.outG.slice(0, k);
      const canMeeple = sc[SC_SUP0 + sc[SC_PL]] > 0;
      for (let j = 0; j < k; j++) {
        out.push([cells[j], gs[j], -1]);
        if (!canMeeple) continue;
        for (let pi = 0; pi < this.npc[gs[j]]; pi++) if (this.pieceFree(S, cells[j], gs[j], pi)) out.push([cells[j], gs[j], pi]);
      }
      return out;
    }

    // 盤上の断片 (x, y, 断片) にいまミープルがいるか（回収済みかの判定用）
    meepleAt(S, x, y, piece, player) {
      const t = S.grid[cellOf(x, y)] - 1;
      const r = find(S.parent, t * this.P + piece);
      return S.meep[r * 2 + player] > 0;
    }
  }

  const cellOf = (x, y) => (x + C0) * G + (y + C0);
  const xyOf = cell => [Math.floor(cell / G) - C0, (cell % G) - C0];

  const api = { G, C0, NT, NF, SC_N, SC_PL, SC_S0, SC_SUP0, SC_OVER, SC_DRAW, SC_CUR, SC_DISC, Engine, Rng, makeState, copyState, copyInto, cellOf, xyOf, find };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Carcassonne = api;
})(typeof self !== "undefined" ? self : this);
