// タイルの絵と形（対戦ページとクイズで共通）。
// 形（都市の輪郭・城壁の線・曲がり道・ミープルの位置）もここだけで決め、各ページはこれを使う。
// 見た目を変えるときは scripts/board_svg.py（解説ページの図）も同じ色・形に合わせる（tests/test_tile_art.py が確かめる）。
//
// 見やすさの決まり（2026-11 利用者の声「2辺の都市が見づらい」から）:
// - 1つにつながった都市は大きく（隣り合う2辺なら角をふくらませる）、別々の都市は細い弧にして間に草原を見せる。
// - ただし同じタイルに道があるときは、隣り合う2辺の都市を角へ引っこめ、道との間の草原を太く見せる（城壁が道に触れると草原が切れて見える）。
// - 城壁は草原との境だけに描く（タイルの継ぎ目に壁を描かない＝隣のタイルとつながった都市が1つに見える）。
// - 小さい画面（スマホ36px）でも潰れないよう、細かい模様は描かず、道は太く濃く、修道院は大きく。
(function (root) {
  "use strict";
  const COL = {
    fieldHi: "#9fcf78", fieldLo: "#78ad5a",
    roadEdge: "#5e4a2e", road: "#fbf0d0", hub: "#c9b07a",
    wall: "#5a3a22", wallStone: "#c9b9a0", cityHi: "#f3cf8e", cityLo: "#e2a865", shade: "rgba(95,55,25,.16)",
    shield: "#2f5fb5", shieldMark: "#ffd75e",
    garden: "#b4dd8f", chapel: "#f3ead6", roof: "#b8463a", border: "rgba(30,25,10,.3)",
  };

  // ---------- 形（一辺1の座標） ----------
  const EM = [[.5,0],[1,.5],[.5,1],[0,.5]];            // 辺の中点 N,E,S,W
  const CORNER = [[0,0],[1,0],[1,1],[0,1]];           // 辺 s は CORNER[s] → CORNER[s+1]

  // P→Q の3次ベジェを17点に（制御点は P→Q の 44.5%・55.5% の位置を n の向きに h ずらす）
  function bend(P, Q, h, n) {
    const d = [Q[0]-P[0], Q[1]-P[1]];
    const c1 = [P[0] + d[0]*.445 + n[0]*h, P[1] + d[1]*.445 + n[1]*h];
    const c2 = [P[0] + d[0]*.555 + n[0]*h, P[1] + d[1]*.555 + n[1]*h];
    const pts = [];
    for (let i = 0; i <= 16; i++) {
      const t = i/16, u = 1 - t, a = u*u*u, b = 3*u*u*t, c = 3*u*t*t, e = t*t*t;
      pts.push([a*P[0] + b*c1[0] + c*c2[0] + e*Q[0], a*P[1] + b*c1[1] + c*c2[1] + e*Q[1]]);
    }
    return pts;
  }

  // 都市1つの輪郭（多角形1つの配列で返す）。shape.walls = 草原との境の線（城壁を描く所）。withRoad = 同じタイルに道がある
  function cityShapes(sides, withRoad) {
    const S = new Set(sides), n = sides.length;
    if (n >= 4) { const p = CORNER.map(q => q.slice()); p.walls = []; return [p]; }
    const start = sides.find(s => !S.has((s + 3) % 4));
    const poly = [CORNER[start]], walls = [];
    let s = start, done = 0;
    while (done < 4) {
      if (S.has(s)) { poly.push(CORNER[(s + 1) % 4]); s = (s + 1) % 4; done++; continue; }
      let e = s, gap = 0;
      while (!S.has(e)) { e = (e + 1) % 4; gap++; }   // 草原の辺 s..e-1
      const P = CORNER[s], Q = CORNER[e];
      let v, h;
      if (gap === 2) { const k = CORNER[(e + 1) % 4]; v = [k[0]-.5, k[1]-.5]; h = withRoad ? .12 : -.13; }  // 隣り合う2辺: 道がなければ草原の側へふくらませて大きく、道があれば角へ引っこめる
      else { v = [.5 - (P[0]+Q[0])/2, .5 - (P[1]+Q[1])/2]; h = gap === 3 ? .373 : (n === 3 ? .33 : .27); }
      const L = Math.hypot(v[0], v[1]), w = bend(P, Q, h, [v[0]/L, v[1]/L]);
      walls.push(w);
      for (const q of w.slice(1)) poly.push(q);
      s = e; done += gap;
    }
    poly.pop();  // 最後の点は始点と同じ
    poly.walls = walls;
    return [poly];
  }

  // 都市のミープル・盾の位置
  function cityAnchor(sides, withRoad) {
    const n = sides.length;
    if (n === 1) return [[.5,.13],[.87,.5],[.5,.87],[.13,.5]][sides[0]];
    if (n >= 4 || (n === 2 && Math.abs(sides[0] - sides[1]) === 2)) return [.5, .5];
    if (n === 2) { const k = [0,1,2,3].find(c => sides.includes(c) && sides.includes((c + 3) % 4)); const f = withRoad ? .55 : .5; return [.5 + (CORNER[k][0]-.5)*f, .5 + (CORNER[k][1]-.5)*f]; }
    const miss = [0,1,2,3].find(c => !sides.includes(c)), e = EM[miss];
    return [.5 - (e[0]-.5)*.2, .5 - (e[1]-.5)*.2];
  }

  // 道の線（点の並び）。曲がり道はなめらかな弧、まっすぐな道は中心を通る、行き止まり（3本以上）は中心の手前で止める
  function roadLine(sides, nroads) {
    const a = EM[sides[0]];
    if (sides.length >= 2) {
      const b = EM[sides[1]];
      if ((sides[0] + sides[1]) % 2 === 0) return [a, [.5,.5], b];
      const pts = [];
      for (let i = 0; i <= 12; i++) { const t = i/12, u = 1 - t; pts.push([u*u*a[0] + 2*u*t*.5 + t*t*b[0], u*u*a[1] + 2*u*t*.5 + t*t*b[1]]); }
      return pts;
    }
    const f = nroads >= 3 ? .78 : 1;
    return [a, [a[0] + (.5 - a[0])*f, a[1] + (.5 - a[1])*f]];
  }

  // ---------- 絵 ----------
  function line(g, pts, S, close) { pts.forEach((q, i) => i ? g.lineTo(q[0]*S, q[1]*S) : g.moveTo(q[0]*S, q[1]*S)); if (close) g.closePath(); }

  function shield(g, ax, ay, r) {
    g.beginPath(); g.moveTo(ax - r, ay - r*1.1); g.lineTo(ax + r, ay - r*1.1); g.lineTo(ax + r, ay + .2*r);
    g.quadraticCurveTo(ax + r, ay + r*.9, ax, ay + r*1.35); g.quadraticCurveTo(ax - r, ay + r*.9, ax - r, ay + .2*r); g.closePath();
    g.fillStyle = COL.shield; g.fill(); g.strokeStyle = "#fff"; g.lineWidth = r*.22; g.stroke();
    g.strokeStyle = COL.shieldMark; g.lineWidth = r*.32; g.beginPath();
    g.moveTo(ax, ay - r*.75); g.lineTo(ax, ay + r*.95); g.moveTo(ax - r*.65, ay - r*.15); g.lineTo(ax + r*.65, ay - r*.15); g.stroke();
  }

  // g: S×S の 2D コンテキスト。vr: タイルの向き（pieces）
  function paint(g, S, vr) {
    const roads = vr.pieces.filter(p => p.kind === "R"), cities = vr.pieces.filter(p => p.kind === "C");

    // 草原: やわらかいグラデーション（細かい模様は小さい画面で潰れるので描かない）
    const fg = g.createRadialGradient(S*.4, S*.35, S*.1, S*.5, S*.5, S*.8);
    fg.addColorStop(0, COL.fieldHi); fg.addColorStop(1, COL.fieldLo);
    g.fillStyle = fg; g.fillRect(0, 0, S, S);

    // 道: 濃いふち＋明るい中身
    g.lineCap = "butt"; g.lineJoin = "round";
    for (const [w, col] of [[.23, COL.roadEdge], [.16, COL.road]]) {
      g.strokeStyle = col; g.lineWidth = S*w;
      for (const r of roads) { g.beginPath(); line(g, roadLine(r.sides, roads.length), S); g.stroke(); }
    }
    if (roads.length >= 3) {
      g.fillStyle = COL.roadEdge; g.beginPath(); g.arc(S/2, S/2, S*.1, 0, 7); g.fill();
      g.fillStyle = COL.hub; g.beginPath(); g.arc(S/2, S/2, S*.066, 0, 7); g.fill();
    }

    // 都市: 明るい色＋城壁の内側にうすい影＋草原との境だけに太い城壁
    for (const ct of cities) {
      for (const sh of cityShapes(ct.sides, roads.length > 0)) {
        const cg = g.createLinearGradient(0, 0, S, S);
        cg.addColorStop(0, COL.cityHi); cg.addColorStop(1, COL.cityLo);
        g.save(); g.beginPath(); line(g, sh, S, true); g.fillStyle = cg; g.fill(); g.clip();
        g.strokeStyle = COL.shade; g.lineJoin = "round";
        for (const w of [.2, .12]) { g.lineWidth = S*w; for (const wl of sh.walls) { g.beginPath(); line(g, wl, S); g.stroke(); } }
        g.restore();
        g.lineJoin = "round"; g.lineCap = "butt";
        for (const [w, col, dash] of [[.075, COL.wall], [.035, COL.wallStone], [.035, COL.wall, [S*.03, S*.03]]]) {
          g.strokeStyle = col; g.lineWidth = S*w; g.setLineDash(dash || []);
          for (const wl of sh.walls) { g.beginPath(); line(g, wl, S); g.stroke(); }
        }
        g.setLineDash([]);
      }
      if (ct.pennant) { const [ax, ay] = cityAnchor(ct.sides, roads.length > 0); shield(g, ax*S, ay*S, S*.085); }
    }

    // 修道院: 明るい庭＋白い礼拝堂（赤い屋根・十字・扉）。小さい画面でも分かるよう大きめ
    if (vr.pieces.some(p => p.kind === "M")) {
      const k = 1.3, T = (x, y) => [S*(.5 + (x - .5)*k), S*(.5 + (y - .5)*k)];
      g.fillStyle = COL.garden; g.beginPath(); g.arc(S*.5, S*.5, S*.2*k, 0, 7); g.fill();
      g.fillStyle = "rgba(0,0,0,.18)"; g.fillRect(...T(.39, .49), S*.27*k, S*.2*k);
      g.fillStyle = COL.chapel; g.fillRect(...T(.37, .46), S*.26*k, S*.2*k);
      g.fillStyle = COL.roof; g.beginPath(); g.moveTo(...T(.33, .47)); g.lineTo(...T(.5, .31)); g.lineTo(...T(.67, .47)); g.closePath(); g.fill();
      const [dx, dy] = T(.5, .57);
      g.fillStyle = COL.wall; g.beginPath(); g.moveTo(...T(.47, .66)); g.lineTo(...T(.47, .57)); g.arc(dx, dy, S*.03*k, Math.PI, 0); g.lineTo(...T(.53, .66)); g.fill();
      g.strokeStyle = COL.wall; g.lineWidth = S*.012*k; g.lineCap = "round";
      g.beginPath(); g.moveTo(...T(.5, .31)); g.lineTo(...T(.5, .23)); g.moveTo(...T(.465, .26)); g.lineTo(...T(.535, .26)); g.stroke();
    }

    // タイルの境にうすい線（盤上でタイル1枚ずつが数えられる）
    g.strokeStyle = COL.border; g.lineWidth = S*.016; g.strokeRect(S*.008, S*.008, S*.984, S*.984);
  }

  const hasRoad = vr => vr.pieces.some(p => p.kind === "R");
  root.TileArt = { paint, COL, EM, cityShapes, cityAnchor, roadLine, hasRoad };
})(typeof self !== "undefined" ? self : this);
