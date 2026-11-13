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
    const move = eng.search(S, searchOpts(data, lv));
    // 山札の残りが少なければ、終局まで読み切った勝率最大の手で指す（FastMCTSAgent の endgame）
    // egMs があれば読み切りにかける時間の上限（遅い端末で長く待たせない。読み切れなければ探索の手か、そこまでで確かめた良い手）
    if (lv.eg && eng.bagLeft(S) <= lv.eg) return eng.endgameBest(S, move, lv.egMs || 0)[0];
    return move;
  }
  function searchOpts(data, lv) {
    return { sims: lv.sims, depth: lv.depth, c: 0.5, scale: 30, meepleProb: 0.3, w: Float64Array.from(data.eval.w), rsel: lv.rsel || 0, rk: lv.rk || 6, rr: !!lv.rr };
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

  // 終局した対局の棋譜（研究用に送ってもらう形。src/carcassonne/human_games.py が検査して読む）。
  // C は Carcassonne（エンジンの定数）、g は LocalGame（deck・history・S・human_seat など）。名前は入れない
  function gameRecord(C, eng, data, g) {
    const sc = g.S.sc;
    return {
      v: 1,
      deck: Array.from(g.deck),
      moves: g.history.map(([cell, gi, piece]) => { const [x, y] = C.xyOf(cell); return [x, y, eng.gVi[gi], piece]; }),
      human_seat: g.human_seat,
      level: g.level,
      ai: data.eval.champion ? data.eval.champion.name : null,
      coach: !!g.coach,
      hints: g.hints || 0,
      undos: g.undos || 0,
      scores: [sc[C.SC_S0], sc[C.SC_S0 + 1]],
    };
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { aiMove, analyzeMoves, runJob, gameRecord };
    return;
  }
  root.CarcassonneLocal = { aiMove, analyzeMoves, runJob, gameRecord };
  if (typeof document === "undefined") return; // Worker の中では画面用の部分は不要

  const C = root.Carcassonne, DATA = root.PLAY_DATA;
  const eng = new C.Engine(DATA.tables);
  const LIB = DATA.tiles;

  // ---- 思考（Worker） ----------------------------------------------------
  // Worker を2つまで用意し、コーチの解析とAIの手を同時に計算できるようにする（1つずつだと待ち時間が足し算になる）
  const cores = (typeof navigator !== "undefined" && navigator.hardwareConcurrency) || 4;
  const NWORKERS = Math.max(1, Math.min(2, cores - 1));
  const workers = [], queue = [];
  let jobId = 0, useWorkers = typeof Worker !== "undefined";
  function startWorker() {
    let w;
    try { w = new Worker("play_worker.js"); } catch (err) { return null; }
    const slot = { w, job: null };
    w.onmessage = e => {
      const j = slot.job;
      slot.job = null;
      if (j && j.id === e.data.id) {
        if (e.data.error) j.reject(new Error(e.data.error));
        else j.resolve(e.data.result);
      }
      pump();
    };
    // 読み込めなかったときは画面側の計算に切り替え、待っている計算もやり直す
    w.onerror = () => {
      useWorkers = false;
      const pend = workers.filter(s => s.job).map(s => s.job).concat(queue.splice(0));
      workers.length = 0;
      for (const j of pend) computeHere(j.job).then(j.resolve, j.reject);
    };
    return slot;
  }
  function pump() {
    while (queue.length && useWorkers) {
      let slot = workers.find(s => !s.job);
      if (!slot && workers.length < NWORKERS) {
        slot = startWorker();
        if (!slot) { useWorkers = false; break; }
        workers.push(slot);
      }
      if (!slot) return;
      const j = queue.shift();
      slot.job = j;
      slot.w.postMessage({ ...j.job, id: j.id });
    }
    if (!useWorkers) for (const j of queue.splice(0)) computeHere(j.job).then(j.resolve, j.reject);
  }
  // 画面を描き直す時間を与えてから計算する
  function computeHere(job) {
    return new Promise(resolve => setTimeout(() => resolve(runJob(eng, DATA, job)), 30));
  }
  // job.history はその時点の写しを渡す（計算が始まる前に対局が進んでも混ざらないように）
  function compute(job) {
    job = { ...job, history: job.history.slice() };
    if (!useWorkers) return computeHere(job);
    return new Promise((resolve, reject) => {
      queue.push({ id: ++jobId, job, resolve, reject });
      pump();
    });
  }

  function coachText(c) {
    const b = c.best;
    const ai = `AIなら紫の点線のマスに置き、${b.kind ? b.kind + "にミープル" : "ミープルは置かない"}`;
    if (c.loss === null) return `ヒント: AIがほとんど考えなかった手です。${ai}。`;
    if (c.loss < 1) return "ヒント: AIの最善手とほぼ同じ、いい手です。";
    return `ヒント: AIの見積もりでは最善より約${c.loss.toFixed(0)}点の損。${ai}。`;
  }

  // 解析結果の手を画面用の dict にする（webplay._best_dict と同じ）
  function bestDict(pieceKind, o) {
    const [x, y] = C.xyOf(o.cell);
    return { x, y, v: eng.gVi[o.g], piece: o.piece < 0 ? null : o.piece, kind: o.piece < 0 ? null : KIND_JA[pieceKind(o.g, o.piece)] };
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
      this.hint = null;  // 置く前のヒント
      this.hints = 0;
      this.undos = 0;
      this.snaps = [];  // 人間の各手の直前の状態（待った用）
      this.mid = 0;
    }

    pieceKind(g, piece) { return LIB[eng.gTi[g]].variants[eng.gVi[g]].pieces[piece].kind; }

    async humanMove(x, y, v, piece) {
      const S = this.S;
      if (S.sc[C.SC_OVER] || S.sc[C.SC_PL] !== this.human_seat) throw new Error("あなたの手番ではありません");
      const cell = C.cellOf(x, y), g = eng.vbase[S.sc[C.SC_CUR]] + v, p = piece === null ? -1 : piece;
      if (!eng.legalMoves(S).some(m => m[0] === cell && m[1] === g && m[2] === p)) throw new Error("不正な手です");
      this.snaps.push({ n: this.history.length, meeples: this.meeples.slice(), events: this.events.slice(), last_ai: this.last_ai, last_coach: this.last_coach, mid: this.mid });
      this.last_ai = null;
      this.last_coach = null;
      this.hint = null;
      // コーチの解析（置く前の局面）とAIの返し手を同時に計算し始める
      const coachJob = this.coach ? compute({ kind: "analyze", deck: this.deck, history: this.history, seed: this.seed * 1000 + this.history.length }) : null;
      this.play(cell, g, p);
      const aiJob = this.startAiJob();
      if (coachJob) {
        if (root.onInterimState) root.onInterimState(this.view()); // 解析を待たずに自分の手を見せる
        const opts = await coachJob;
        const best = opts[0];
        this.last_coach = { best: bestDict((g, p) => this.pieceKind(g, p), best), loss: null };
        const mine = opts.find(o => o.cell === cell && o.g === g && o.piece === p);
        if (mine) this.last_coach.loss = Math.round(Math.max(0, best.diff - mine.diff) * 10) / 10;
        this.events.push({ player: this.human_seat, text: coachText(this.last_coach), x: this.last_coach.best.x, y: this.last_coach.best.y });
      }
      if (root.onInterimState) root.onInterimState(this.view());
      await this.advanceAi(aiJob);
    }

    // AIの手番なら、その手の計算を始めて { ply, promise } を返す
    startAiJob() {
      const S = this.S;
      if (S.sc[C.SC_OVER] || S.sc[C.SC_PL] === this.human_seat) return null;
      const ply = this.history.length;
      return { ply, promise: compute({ kind: "move", deck: this.deck, history: this.history, level: this.level, seed: (this.seed * 2 + 1 - this.human_seat) * 1000 + ply }) };
    }

    // 待った: 直前の自分の手（とそれに続くAIの手）を取り消す。局面は山札と着手列から作り直す
    undo() {
      if (this.S.sc[C.SC_OVER]) throw new Error("終局後は戻せません");
      const sn = this.snaps.pop();
      if (!sn) throw new Error("戻せる手がありません");
      this.history = this.history.slice(0, sn.n);
      this.S = eng.newGame(this.deck);
      for (const [cell, g, piece] of this.history) eng.applyMove(this.S, cell, g, piece);
      this.meeples = sn.meeples; this.events = sn.events; this.last_ai = sn.last_ai; this.last_coach = sn.last_coach; this.mid = sn.mid;
      this.hint = null;
      this.undos++;
      this.events.push({ player: this.human_seat, text: "待った: 1手戻しました" });
    }

    // 置く前のヒント: 今の局面でのAIの最善手（最強設定の解析）
    async requestHint() {
      const S = this.S;
      if (S.sc[C.SC_OVER] || S.sc[C.SC_PL] !== this.human_seat) throw new Error("あなたの手番ではありません");
      const opts = await compute({ kind: "analyze", deck: this.deck, history: this.history, seed: this.seed * 1000 + 500 + this.history.length });
      this.hint = bestDict((g, p) => this.pieceKind(g, p), opts[0]);
      this.hints++;
    }

    async advanceAi(started) {
      const S = this.S;
      while (!S.sc[C.SC_OVER] && S.sc[C.SC_PL] !== this.human_seat) {
        const job = started && started.ply === this.history.length ? started : this.startAiJob();
        started = null;
        const m = await job.promise;
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
      const who = player !== this.human_seat ? "AI" : this.plays ? "人" : "あなた";  // plays があれば棋譜の再生
      const put = piece >= 0 ? `${KIND_JA[this.pieceKind(g, piece)]}にミープル` : "ミープルなし";
      let text = `${who}: タイルを置き、${put}`;
      if (gain || opp) text += ` ／ 得点 ${who}+${gain}` + (opp ? ` 相手+${opp}` : "");
      this.events.push({ player, text, x, y });
    }

    record() { return gameRecord(C, eng, DATA, this); }

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
        record: over ? this.record() : null,
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
        hint: this.hint,
        can_undo: this.snaps.length > 0 && !over,
        events: this.events.slice(-40),
        placements,
        discarded: sc[C.SC_DISC],
      };
    }
  }

  // ---- 棋譜の再生（送ってもらった棋譜を一手ずつ見る。手は指せない） ----------------
  class ReplayGame extends LocalGame {
    constructor(rec) {
      super(0, rec.human_seat === 1 ? 1 : 0, rec.level || "strong", "", false);
      if (!rec || !Array.isArray(rec.deck) || !Array.isArray(rec.moves)) throw new Error("棋譜の形が違います");
      // 山札は基本セットの71枚そのもの（並びだけ違う）でなければならない
      const want = eng.shuffledDeck(0).slice().sort((a, b) => a - b).join();
      if (rec.deck.slice().sort((a, b) => a - b).join() !== want) throw new Error("山札が基本セットの71枚になっていません");
      this.rec = rec;
      this.deck = rec.deck.map(Number);
      // 山札と指し手を内部の手（マス・向きID・断片）にし、ルールどおりか確かめる
      const S = eng.newGame(this.deck);
      this.plays = rec.moves.map(([x, y, v, p], k) => {
        if (S.sc[C.SC_OVER]) throw new Error(`${k + 1}手目: もう終局しています`);
        const cell = C.cellOf(x, y), g = eng.vbase[S.sc[C.SC_CUR]] + v, piece = p === null || p < 0 ? -1 : p;
        if (!eng.legalMoves(S).some(m => m[0] === cell && m[1] === g && m[2] === piece)) throw new Error(`${k + 1}手目がルール上置けない手です`);
        eng.applyMove(S, cell, g, piece);
        return [cell, g, piece];
      });
      // 形勢の線: 各手数で「今終わったら」の見込みの点差（人 − AI）
      const S2 = eng.newGame(this.deck), h = this.human_seat, curve = [];
      const diff = () => { const p = eng.projected(S2); return p[h] - p[1 - h]; };
      curve.push(diff());
      for (const [cell, g, piece] of this.plays) { eng.applyMove(S2, cell, g, piece); curve.push(diff()); }
      this.curve = curve;
      this.analysis = {};  // 手数 → その手の採点（AIの最善手と何点損したか）
      this.ply = 0;
      this.goto(0);
    }
    // ply 手目（1始まり）を、その手の直前の局面で最強設定で解析して採点する（初心者モードと同じ）
    async analyze(ply) {
      ply = ply | 0;
      if (ply < 1 || ply > this.plays.length || this.analysis[ply]) return;
      const [cell, g, piece] = this.plays[ply - 1];
      const opts = await compute({ kind: "analyze", deck: this.deck, history: this.plays.slice(0, ply - 1), seed: 7000 + ply });
      const best = opts[0], mine = opts.find(o => o.cell === cell && o.g === g && o.piece === piece);
      const S = eng.newGame(this.deck);
      for (const m of this.plays.slice(0, ply - 1)) eng.applyMove(S, m[0], m[1], m[2]);
      this.analysis[ply] = {
        human: S.sc[C.SC_PL] === this.human_seat,
        best: bestDict((gg, p) => this.pieceKind(gg, p), best),
        loss: mine ? Math.round(Math.max(0, best.diff - mine.diff) * 10) / 10 : null,
      };
    }
    goto(ply) {
      ply = Math.max(0, Math.min(this.plays.length, ply | 0));
      this.S = eng.newGame(this.deck);
      this.history = []; this.meeples = []; this.events = []; this.end_meeples = []; this.mid = 0; this.last_ai = null;
      for (let k = 0; k < ply; k++) {
        const [cell, g, piece] = this.plays[k], who = this.S.sc[C.SC_PL];
        this.play(cell, g, piece);
        const [x, y] = C.xyOf(cell);
        this.last_ai = who !== this.human_seat ? { x, y } : null;
      }
      this.ply = ply;
    }
    view() {
      const v = super.view();
      v.placements = [];
      v.record = null;
      v.can_undo = false;
      const last = this.ply ? C.xyOf(this.plays[this.ply - 1][0]) : null;
      const a = this.analysis[this.ply] || null;
      v.replay = { ply: this.ply, total: this.plays.length, last: last && { x: last[0], y: last[1] }, curve: this.curve, analysis: a };
      v.last_coach = a && (a.loss === null || a.loss >= 1) ? { best: a.best, loss: a.loss } : null;
      return v;
    }
  }

  // ---- web/play.html からの問い合わせ（scripts/play_human.py の API と同じ形） ----
  let game = null, live = null;  // live: 再生を開く前の対局（再生を終えたら戻す）
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
    if (path === "/api/replay") {
      const rg = new ReplayGame(body.record);
      if (!(game instanceof ReplayGame)) live = game;
      game = rg;
      if (body.ply !== undefined) game.goto(Number(body.ply));
      return game.view();
    }
    if (path === "/api/replay_goto") {
      if (!(game instanceof ReplayGame)) throw new Error("棋譜を開いていません");
      game.goto(Number(body.ply));
      return game.view();
    }
    if (path === "/api/replay_analyze") {
      if (!(game instanceof ReplayGame)) throw new Error("棋譜を開いていません");
      const g = game;
      await g.analyze(Number(body.ply));
      return g === game ? g.view() : null;
    }
    if (path === "/api/replay_close") {
      if (game instanceof ReplayGame) game = live;
      return game ? game.view() : null;
    }
    if (path === "/api/undo" || path === "/api/hint") {
      if (!game) throw new Error("対局が始まっていません");
      if (path === "/api/undo") game.undo();
      else await game.requestHint();
      return game.view();
    }
    throw new Error("not found");
  };
})(typeof self !== "undefined" ? self : this);
