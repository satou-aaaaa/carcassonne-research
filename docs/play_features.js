// 対戦画面用: 盤面の特徴（都市・道・草原・修道院）のつながりと得点を、表示用のデータだけから求める。
//
// 画面（web/play.html）は、ミープル候補が属する特徴の範囲と点数、完成した特徴の点滅、終局の得点内訳に
// これを使う。AIの思考（carcassonne_engine.js）とは独立していて、点数の数え方は
// src/carcassonne/state.py（_score_after_placement, _end_awards）と同じ。
// tests/test_play_js.py が Python 版の「今終局した場合の予測得点」と一致することを確かめている。
//
// 入力は /api/tiles の tiles（LIB）と view() の board [{x, y, t, v}]、meeples [{x, y, piece, player}]。
// 辺は N,E,S,W = 0..3、半辺は side*2+h。(side, h) は隣の ((side+2)%4, 1-h) に接する。y は上が正。
(function (root) {
  "use strict";
  const DIRS = [[0, 1], [1, 0], [0, -1], [-1, 0]];
  const AROUND = [[-1, -1], [0, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [0, 1], [1, 1]];
  const FARM = 3;
  const key = (x, y) => x + "," + y;

  // 盤面の断片をつなぎ、特徴ごとの集計を作る
  function build(lib, board) {
    const parent = [], nodes = new Map(), at = new Map(), info = [];
    const find = a => { while (parent[a] !== a) { parent[a] = parent[parent[a]]; a = parent[a]; } return a; };
    const union = (a, b) => { a = find(a); b = find(b); if (a !== b) parent[b] = a; };
    for (const b of board) {
      const vr = lib[b.t].variants[b.v], ids = [];
      vr.pieces.forEach((p, i) => { const n = parent.length; parent.push(n); ids.push(n); info.push({ x: b.x, y: b.y, piece: i, p }); });
      nodes.set(key(b.x, b.y), ids);
      at.set(key(b.x, b.y), vr);
    }
    // 辺の数（都市・道の未完成の端）を数えるために、つながった辺を記録する
    const closed = new Set();
    for (const b of board) {
      const vr = at.get(key(b.x, b.y)), ids = nodes.get(key(b.x, b.y));
      for (let s = 0; s < 4; s++) {
        const nk = key(b.x + DIRS[s][0], b.y + DIRS[s][1]);
        const nv = at.get(nk);
        if (!nv) continue;
        const nids = nodes.get(nk), os = (s + 2) % 4;
        const mine = vr.pieces.findIndex(p => (p.kind === "C" || p.kind === "R") && p.sides.includes(s));
        const theirs = nv.pieces.findIndex(p => (p.kind === "C" || p.kind === "R") && p.sides.includes(os));
        if (mine >= 0 && theirs >= 0) { union(ids[mine], nids[theirs]); closed.add(ids[mine] + ":" + s); }
        for (let h = 0; h < 2; h++) {
          const fm = vr.pieces.findIndex(p => p.kind === "F" && p.halves.includes(s * 2 + h));
          const ft = nv.pieces.findIndex(p => p.kind === "F" && p.halves.includes(os * 2 + 1 - h));
          if (fm >= 0 && ft >= 0) union(ids[fm], nids[ft]);
        }
      }
    }
    const feats = new Map();
    info.forEach((it, n) => {
      const r = it.p.kind === "M" ? n : find(n);  // 修道院は1タイルで1つの特徴
      if (!feats.has(r)) feats.set(r, { id: r, kind: it.p.kind, parts: [], cells: new Set(), open: 0, pennants: 0, cityIds: new Set() });
      const f = feats.get(r);
      f.parts.push({ x: it.x, y: it.y, piece: it.piece });
      f.cells.add(key(it.x, it.y));
      if (it.p.kind === "C" || it.p.kind === "R") {
        for (const s of it.p.sides) if (!closed.has(n + ":" + s)) f.open++;
        if (it.p.pennant) f.pennants++;
      }
      if (it.p.kind === "F") for (const c of it.p.city_adj || []) f.cityIds.add(nodes.get(key(it.x, it.y))[c]);
    });
    const featOf = n => feats.get(info[n].p.kind === "M" ? n : find(n));
    for (const f of feats.values()) {
      if (f.kind === "M") {
        const { x, y } = f.parts[0];
        f.around = AROUND.filter(([dx, dy]) => at.has(key(x + dx, y + dy))).length;
        f.complete = f.around === 8;
      } else if (f.kind === "C" || f.kind === "R") {
        f.complete = f.open === 0;
      } else {
        f.complete = false;
      }
    }
    for (const f of feats.values()) {
      if (f.kind !== "F") continue;
      const cities = new Set([...f.cityIds].map(c => featOf(c)));
      f.cities = [...cities];
      f.doneCities = f.cities.filter(c => c.complete).length;
    }
    return {
      // (x, y) の piece 番目の断片が属する特徴（無ければ null）
      feature(x, y, piece) {
        const ids = nodes.get(key(x, y));
        return ids && ids[piece] !== undefined ? featOf(ids[piece]) : null;
      },
      features: () => [...feats.values()],
    };
  }

  // 完成したときの点数（草原は完成しない）
  function completeValue(f) {
    if (f.kind === "C") return 2 * (f.cells.size + f.pennants);
    if (f.kind === "R") return f.cells.size;
    if (f.kind === "M") return 9;
    return null;
  }
  // 今終局した場合の点数（未完成の都市・道、修道院、草原）
  function endValue(f) {
    if (f.kind === "C") return f.cells.size + f.pennants;
    if (f.kind === "R") return f.cells.size;
    if (f.kind === "M") return 1 + f.around;
    return FARM * f.doneCities;
  }
  // 特徴ごとのミープル数 [先手, 後手]
  function owners(B, f, meeples) {
    const m = [0, 0];
    for (const q of meeples) if (B.feature(q.x, q.y, q.piece) === f) m[q.player]++;
    return m;
  }

  // 今終局した場合に加わる点数。kinds[player][kind] は種類別の内訳
  function endScores(lib, board, meeples) {
    const B = build(lib, board);
    const total = [0, 0], kinds = [{ C: 0, R: 0, M: 0, F: 0 }, { C: 0, R: 0, M: 0, F: 0 }];
    const seen = new Set();
    for (const q of meeples) {
      const f = B.feature(q.x, q.y, q.piece);
      if (!f || seen.has(f)) continue;
      seen.add(f);
      if (f.complete) continue;  // 完成した特徴は置いた時点で得点済み
      const m = owners(B, f, meeples), top = Math.max(m[0], m[1]), pts = endValue(f);
      for (const p of [0, 1]) if (m[p] === top) { total[p] += pts; kinds[p][f.kind] += pts; }
    }
    return { total, kinds };
  }

  const api = { build, completeValue, endValue, owners, endScores, key };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CarcFeatures = api;
})(typeof self !== "undefined" ? self : this);
