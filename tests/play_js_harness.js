// tests/test_play_js.py から node で呼ぶ検証用スクリプト（公開ページ docs/ の JavaScript を読み込む）。
//
//   node tests/play_js_harness.js '{"cmd": "games", "seeds": [1, 2]}'
//
// games:  ランダムに指した対局の毎手の記録（合法手・着手・着手後の得点など・着手前の特徴量）
// search: 局面を少し進めてから探索し、返した手が合法か
// match:  ブラウザ版のAI同士の対局結果
// move:   山札と着手列 [x, y, 種別, 向き, 断片] の局面で、ブラウザ版のAIが選ぶ手
"use strict";
const path = require("path");
const DOCS = path.join(__dirname, "..", "docs");
const C = require(path.join(DOCS, "carcassonne_engine.js"));
const DATA = require(path.join(DOCS, "play_data.js"));
const { aiMove } = require(path.join(DOCS, "play_local.js"));

const eng = new C.Engine(DATA.tables);
const args = JSON.parse(process.argv[2]);

function snap(S) {
  const sc = S.sc;
  return {
    scores: [sc[C.SC_S0], sc[C.SC_S0 + 1]],
    supply: [sc[C.SC_SUP0], sc[C.SC_SUP0 + 1]],
    over: !!sc[C.SC_OVER],
    player: sc[C.SC_PL],
    cur: sc[C.SC_CUR],
    disc: sc[C.SC_DISC],
  };
}
const mv = m => { const [x, y] = C.xyOf(m[0]); return [x, y, eng.gTi[m[1]], eng.gVi[m[1]], m[2] < 0 ? null : m[2]]; };

if (args.cmd === "games") {
  const out = [];
  for (const seed of args.seeds) {
    eng.rng.seed(seed);
    const deck = eng.shuffledDeck(seed);
    const S = eng.newGame(deck);
    const steps = [];
    const f = new Float64Array(C.NF);
    while (!S.sc[C.SC_OVER]) {
      const legal = eng.legalMoves(S).map(mv);
      eng.features(S, S.sc[C.SC_PL], f);
      const feats = Array.from(f);
      const m = eng.randomMove(S, args.meeple_prob ?? 0.5);
      eng.applyMove(S, m[0], m[1], m[2]);
      steps.push({ legal, move: mv(m), snap: snap(S), projected: eng.projected(S), feats });
    }
    out.push({ seed, deck, start: snap(eng.newGame(deck)), steps });
  }
  console.log(JSON.stringify(out));
} else if (args.cmd === "search") {
  const out = [];
  for (const seed of args.seeds) {
    eng.rng.seed(seed);
    const S = eng.newGame(eng.shuffledDeck(seed));
    eng.rollout(S, 0.3, args.plies, null);
    if (S.sc[C.SC_OVER]) continue;
    const legal = new Set(eng.legalMoves(S).map(m => m.join(",")));
    const t = Date.now();
    const m = aiMove(eng, DATA, S, args.level, seed);
    out.push({ legal: legal.has(m.join(",")), ms: Date.now() - t });
  }
  console.log(JSON.stringify(out));
} else if (args.cmd === "match") {
  // args.a / args.b: 強さ。席を入れ替えて各シード2局
  const res = [];
  for (const seed of args.seeds) {
    for (const aSeat of [0, 1]) {
      const S = eng.newGame(eng.shuffledDeck(seed));
      let ply = 0;
      while (!S.sc[C.SC_OVER]) {
        const level = S.sc[C.SC_PL] === aSeat ? args.a : args.b;
        const m = aiMove(eng, DATA, S, level, seed * 1000 + ply++);
        eng.applyMove(S, m[0], m[1], m[2]);
      }
      const s = [S.sc[C.SC_S0], S.sc[C.SC_S0 + 1]];
      res.push({ seed, a_seat: aSeat, diff_a: s[aSeat] - s[1 - aSeat] });
    }
  }
  console.log(JSON.stringify(res));
} else if (args.cmd === "move") {
  const S = eng.newGame(args.deck);
  for (const [x, y, ti, vi, piece] of args.history) eng.applyMove(S, C.cellOf(x, y), eng.vbase[ti] + vi, piece === null ? -1 : piece);
  console.log(JSON.stringify(mv(aiMove(eng, DATA, S, args.level, args.seed))));
}
