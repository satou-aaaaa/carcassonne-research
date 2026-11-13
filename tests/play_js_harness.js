// tests/test_play_js.py から node で呼ぶ検証用スクリプト（公開ページ docs/ の JavaScript を読み込む）。
//
//   node tests/play_js_harness.js '{"cmd": "games", "seeds": [1, 2]}'
//
// games:  ランダムに指した対局の毎手の記録（合法手・着手・着手後の得点など・着手前の特徴量）
// search: 局面を少し進めてから探索し、返した手が合法か
// match:  ブラウザ版のAI同士の対局結果
// record: ランダムに指した対局の棋譜（公開ページが研究用に書き出す形。human_games.py が読む）
// ntv:    ランダムに進めた局面で、候補手ごとの「次のタイルで平均した評価値」（返し手あり・なし）
// replay: 棋譜（records）を再生ページの仕組み（LOCAL_API の /api/replay）で開き、途中と最後の盤・得点
// endgame: ランダムに残り bag 枚まで進めた局面で、終盤の厳密解（endgameBest）の手と値・かかった時間
// move:   山札と着手列 [x, y, 種別, 向き, 断片] の局面で、ブラウザ版のAIが選ぶ手
// copy:   局面の写し（copyInto。盤は置いたマスだけ書き直す）が、深い局面・浅い局面のどちらからでも元と同じになるか
// egcap:  時間の上限つきの終盤読み切り（endgameBest の budgetMs）が、時間切れでも合法な手を返すか
"use strict";
const path = require("path");
const DOCS = path.join(__dirname, "..", "docs");
const C = require(path.join(DOCS, "carcassonne_engine.js"));
const DATA = require(path.join(DOCS, "play_data.js"));
const { aiMove, gameRecord } = require(path.join(DOCS, "play_local.js"));

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
      // 置ける場所の列挙の順番（ロールアウトの乱数がどの手を選ぶかに効く。Python の gen_placements と同じ順か）
      const k = eng.genPlacements(S, S.sc[C.SC_CUR], false);
      const order = [];
      for (let q = 0; q < k; q++) { const [x, y] = C.xyOf(eng.outCell[q]); order.push([x, y, eng.gVi[eng.outG[q]]]); }
      eng.features(S, S.sc[C.SC_PL], f);
      const feats = Array.from(f);
      const m = eng.randomMove(S, args.meeple_prob ?? 0.5);
      eng.applyMove(S, m[0], m[1], m[2]);
      steps.push({ legal, order, move: mv(m), snap: snap(S), projected: eng.projected(S), feats });
    }
    out.push({ seed, deck, start: snap(eng.newGame(deck)), steps });
  }
  console.log(JSON.stringify(out));
} else if (args.cmd === "record") {
  const out = [];
  for (const seed of args.seeds) {
    eng.rng.seed(seed);
    const deck = eng.shuffledDeck(seed);
    const S = eng.newGame(deck);
    const history = [];
    while (!S.sc[C.SC_OVER]) {
      const m = eng.randomMove(S, 0.5);
      eng.applyMove(S, m[0], m[1], m[2]);
      history.push(m);
    }
    out.push(gameRecord(C, eng, DATA, { S, deck, history, human_seat: seed % 2, level: "strong", coach: false, hints: 0, undos: 1 }));
  }
  console.log(JSON.stringify(out));
} else if (args.cmd === "replay") {
  // 画面用の部分（LOCAL_API）は、ブラウザに似せた入れ物の中で読み込む
  const vm = require("vm"), fs = require("fs");
  const box = { Carcassonne: C, PLAY_DATA: DATA, document: {}, console, setTimeout };
  box.self = box;
  vm.runInNewContext(fs.readFileSync(path.join(DOCS, "play_local.js"), "utf8"), box);
  const LOCAL_API = box.LOCAL_API;
  (async () => {
    const out = [];
    for (const rec of args.records) {
      try {
        const v0 = await LOCAL_API("/api/replay", { record: rec, ply: args.ply });
        const va = args.analyze ? await LOCAL_API("/api/replay_analyze", { ply: args.ply }) : null;
        const v1 = await LOCAL_API("/api/replay_goto", { ply: 9999 });
        out.push({ mid: { board: v0.board.length, replay: v0.replay, over: v0.over, placements: v0.placements.length },
          end: { scores: v1.scores, over: v1.over, total: v1.replay.total, curve: v1.replay.curve },
          analysis: va && { a: va.replay.analysis, coach: va.last_coach } });
      } catch (e) { out.push({ error: e.message }); }
    }
    const closed = await LOCAL_API("/api/replay_close", {});
    console.log(JSON.stringify({ out, closed }));
  })();
} else if (args.cmd === "ntv") {
  const out = [];
  const w = Float64Array.from(DATA.eval.w);
  for (const seed of args.seeds) {
    eng.rng.seed(seed);
    const deck = eng.shuffledDeck(seed);
    const S = eng.newGame(deck);
    const history = [];
    for (let i = 0; i < args.plies && !S.sc[C.SC_OVER]; i++) {
      const m = eng.randomMove(S, 0.5);
      history.push(mv(m));
      eng.applyMove(S, m[0], m[1], m[2]);
    }
    if (S.sc[C.SC_OVER]) continue;
    const cands = eng.legalMoves(S).slice(0, 4);
    out.push({ deck, history, cands, plain: eng.nextTileValue(S, cands, w, false), reply: eng.nextTileValue(S, cands, w, true) });
  }
  console.log(JSON.stringify(out));
} else if (args.cmd === "endgame") {
  const out = [];
  for (const seed of args.seeds) {
    eng.rng.seed(seed);
    const deck = eng.shuffledDeck(seed);
    const S = eng.newGame(deck);
    const history = [];
    while (!S.sc[C.SC_OVER] && eng.bagLeft(S) > args.bag) {
      const m = eng.randomMove(S, 0.5);
      history.push(mv(m));
      eng.applyMove(S, m[0], m[1], m[2]);
    }
    if (S.sc[C.SC_OVER]) continue;
    const prefer = eng.legalMoves(S)[0];
    const t = Date.now();
    const [m, v] = eng.endgameBest(S, prefer);
    out.push({ deck, history, prefer, move: m, value: v, ms: Date.now() - t });
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
} else if (args.cmd === "copy") {
  const KEYS = ["grid", "tg", "tcell", "parent", "kind", "opn", "pen", "t0", "t1", "t2", "meep", "sc", "deck", "fr", "fp"];
  const same = (a, b) => KEYS.every(k => a[k].length === b[k].length && a[k].every((v, i) => v === b[k][i]));
  const out = [];
  for (const seed of args.seeds) {
    eng.rng.seed(seed);
    const S = eng.newGame(eng.shuffledDeck(seed));
    const snaps = [C.copyState(S)];
    while (!S.sc[C.SC_OVER]) { const m = eng.randomMove(S, 0.5); eng.applyMove(S, m[0], m[1], m[2]); snaps.push(C.copyState(S)); }
    // 作業用の局面に、深い局面と浅い局面を順不同に写す（探索・読み切りと同じ使い方）
    const W = C.makeState(eng.P);
    let ok = true;
    for (let i = 0; i < 200; i++) {
      const src = snaps[eng.rng.randint(0, snaps.length)];
      C.copyInto(W, src);
      if (!same(W, src)) ok = false;
      if (!src.sc[C.SC_OVER]) { const m = eng.randomMove(W, 0.5); eng.applyMove(W, m[0], m[1], m[2]); } // 写した後に進めても次の写しに残らない
    }
    out.push(ok);
  }
  console.log(JSON.stringify(out));
} else if (args.cmd === "egcap") {
  const out = [];
  for (const seed of args.seeds) {
    eng.rng.seed(seed);
    const S = eng.newGame(eng.shuffledDeck(seed));
    while (!S.sc[C.SC_OVER] && eng.bagLeft(S) > 3) { const m = eng.randomMove(S, 0.5); eng.applyMove(S, m[0], m[1], m[2]); }
    if (S.sc[C.SC_OVER]) continue;
    const legal = new Set(eng.legalMoves(S).map(m => m.join(",")));
    const prefer = eng.legalMoves(S).slice(-1)[0];
    const t = Date.now();
    const [m] = eng.endgameBest(S, prefer, args.budget);
    out.push({ legal: legal.has(m.join(",")), timedOut: eng.egTimedOut, ms: Date.now() - t });
  }
  console.log(JSON.stringify(out));
}
