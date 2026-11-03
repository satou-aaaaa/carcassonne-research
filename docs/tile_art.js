// タイルの絵（対戦ページとクイズで共通）。形の計算（cityShapes・anchorOf・EM）は各ページのものを受け取る。
// 見た目を変えるときは scripts/board_svg.py（解説ページの図）も同じ色・描き方に合わせる。
(function (root) {
  "use strict";
  const COL = {
    fieldHi: "#9fcf78", fieldLo: "#78ad5a", tuft: "rgba(52,105,38,.55)",
    roadEdge: "#8a6f48", road: "#f2e2b6", pebble: "rgba(201,178,128,.55)", hub: "#c9b07a",
    wall: "#6a4a30", cityHi: "#e2ad78", cityLo: "#c98656", shade: "rgba(95,55,25,.8)",
    shield: "#2f5fb5", shieldMark: "#ffd75e",
    garden: "#b4dd8f", chapel: "#f3ead6", roof: "#b8463a",
  };

  // 同じタイル・向きなら毎回同じ模様になる乱数
  function rng(seed) {
    let s = (Math.imul(seed + 1, 2654435761) >>> 0) || 1;
    return () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; };
  }

  function shapePath(g, sh, S) { sh.forEach((q, i) => i ? g.lineTo(q[0]*S, q[1]*S) : g.moveTo(q[0]*S, q[1]*S)); g.closePath(); }

  // 都市の形を1枚の影絵にする（台形どうしの継ぎ目が線にならないよう、同じ色で細くふちどる）
  function cityMask(S, shapes) {
    const m = document.createElement("canvas"); m.width = m.height = S;
    const mg = m.getContext("2d"); mg.fillStyle = mg.strokeStyle = "#000"; mg.lineWidth = S*.008; mg.lineJoin = "round";
    for (const sh of shapes) { mg.beginPath(); shapePath(mg, sh, S); mg.fill(); mg.stroke(); }
    return m;
  }

  // 城壁の内側に影を落とす（都市の外側を影の元にして、内側だけ残す）
  function innerShade(g, S, mask) {
    const o = document.createElement("canvas"); o.width = o.height = S;
    const og = o.getContext("2d"); og.fillRect(0, 0, S, S); og.globalCompositeOperation = "destination-out"; og.drawImage(mask, 0, 0);
    const t = document.createElement("canvas"); t.width = t.height = S;
    const tg = t.getContext("2d"); tg.shadowColor = COL.shade; tg.shadowBlur = S*.08; tg.drawImage(o, 0, 0);
    tg.shadowColor = "transparent"; tg.globalCompositeOperation = "destination-in"; tg.drawImage(mask, 0, 0);
    g.drawImage(t, 0, 0);
  }

  function shield(g, ax, ay, r) {
    g.beginPath(); g.moveTo(ax - r, ay - r*1.1); g.lineTo(ax + r, ay - r*1.1); g.lineTo(ax + r, ay + .2*r);
    g.quadraticCurveTo(ax + r, ay + r*.9, ax, ay + r*1.35); g.quadraticCurveTo(ax - r, ay + r*.9, ax - r, ay + .2*r); g.closePath();
    g.fillStyle = COL.shield; g.fill(); g.strokeStyle = "#fff"; g.lineWidth = r*.22; g.stroke();
    g.strokeStyle = COL.shieldMark; g.lineWidth = r*.32; g.beginPath();
    g.moveTo(ax, ay - r*.75); g.lineTo(ax, ay + r*.95); g.moveTo(ax - r*.65, ay - r*.15); g.lineTo(ax + r*.65, ay - r*.15); g.stroke();
  }

  // g: S×S の 2D コンテキスト。vr: タイルの向き（pieces）。geo: {EM, cityShapes, anchor(p)}。seed: 模様の種
  function paint(g, S, vr, geo, seed) {
    const rnd = rng(seed), EM = geo.EM;
    const roads = vr.pieces.filter(p => p.kind === "R"), cities = vr.pieces.filter(p => p.kind === "C");
    const shapes = cities.flatMap(ct => geo.cityShapes(ct.sides));

    // 草原: やわらかいグラデーション＋草のふさ＋小さな花
    const fg = g.createRadialGradient(S*.4, S*.35, S*.1, S*.5, S*.5, S*.8);
    fg.addColorStop(0, COL.fieldHi); fg.addColorStop(1, COL.fieldLo);
    g.fillStyle = fg; g.fillRect(0, 0, S, S);
    g.lineCap = "round"; g.strokeStyle = COL.tuft; g.lineWidth = S*.008;
    for (let i = 0; i < 22; i++) {
      const x = rnd()*S, y = rnd()*S, h = S*(.025 + rnd()*.02);
      g.beginPath(); g.moveTo(x - h*.5, y - h); g.lineTo(x, y); g.lineTo(x + h*.5, y - h); g.moveTo(x, y); g.lineTo(x, y - h*1.1); g.stroke();
    }
    for (let i = 0; i < 5; i++) {
      g.fillStyle = rnd() < .5 ? "rgba(255,248,200,.85)" : "rgba(255,255,255,.8)";
      g.beginPath(); g.arc(rnd()*S, rnd()*S, S*.009, 0, 7); g.fill();
    }

    // 道: こげ茶のふち＋クリーム色＋小石。2辺の道は 端→中心→端、3本以上は中心の手前で止める
    const roadPath = r => {
      g.beginPath();
      const a = [EM[r.sides[0]][0]*S, EM[r.sides[0]][1]*S];
      if (r.sides.length >= 2) {
        const b = [EM[r.sides[1]][0]*S, EM[r.sides[1]][1]*S];
        g.moveTo(a[0], a[1]); g.lineTo(S/2, S/2); g.lineTo(b[0], b[1]);
      } else {
        const f = roads.length >= 3 ? .78 : 1;
        g.moveTo(a[0], a[1]); g.lineTo(a[0] + (S/2 - a[0])*f, a[1] + (S/2 - a[1])*f);
      }
    };
    const strokeRoads = (w, col, dash) => {
      g.strokeStyle = col; g.lineWidth = w; g.lineCap = "butt"; g.lineJoin = "round"; g.setLineDash(dash || []);
      for (const r of roads) { roadPath(r); g.stroke(); }
      g.setLineDash([]);
    };
    strokeRoads(S*.19, COL.roadEdge); strokeRoads(S*.135, COL.road); strokeRoads(S*.135, COL.pebble, [S*.012, S*.05]);
    if (roads.length >= 3) {
      g.fillStyle = COL.roadEdge; g.beginPath(); g.arc(S/2, S/2, S*.085, 0, 7); g.fill();
      g.fillStyle = COL.hub; g.beginPath(); g.arc(S/2, S/2, S*.055, 0, 7); g.fill();
    }

    // 都市: ぎざぎざの城壁＋レンガ色＋内側の影＋家並みの屋根
    if (shapes.length) {
      g.lineJoin = "miter"; g.strokeStyle = COL.wall;
      for (const sh of shapes) { g.beginPath(); shapePath(g, sh, S); g.lineWidth = S*.06; g.stroke(); }
      g.setLineDash([S*.04, S*.035]);
      for (const sh of shapes) { g.beginPath(); shapePath(g, sh, S); g.lineWidth = S*.1; g.stroke(); }
      g.setLineDash([]);
      const mask = cityMask(S, shapes);
      const body = document.createElement("canvas"); body.width = body.height = S;
      const bg = body.getContext("2d"), cg = bg.createLinearGradient(0, 0, S, S);
      cg.addColorStop(0, COL.cityHi); cg.addColorStop(1, COL.cityLo);
      bg.fillStyle = cg; bg.fillRect(0, 0, S, S);
      for (let i = 0; i < 26; i++) {
        const x = rnd()*S, y = rnd()*S, w = S*.035;
        bg.fillStyle = rnd() < .5 ? "rgba(178,72,52,.55)" : "rgba(150,90,60,.45)";
        bg.beginPath(); bg.moveTo(x - w, y); bg.lineTo(x, y - w*.9); bg.lineTo(x + w, y); bg.closePath(); bg.fill();
      }
      bg.globalCompositeOperation = "destination-in"; bg.drawImage(mask, 0, 0);
      g.drawImage(body, 0, 0);
      innerShade(g, S, mask);
      for (const ct of cities) if (ct.pennant) {
        const [ax, ay] = geo.anchor(ct);
        shield(g, ax*S, ay*S, S*.065);
      }
    }

    // 修道院: 明るい庭＋白い礼拝堂（赤い屋根・十字・扉）
    if (vr.pieces.some(p => p.kind === "M")) {
      g.fillStyle = COL.garden; g.beginPath(); g.arc(S*.5, S*.5, S*.2, 0, 7); g.fill();
      g.fillStyle = "rgba(0,0,0,.18)"; g.fillRect(S*.39, S*.49, S*.27, S*.2);
      g.fillStyle = COL.chapel; g.fillRect(S*.37, S*.46, S*.26, S*.2);
      g.fillStyle = COL.roof; g.beginPath(); g.moveTo(S*.33, S*.47); g.lineTo(S*.5, S*.31); g.lineTo(S*.67, S*.47); g.closePath(); g.fill();
      g.fillStyle = COL.wall; g.beginPath(); g.moveTo(S*.47, S*.66); g.lineTo(S*.47, S*.57); g.arc(S*.5, S*.57, S*.03, Math.PI, 0); g.lineTo(S*.53, S*.66); g.fill();
      g.strokeStyle = COL.wall; g.lineWidth = S*.012; g.lineCap = "round";
      g.beginPath(); g.moveTo(S*.5, S*.31); g.lineTo(S*.5, S*.23); g.moveTo(S*.465, S*.26); g.lineTo(S*.535, S*.26); g.stroke();
    }

    // ふちの立体感（左上に光、右下に影）
    g.lineWidth = S*.012; g.lineCap = "butt";
    g.strokeStyle = "rgba(255,255,255,.35)"; g.beginPath(); g.moveTo(S*.006, S); g.lineTo(S*.006, S*.006); g.lineTo(S, S*.006); g.stroke();
    g.strokeStyle = "rgba(40,30,10,.45)"; g.beginPath(); g.moveTo(S*.994, 0); g.lineTo(S*.994, S*.994); g.lineTo(0, S*.994); g.stroke();
  }

  root.TileArt = { paint, COL };
})(typeof self !== "undefined" ? self : this);
