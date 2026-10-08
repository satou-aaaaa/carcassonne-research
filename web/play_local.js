// ブラウザだけで対局を進める（公開ページ docs/play.html 用）。
//
// web/play.html はローカルサーバー（scripts/play_human.py）に問い合わせて対局を進めるが、公開ページでは
// この window.LOCAL_API が同じ問い合わせに答える。対局の進め方と画面に渡すデータは
// src/carcassonne/webplay.py の HumanGame と同じ。AIの思考は Web Worker（play_worker.js）で行い、
// Worker が使えない環境（file:// で開いた場合など）では画面側で計算する（その間は画面が止まる）。
(function (root) {
  "use strict";
  const KIND_JA = { C: "都市", R: "道", F: "草原", M: "修道院" };

  // AIの1手 [マス, 向きID, 断片]。level は PLAY_DATA.levels のキー、seed で乱数を決める
  function aiMove(eng, data, S, level, seed) {
    eng.rng.seed(seed);
    const moves = eng.legalMoves(S);
    if (moves.length === 1) return moves[0];
    const lv = data.levels[level];
    if (!lv.sims) return eng.greedy(S);
    return eng.search(S, searchOpts(data, lv));
  }
  function searchOpts(data, lv) {
    return { sims: lv.sims, depth: lv.depth, c: 0.5, scale: 30, meepleProb: 0.3, w: Float64Array.from(data.eval.w) };
  }
  // 人間の手の採点用に、最強設定で候補手を解析する（webplay.make_coach）
  function analyzeMoves(eng, data, S, seed) {
    eng.rng.seed(seed);
    return eng.analyze(S, searchOpts(data, data.levels.strong));
  }
  // Worker と画面側の両方で使う: 山札と着手列から局面を作り直して計算する
  function runJob(eng, data, job) {
    const S = eng.newGame(job.deck);
    for (const [cell, g, piece] of job.history) eng.applyMove(S, cell, g, piece);
    if (job.kind === "analyze") return analyzeMoves(eng, data, S, job.seed);
    return aiMove(eng, data, S, job.level, job.seed);
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { aiMove, analyzeMoves, runJob };
    return;
  }
  root.CarcassonneLocal = { aiMove, analyzeMoves, runJob };
  if (typeof document === "undefined") return; // Worker の中では画面用の部分は不要

  const C = root.Carcassonne, DATA = root.PLAY_DATA;
  const eng = new C.Engine(DATA.tables);
  const LIB = DATA.tiles;

  // ---- 思考（Worker） ----------------------------------------------------
  let worker = null, jobId = 0;
  const waiting = new Map();
  try {
    worker = new Worker("play_worker.js");
    worker.onmessage = e => {
      const w = waiting.get(e.data.id);
      waiting.delete(e.data.id);
      if (e.data.error) w.reject(new Error(e.data.error));
      else w.resolve(e.data.result);
    };
    // 読み込めなかったときは画面側の計算に切り替え、待っている計算もやり直す
    worker.onerror = () => {
      worker = null;
      for (const w of waiting.values()) computeHere(w.job).then(w.resolve, w.reject);
      waiting.clear();
    };
  } catch (err) {
    worker = null;
  }
  // 画面を描き直す時間を与えてから計算する
  function computeHere(job) {
    return new Promise(resolve => setTimeout(() => resolve(runJob(eng, DATA, job)), 30));
  }
  function compute(job) {
    if (!worker) return computeHere(job);
    return new Promise((resolve, reject) => {
      const id = ++jobId;
      waiting.set(id, { job, resolve, reject });
      worker.postMessage({ ...job, id });
    });
  }

  function coachText(c) {
    const b = c.best;
    const ai = `AIなら紫の点線のマスに置き、${b.kind ? b.kind + "にミープル" : "ミープルは置かない"}`;
    if (c.loss === null) return `ヒント: AIがほとんど考えなかった手です。${ai}。`;
    if (c.loss < 1) return "ヒント: AIの最善手とほぼ同じ、いい手です。";
    return `ヒント: AIの見積もりでは最善より約${c.loss.toFixed(0)}点の損。${ai}。`;
  }

  // ---- 対局（webplay.HumanGame と同じ） ------------------------------------
  class LocalGame {
    constructor(seed, humanSeat, level, name, coach) {
      this.seed = seed;
      this.human_seat = humanSeat;
      this.level = level;
      this.name = name;
      this.coach = coach;
      this.deck = eng.shuffledDeck(seed);
      this.S = eng.newGame(this.deck);
      this.history = [];
      this.meeples = [];
      this.events = [];
      this.last_ai = null;
      this.last_coach = null;
      this.end_meeples = [];  // 終局直前に盤上にいたミープル（終局の得点内訳用）
      this.mid = 0;
    }

    pieceKind(g, piece) { return LIB[eng.gTi[g]].variants[eng.gVi[g]].pieces[piece].kind; }

    async humanMove(x, y, v, piece) {
      const S = this.S;
      if (S.sc[C.SC_OVER] || S.sc[C.SC_PL] !== this.human_seat) throw new Error("あなたの手番ではありません");
      const cell = C.cellOf(x, y), g = eng.vbase[S.sc[C.SC_CUR]] + v, p = piece === null ? -1 : piece;
      if (!eng.legalMoves(S).some(m => m[0] === cell && m[1] === g && m[2] === p)) throw new Error("不正な手です");
      this.last_ai = null;
      this.last_coach = null;
      if (this.coach) {
        const opts = await compute({ kind: "analyze", deck: this.deck, history: this.history, seed: this.seed * 1000 + this.history.length });
        const best = opts[0], [bx, by] = C.xyOf(best.cell);
        this.last_coach = {
          best: { x: bx, y: by, v: eng.gVi[best.g], piece: best.piece < 0 ? null : best.piece, kind: best.piece < 0 ? null : KIND_JA[this.pieceKind(best.g, best.piece)] },
          loss: null,
        };
        const mine = opts.find(o => o.cell === cell && o.g === g && o.piece === p);
        if (mine) this.last_coach.loss = Math.round(Math.max(0, best.diff - mine.diff) * 10) / 10;
      }
      this.play(cell, g, p);
      if (this.last_coach) this.events.push({ player: this.human_seat, text: coachText(this.last_coach), x: this.last_coach.best.x, y: this.last_coach.best.y });
      if (root.onInterimState) root.onInterimState(this.view());
      await this.advanceAi();
    }

    async advanceAi() {
      const S = this.S;
      while (!S.sc[C.SC_OVER] && S.sc[C.SC_PL] !== this.human_seat) {
        const ply = this.history.length;
        const m = await compute({ kind: "move", deck: this.deck, history: this.history, level: this.level, seed: (this.seed * 2 + 1 - this.human_seat) * 1000 + ply });
        this.play(m[0], m[1], m[2]);
        const [x, y] = C.xyOf(m[0]);
        this.last_ai = { x, y };
      }
    }

    play(cell, g, piece) {
      const S = this.S, player = S.sc[C.SC_PL], before = [S.sc[C.SC_S0], S.sc[C.SC_S0 + 1]];
      const [x, y] = C.xyOf(cell);
      eng.applyMove(S, cell, g, piece);
      this.history.push([cell, g, piece]);
      if (piece >= 0) this.meeples.push({ id: ++this.mid, x, y, piece, player });
      if (S.sc[C.SC_OVER]) this.end_meeples = this.meeples.slice();
      // 回収されたミープル（特徴が完成/終局処理された）を除く
      this.meeples = this.meeples.filter(m => eng.meepleAt(S, m.x, m.y, m.piece, m.player));
      const gain = S.sc[C.SC_S0 + player] - before[player], opp = S.sc[C.SC_S0 + 1 - player] - before[1 - player];
      const who = player === this.human_seat ? "あなた" : "AI";
      const put = piece >= 0 ? `${KIND_JA[this.pieceKind(g, piece)]}にミープル` : "ミープルなし";
      let text = `${who}: タイルを置き、${put}`;
      if (gain || opp) text += ` ／ 得点 ${who}+${gain}` + (opp ? ` 相手+${opp}` : "");
      this.events.push({ player, text, x, y });
    }

    view() {
      const S = this.S, sc = S.sc, over = !!sc[C.SC_OVER];
      const placements = [];
      if (!over && sc[C.SC_PL] === this.human_seat) {
        const grouped = new Map();
        for (const [cell, g, piece] of eng.legalMoves(S)) {
          const key = cell + ":" + g;
          if (!grouped.has(key)) {
            const [x, y] = C.xyOf(cell);
            grouped.set(key, { x, y, v: eng.gVi[g], pieces: [] });
          }
          if (piece >= 0) grouped.get(key).pieces.push(piece);
        }
        placements.push(...grouped.values());
      }
      const remaining = LIB.map(() => 0);
      for (let i = sc[C.SC_DRAW]; i < C.NT - 1; i++) remaining[S.deck[i]]++;
      const board = [];
      for (let t = 0; t < sc[C.SC_N]; t++) {
        const [x, y] = C.xyOf(S.tcell[t]);
        board.push({ x, y, t: eng.gTi[S.tg[t]], v: eng.gVi[S.tg[t]] });
      }
      return {
        seed: this.seed,
        human_seat: this.human_seat,
        level: this.level,
        name: this.name,
        player: sc[C.SC_PL],
        over,
        saved: false,
        scores: [sc[C.SC_S0], sc[C.SC_S0 + 1]],
        projected: eng.projected(S),
        supply: [sc[C.SC_SUP0], sc[C.SC_SUP0 + 1]],
        deck_left: C.NT - 1 - sc[C.SC_DRAW],
        current: over ? null : sc[C.SC_CUR],
        remaining,
        board,
        meeples: this.meeples,
        end_meeples: over ? this.end_meeples : [],
        last_ai: this.last_ai,
        coach: this.coach,
        last_coach: this.last_coach,
        events: this.events.slice(-40),
        placements,
        discarded: sc[C.SC_DISC],
      };
    }
  }

  // ---- web/play.html からの問い合わせ（scripts/play_human.py の API と同じ形） ----
  let game = null;
  root.LOCAL_API = async function (path, body) {
    if (path === "/api/tiles") {
      const levels = {};
      for (const [k, v] of Object.entries(DATA.levels)) levels[k] = v.label;
      return { tiles: LIB, levels };
    }
    if (path === "/api/state") return game ? game.view() : null;
    if (path === "/api/new") {
      if (!DATA.levels[body.level]) throw new Error("未知の強さ");
      game = new LocalGame(Number(body.seed), Number(body.human_seat), body.level, String(body.name || "").slice(0, 40), !!body.coach);
      await game.advanceAi();
      return game.view();
    }
    if (path === "/api/move") {
      if (!game) throw new Error("対局が始まっていません");
      await game.humanMove(Number(body.x), Number(body.y), Number(body.variant), body.piece === null || body.piece === undefined ? null : Number(body.piece));
      return game.view();
    }
    throw new Error("not found");
  };
})(typeof self !== "undefined" ? self : this);
