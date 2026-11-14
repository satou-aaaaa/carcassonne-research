// 公開ページ（docs/*.html）の UI 点検。スマホ幅とPC幅で開き、機械で分かる問題を探す。
//
//   node scripts/ui_check.mjs                 # 点検だけ（問題があれば終了コード 1）
//   node scripts/ui_check.mjs --shots DIR     # 各ページ・各幅のスクリーンショットも DIR に保存
//   node scripts/ui_check.mjs play.html       # 指定したページだけ
//
// Playwright（npm の playwright）と Chromium が要る。クラウドセッションには入っている。
// CI は .github/workflows/ui-check.yml。目で見る点検の手順は .claude/skills/ui-check/SKILL.md。
//
// 見ること（基準）:
//   - コンソールのエラー・読み込み失敗がない
//   - 横方向にはみ出さない（ページ全体が横にスクロールしない）
//   - ボタン・入力欄・ナビのリンクは 24×24px 以上（WCAG 2.2 達成基準 2.5.8）。
//     スマホ幅では高さ 44px 未満を ✗ にする（Apple HIG の目安。全ページ）
//   - ボタン・入力欄・画像に名前（文字・aria-label・alt・label）がある
//   - 本文の文字が 12px 未満でない、viewport の指定がある（12px 未満は ✗）
//   - 対戦ページは「新しい対局」から1手置くところまで動かす
//   - みんなの対局は、棋譜が5000局あっても一覧を分けて並べ、番号で開いた局を再生できる（スマホでも ◀ ▶ が1画面に見える）
//   - 英語ページ（docs/en/）も点検する。日本語ページは ja-JP、英語ページは en-US のブラウザで開く
//   - 言語の自動切り替え: en-US のブラウザでトップを開くと英語版へ、ja-JP で英語版を開くと日本語版へ移る

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DOCS = path.join(ROOT, "docs");

function loadPlaywright() {
  const require = createRequire(import.meta.url);
  const tries = [
    "playwright",
    path.join(process.env.npm_config_prefix || "/opt/node22", "lib/node_modules/playwright"),
  ];
  try {
    const g = require("child_process").execSync("npm root -g", { encoding: "utf8" }).trim();
    tries.push(path.join(g, "playwright"));
  } catch {}
  for (const t of tries) {
    try {
      return require(t);
    } catch {}
  }
  console.error("playwright が見つかりません（npm i -g playwright）");
  process.exit(2);
}

const VIEWPORTS = [
  { name: "mobile", width: 390, height: 844, isMobile: true, hasTouch: true },
  { name: "pc", width: 1280, height: 800, isMobile: false, hasTouch: false },
];

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".css": "text/css",
};

function serve() {
  const server = http.createServer((req, res) => {
    const p = decodeURIComponent(new URL(req.url, "http://x").pathname);
    const f = path.join(DOCS, p === "/" ? "index.html" : p);
    if (!f.startsWith(DOCS) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { "content-type": TYPES[path.extname(f)] || "application/octet-stream" });
    fs.createReadStream(f).pipe(res);
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok(server)));
}

// ページ内で実行する点検。結果は { errors: [], warns: [] }
function inspect(isMobile) {
  const errors = [];
  const warns = [];
  const vw = document.documentElement.clientWidth;
  const desc = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += "#" + el.id;
    else if (el.className && typeof el.className === "string")
      s += "." + el.className.trim().split(/\s+/).join(".");
    const t = (el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 20);
    return t ? `${s}「${t}」` : s;
  };
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none";
  };

  if (!document.querySelector('meta[name="viewport"]')) errors.push("viewport の指定がない");
  if (!document.title.trim()) errors.push("title が空");

  // 横のはみ出し
  const sw = document.scrollingElement.scrollWidth;
  if (sw > vw + 1) {
    const culprits = [];
    for (const el of document.body.querySelectorAll("*")) {
      if (!visible(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.right > vw + 1 && culprits.length < 5) {
        // 横スクロールできる箱の中身は対象外
        let p = el.parentElement;
        let scrolls = false;
        while (p && p !== document.body) {
          const ox = getComputedStyle(p).overflowX;
          if (ox === "auto" || ox === "scroll" || ox === "hidden") scrolls = true;
          p = p.parentElement;
        }
        if (!scrolls) culprits.push(`${desc(el)} 右端${Math.round(r.right)}px`);
      }
    }
    errors.push(`横にはみ出す（ページ幅${sw}px > 画面${vw}px）: ${culprits.join(" / ")}`);
  }

  // 横スクロールの箱（表など）。中身が切れて見えるので、スマホでは避けたい
  const scrollers = [];
  for (const el of document.body.querySelectorAll("*")) {
    if (!visible(el)) continue;
    const ox = getComputedStyle(el).overflowX;
    if ((ox === "auto" || ox === "scroll") && el.scrollWidth > el.clientWidth + 1)
      scrollers.push(`${desc(el)} 中身${el.scrollWidth}px/幅${el.clientWidth}px`);
  }
  if (scrollers.length) warns.push(`横スクロールしないと見えない箱: ${scrollers.slice(0, 4).join(" / ")}`);

  // 押せるもの: 大きさと名前
  const controls = document.querySelectorAll(
    "button, input:not([type=hidden]), select, textarea, nav a, a.btn, [role=button], summary",
  );
  const small = [];
  const smallWarn = [];
  for (const el of controls) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    // チェックボックスは label ごと押せるので label の大きさで見る
    let box = r;
    const lab = el.closest("label") || (el.id && document.querySelector(`label[for="${el.id}"]`));
    if ((el.type === "checkbox" || el.type === "radio") && lab) box = lab.getBoundingClientRect();
    if (box.width < 24 - 0.5 || box.height < 24 - 0.5)
      small.push(`${desc(el)} ${Math.round(box.width)}×${Math.round(box.height)}`);
    else if (isMobile && box.height < 44 - 0.5)
      smallWarn.push(`${desc(el)} 高さ${Math.round(box.height)}`);
    const name =
      el.getAttribute("aria-label") ||
      el.getAttribute("title") ||
      (el.labels && [...el.labels].map((l) => l.textContent).join("")) ||
      el.textContent ||
      el.value ||
      el.getAttribute("placeholder");
    if (!name || !String(name).trim()) errors.push(`名前のない操作部品: ${desc(el)}`);
  }
  if (small.length) errors.push(`押す場所が 24px 未満: ${small.slice(0, 8).join(" / ")}`);
  if (smallWarn.length)
    warns.push(`スマホで高さ 44px 未満が ${smallWarn.length} 個（例: ${smallWarn.slice(0, 4).join(" / ")}）`);

  for (const img of document.querySelectorAll("img")) {
    if (!img.hasAttribute("alt")) errors.push(`alt のない画像: ${img.src.slice(-40)}`);
  }

  // 小さすぎる文字（本文の文字を持つ要素だけ）
  const tiny = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode;
    if (!n.textContent.trim()) continue;
    const el = n.parentElement;
    if (!el || !visible(el) || el.closest("svg, kbd")) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs < 12) tiny.add(`${desc(el)} ${fs}px`);
  }
  if (tiny.size) warns.push(`12px 未満の文字が ${tiny.size} か所（例: ${[...tiny].slice(0, 3).join(" / ")}）`);

  return { errors, warns };
}

// 対戦ページ: 新しい対局を始め、置ける場所に1枚置いて確定するまで
async function exercisePlay(page, shotDir, vpName, moveProblems = []) {
  // 開いた直後に「新しい対局」の窓が出る。出ていなければボタンで開く
  let dlg = page.locator("dialog[open]");
  if (!(await dlg.count())) {
    await page.click("#btnNew");
    dlg = page.locator("dialog[open]");
  }
  await dlg.locator("button.primary").click();
  // 先手なので自分の番から始まる
  await page.waitForTimeout(1000);
  await page.waitForFunction(() => typeof G !== "undefined" && G && G.placements && G.placements.length, null, {
    timeout: 15000,
  });
  // 置ける場所の真ん中を押す（盤面の座標はページの関数で求める）
  const pt = await page.evaluate(() => {
    const p = G.placements[0];
    const r = document.getElementById("board").getBoundingClientRect();
    return { x: r.left + cellLeft(p.x) + view.s / 2, y: r.top + cellTop(p.y) + view.s / 2 };
  });
  const boardH = () => page.evaluate(() => Math.round(document.getElementById("board").getBoundingClientRect().height));
  const h0 = await boardH();
  await page.mouse.click(pt.x, pt.y);
  await page.waitForTimeout(300);
  // 仮置きしても盤の高さが変わらないこと（変わると、押そうとしたタイルや円が指の下から動く）
  const h1 = await boardH();
  if (Math.abs(h1 - h0) > 2) moveProblems.push(`仮置きすると盤の高さが ${h0}px → ${h1}px に変わる`);
  // 仮置きすると、タイルのすぐ下に操作バー（回転・やめる・確定）が出る
  if (!(await page.locator("#tileBar:not([hidden]) #tbOk").count())) return false;
  if (shotDir) await page.screenshot({ path: path.join(shotDir, `play_pending_${vpName}.png`) });
  await page.click("#tbOk");
  // 駒を置くかの選択が出たら「置かない」
  const none = page.locator("#pieceBtns button", { hasText: /^(置かない|None)$/ });
  if (await none.count()) await none.first().click();
  if (await page.locator("#btnOk:not([disabled])").count()) await page.click("#btnOk");
  // AI の返し手を待つ（自分の番に戻り、置ける場所が出るまで）
  await page.waitForFunction(() => G && G.board.length >= 3 && myTurn(), null, { timeout: 30000 });
  await page.waitForTimeout(300);
  return true;
}

// 対戦ページの対局の途中（盤が広がって画面に入りきらない頃）を、小さいスマホ（iPhone SE 320×568）で確かめる。
// 2026-11 の点検で見つかった問題の再発防止:
//   - 置ける緑のマスが右下のボタン（陣地・全体を表示）の下に隠れて押せない
//   - 画面の外にある置ける場所が分からない（緑の矢印が出ない・矢印がボタンの下で押せない）
//   - 案内文の行数が変わるたびに盤が上下に動く（押そうとしたマスが指の下からずれる）／案内文が切れる
//   - 読み込み直す（スマホでアプリを切り替えるとよく起きる）と、途中の対局が消える
const MID_TURNS = 24;
async function exerciseMidGame(browser, base, file) {
  const problems = [];
  const ctx = await browser.newContext({
    viewport: { width: 320, height: 568 }, isMobile: true, hasTouch: true, deviceScaleFactor: 1,
    locale: file.startsWith("en/") ? "en-US" : "ja-JP",
  });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => problems.push(`スクリプトエラー: ${String(e).slice(0, 160)}`));
  await page.goto(base + file, { waitUntil: "load" });
  await page.waitForSelector("#dlg[open]");
  await page.evaluate(() => {
    $("fSeed").value = "1";
    $("fLevel").value = "greedy";
    $("fCoach").checked = false;
  });
  await page.locator("#dlg button.primary").click();
  const myTurnNow = () => page.waitForFunction(() => G && G.board && (G.over || myTurn()), null, { timeout: 30000 });
  const tops = new Set();
  let covered = 0, noArrow = 0, badArrow = 0, clipped = 0;
  for (let t = 1; t <= MID_TURNS; t++) {
    await myTurnNow();
    await page.waitForTimeout(400); // 盤を寄せる動き（260ms）が終わるまで
    const r = await page.evaluate(() => {
      const c = cv.getBoundingClientRect(), s = view.s, a = safeArea();
      let cov = 0, off = 0;
      for (const p of placeCells()) {
        const x = cellLeft(p.x) + s / 2, y = cellTop(p.y) + s / 2;
        const L = x - s / 2, T = y - s / 2;
        if (L + s <= 0 || L >= a.w || T + s <= a.top || T >= a.bottom) { off++; continue; } // まったく見えない（矢印で示す）
        if (x < 0 || x > a.w || y < a.top || y > a.bottom) continue; // 端だけ見えている（見えている所を押せる）
        if (document.elementFromPoint(c.left + x, c.top + y) !== cv) cov++;
      }
      const marks = typeof offMarks === "undefined" ? [] : offMarks;
      const badMarks = marks.filter((m) => document.elementFromPoint(c.left + m.px, c.top + m.py) !== cv).length;
      const h = $("hint");
      return { cov, off, marks: marks.length, badMarks, top: Math.round(c.top), clip: h.scrollHeight > h.clientHeight + 1 };
    });
    covered += r.cov;
    if (r.off && !r.marks) noArrow++;
    badArrow += r.badMarks;
    if (r.clip) clipped++;
    tops.add(r.top);
    // 置いた直後（AIの考え中）も盤の上端が変わらないこと
    tops.add(await page.evaluate(() => { const p = G.placements[0]; sendMove(p.x, p.y, p.v, null); return Math.round(cv.getBoundingClientRect().top); }));
  }
  await myTurnNow();
  if (covered) problems.push(`置ける緑のマスが盤の上のボタンの下に隠れて押せない（${covered} マス）`);
  if (noArrow) problems.push(`置ける場所が画面の外にあるのに緑の矢印が出ない（${noArrow} 手）`);
  if (badArrow) problems.push(`緑の矢印がボタンの下に隠れて押せない（${badArrow} 個）`);
  if (clipped) problems.push(`案内文が2行に収まらず切れる（${clipped} 手）`);
  if (tops.size > 1) problems.push(`手番ごとに盤の上端が動く（${[...tops].join(", ")}px）`);
  // 読み込み直しても途中の対局が続けられる（待ったも使える）
  const before = await page.evaluate(() => G.board.length);
  await page.reload({ waitUntil: "load" });
  try {
    await page.waitForFunction(() => G && G.board && myTurn(), null, { timeout: 30000 });
    const after = await page.evaluate(() => ({ n: G.board.length, undo: G.can_undo }));
    if (after.n !== before || !after.undo) problems.push(`読み込み直すと途中の対局が戻らない（盤 ${before} 枚 → ${after.n} 枚、待った ${after.undo}）`);
  } catch {
    problems.push("読み込み直すと途中の対局が消える");
  }
  await ctx.close();
  return problems;
}

// 終局の「振り返り」（初心者モードの採点から、損の大きかった手を並べる）を、スマホ幅で終局まで指して確かめる。
// 2026-11 の点検で見つかった問題の再発防止:
//   - 終局後に学びが残らない（振り返りの欄・損の大きかった手のボタン・学習ページへの案内が無い）
//   - 結果の欄（ページの下の方）から再生を始めても画面が下のままで、盤が見えない
//   - 1手目の盤の欄が空白ばかり（タイルが小さい。MAX_TOUCH_TILE）
//   - 終局後も「山札に残るタイル」が全部 ×0 のまま場所を取る
async function exerciseEndGame(browser, base, file) {
  const problems = [];
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 1,
    locale: file.startsWith("en/") ? "en-US" : "ja-JP",
  });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => problems.push(`スクリプトエラー: ${String(e).slice(0, 160)}`));
  await page.goto(base + file, { waitUntil: "load" });
  await page.waitForSelector("#dlg[open]");
  await page.evaluate(() => { $("fSeed").value = "2"; $("fLevel").value = "greedy"; $("fCoach").checked = true; });
  await page.locator("#dlg button.primary").click();
  for (let k = 0; ; k++) {
    await page.waitForFunction(() => G && G.board && (G.over || myTurn()), null, { timeout: 60000 });
    if (await page.evaluate(() => G.over)) break;
    if (k === 0) {
      await page.waitForTimeout(400);
      const s0 = await page.evaluate(() => Math.round(view.s));
      if (s0 < 96) problems.push(`1手目の盤のタイルが小さく、盤の欄が空白ばかり（${s0}px、96px 以上にしたい）`);
    }
    await page.evaluate((k) => { const ps = G.placements, p = ps[(k * 7) % ps.length]; sendMove(p.x, p.y, p.v, null); }, k);
  }
  await page.waitForTimeout(500);
  if (await page.locator("#remainSec").isVisible()) problems.push("終局後も「山札に残るタイル」（全部 ×0）が出たまま");
  const go = page.locator("#result .review .rvGo");
  if (!(await page.locator("#result .review").count())) problems.push("終局の欄に振り返りが無い");
  else if (!(await go.count())) problems.push("振り返りに損の大きかった手のボタンが無い");
  else if (!(await page.locator('#result .review a[href="ai_tips.html"]').count())) problems.push("振り返りに学習ページへの案内が無い");
  else {
    const ply = Number(await go.first().getAttribute("data-ply"));
    await go.first().scrollIntoViewIfNeeded();
    await go.first().click();
    await page.waitForFunction(() => G && G.replay, null, { timeout: 30000 });
    await page.waitForTimeout(1200); // スクロールの動きが終わるまで
    const r = await page.evaluate(() => ({ ply: G.replay.ply, y: Math.round(scrollY), top: Math.round(cv.getBoundingClientRect().top) }));
    if (r.ply !== ply) problems.push(`振り返りの手を押しても、その手から再生しない（${ply}手目 → ${r.ply}手目）`);
    if (r.y > 5 || r.top < 0) problems.push(`振り返りから再生しても盤が画面の上に見えない（scrollY ${r.y}px、盤の上端 ${r.top}px）`);
    if (!(await page.locator("#remainSec").isVisible())) problems.push("棋譜の再生中に「山札に残るタイル」が出ない");
    await page.click("#rpClose");
    await page.waitForFunction(() => G && G.over && !G.replay, null, { timeout: 30000 });
    if (!(await page.locator("#result .review .rvGo").count())) problems.push("再生を終えると振り返りが消える");
  }
  await ctx.close();
  return problems;
}

// 英語のページで、文と文の間の空白が抜けていないか（日本語の文をつないだ所を訳すと抜けやすい）
function englishJoins(text) {
  const bad = [];
  for (const m of text.matchAll(/[a-z)][.!?][“"A-Z][a-z]|\w \.(?:\s|$)/g)) bad.push(text.slice(Math.max(0, m.index - 25), m.index + 10));
  return bad;
}

// 棋譜が何千局になっても「みんなの対局」が崩れない・重くならないか。一覧（human_games/index.json）を
// MANY 局分のにせものに差し替えて開き、一覧が分けて並ぶこと、番号で開いた局が再生でき、
// スマホでも ◀ ▶ が盤と同じ1画面に見えることを確かめる（棋譜の本体は届いている1局目を使い回す）
const MANY = 5000;
async function exerciseManyGames(ctx, base, file, isMobile) {
  const problems = [];
  const first = path.join(DOCS, "human_games", "0.json");
  if (!fs.existsSync(first)) return problems; // まだ届いた棋譜がない
  const sample = JSON.parse(fs.readFileSync(path.join(DOCS, "human_games", "0.json"), "utf8"))[0];
  const h = sample.human_seat;
  const row = [sample.level, h, sample.scores[h], sample.scores[1 - h], sample.moves.length, 0];
  const page = await ctx.newPage();
  page.on("pageerror", (e) => problems.push(`スクリプトエラー: ${String(e).slice(0, 160)}`));
  await page.route("**/human_games/index.json", (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify(Array.from({ length: MANY }, () => row)) }));
  await page.route(/human_games\/\d+\.json$/, (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify(Array.from({ length: 100 }, () => sample)) }));
  await page.goto(base + file, { waitUntil: "load" });
  await page.waitForSelector("#games li", { timeout: 15000 });
  const g = await page.evaluate(() => ({
    li: document.querySelectorAll("#games li").length,
    height: document.documentElement.scrollHeight,
    over: document.documentElement.scrollWidth > window.innerWidth + 1,
  }));
  if (g.li > 50) problems.push(`棋譜${MANY}局で一覧に ${g.li} 局を一度に並べている（分けて並べる）`);
  if (g.height > 20000) problems.push(`棋譜${MANY}局でページの高さが ${g.height}px`);
  if (g.over) problems.push(`棋譜${MANY}局でページが横にはみ出す`);
  await page.click("#pgNext");
  await page.fill("#jumpNo", String(MANY - 1));
  await Promise.all([page.waitForURL(/play\.html#replay=/), page.click("#jump button")]);
  try {
    await page.waitForSelector("#replayBar:not([hidden])", { timeout: 20000 });
    await page.waitForTimeout(500);
    // ◀ ▶・形勢グラフ・その手の説明までが1画面に入ること（評価の切り替え・リンクのボタンは下にあってよい）
    const bar = await page.evaluate(() => ["rpNext", "rpGraph", "rpNote"].every(id => document.getElementById(id).getBoundingClientRect().bottom <= window.innerHeight));
    if (isMobile && !bar) problems.push("再生の ◀ ▶ が最初の画面に見えない（スクロールしないと押せない）");
    if (isMobile) {
      // 終局まで進めても、スマホではタイルが小さくなりすぎず（MIN_AUTO_TILE 以上）、直前に置いたマスが盤の中に見えること
      await page.click("#rpLast");
      await page.waitForTimeout(800);
      const v = await page.evaluate(() => {
        const r = cv.getBoundingClientRect(), l = G.replay.last;
        const inside = !!l && cellLeft(l.x) >= 0 && cellTop(l.y) >= 0 && cellLeft(l.x) + view.s <= r.width && cellTop(l.y) + view.s <= r.height;
        return { s: Math.round(view.s), min: typeof MIN_AUTO_TILE === "number" ? MIN_AUTO_TILE : 36, inside, h: Math.round(r.height) };
      });
      if (v.s < v.min) problems.push(`終盤の盤のタイルが ${v.s}px（スマホは ${v.min}px 以上にする）`);
      if (!v.inside) problems.push("終盤に再生で進めると、直前に置いたマスが盤の外になる");
      if (v.h < 300) problems.push(`再生中の盤の高さが ${v.h}px しかない`);
    }
  } catch (e) {
    problems.push(`番号で開いた局が再生できない: ${String(e).slice(0, 120)}`);
  }
  await page.close();
  return problems;
}

async function main() {
  const args = process.argv.slice(2);
  const shotDir = args.includes("--shots") ? args[args.indexOf("--shots") + 1] : null;
  if (shotDir) fs.mkdirSync(shotDir, { recursive: true });
  const only = args.filter((a) => a.endsWith(".html"));
  const pages = only.length
    ? only
    : [
        ...fs.readdirSync(DOCS).filter((f) => f.endsWith(".html")).sort(),
        ...fs.readdirSync(path.join(DOCS, "en")).filter((f) => f.endsWith(".html")).sort().map((f) => "en/" + f),
      ];

  const { chromium } = loadPlaywright();
  if (args.includes("--probe")) {
    // Playwright と Chromium が使えるかだけ確かめる（tests/test_ui.py が使う）
    const b = await chromium.launch();
    await b.close();
    return;
  }
  const browser = await chromium.launch();
  const server = await serve();
  const base = `http://127.0.0.1:${server.address().port}/`;
  let failed = 0;

  // 言語の自動切り替え（初めて来た人。選んだ言語は localStorage に覚える）
  for (const [locale, from, to] of [
    ["en-US", "", "en/index.html"],
    ["en-US", "rules.html", "en/rules.html"],
    ["ja-JP", "en/quiz.html", "quiz.html"],
    ["ja-JP", "index.html", "index.html"],
    ["fr-FR", "strategy.html", "en/strategy.html"],
  ]) {
    const ctx = await browser.newContext({ locale });
    const page = await ctx.newPage();
    await page.goto(base + from, { waitUntil: "load" });
    await page.waitForLoadState("load");
    const got = page.url().replace(base, "");
    const ok = got === to;
    console.log(`${ok ? "✓" : "✗"} 言語の自動切り替え ${locale} ${from || "/"} → ${got || "/"}`);
    if (!ok) failed++;
    if (ok && locale === "en-US" && from === "") {
      // 「日本語」を押すと日本語版に移り、以後は英語版に移されない
      await page.click('nav.site a[data-lang="ja"]');
      await page.waitForLoadState("load");
      await page.goto(base + "rules.html", { waitUntil: "load" });
      const stay = page.url().replace(base, "") === "rules.html";
      console.log(`${stay ? "✓" : "✗"} 選んだ言語（日本語）を覚える`);
      if (!stay) failed++;
    }
    await ctx.close();
  }

  for (const vp of VIEWPORTS) {
    const ctxs = {};
    const ctxFor = async (locale) =>
      (ctxs[locale] ||= await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        isMobile: vp.isMobile,
        hasTouch: vp.hasTouch,
        deviceScaleFactor: 1,
        locale,
      }));
    for (const file of pages) {
      const ctx = await ctxFor(file.startsWith("en/") ? "en-US" : "ja-JP");
      const page = await ctx.newPage();
      const problems = [];
      page.on("console", (m) => {
        if (m.type() === "error") problems.push(`コンソールエラー: ${m.text().slice(0, 160)}`);
      });
      page.on("pageerror", (e) => problems.push(`スクリプトエラー: ${String(e).slice(0, 160)}`));
      page.on("requestfailed", (r) => problems.push(`読み込み失敗: ${r.url().replace(base, "")}`));
      page.on("response", (r) => {
        if (r.status() >= 400) problems.push(`読み込み失敗 ${r.status()}: ${r.url().replace(base, "")}`);
      });
      await page.goto(base + file, { waitUntil: "load" });
      await page.waitForTimeout(300);
      let res = await page.evaluate(inspect, vp.isMobile);
      if (shotDir)
        await page.screenshot({ path: path.join(shotDir, `${file.replace(".html", "").replace("/", "_")}_${vp.name}.png`), fullPage: true });
      if (page.url() !== base + file) problems.push(`別のページに移された: ${page.url().replace(base, "")}`);
      if (file.endsWith("play.html")) {
        try {
          const placed = await exercisePlay(page, shotDir, vp.name, problems);
          if (!placed) problems.push("対戦ページ: 最初の1枚を置ける場所が見つからない");
          const r2 = await page.evaluate(inspect, vp.isMobile);
          res = { errors: [...res.errors, ...r2.errors], warns: [...res.warns, ...r2.warns] };
          if (shotDir)
            await page.screenshot({ path: path.join(shotDir, `${file.replace("play.html", "").replace("/", "_")}play_ingame_${vp.name}.png`), fullPage: true });
        } catch (e) {
          problems.push(`対戦ページの操作に失敗: ${String(e).slice(0, 160)}`);
        }
      }
      if (file.startsWith("en/")) {
        // 終局の欄（棋譜を送る説明）は対局が終わるまで出ないので、組み立てる関数の文も確かめる
        const text = await page.evaluate(() => document.body.innerText + "\n" +
          (() => {
            if (typeof shareHtml !== "function") return "";
            // 振り返りの文（終局まで出ない）は、にせものの採点で組み立てる
            const keep = G, best = { x: 0, y: 1, v: 0, piece: 0, kind: "City" };
            G = { review: [{ ply: 3, loss: 4.2, best }, { ply: 5, loss: 0.3, best }, { ply: 7, loss: 2.5, best: { ...best, piece: null, kind: null } }, { ply: 9, loss: 2.1, best }] };
            const rv = reviewHtml();
            G = keep;
            const d = Object.assign(document.createElement("div"), { innerHTML: rv + shareHtml() });
            d.style.cssText = "position:absolute;left:-9999px;width:600px";
            document.body.appendChild(d);
            const t = d.innerText;
            d.remove();
            return t;
          })());
        for (const b of englishJoins(text)) problems.push(`英文の空白が抜けている: 「${b}」`);
      }
      if (file.endsWith("play.html") && vp.isMobile) {
        const mid = await exerciseMidGame(browser, base, file);
        console.log(`${mid.length ? "✗" : "✓"} ${file} 対局の途中 ${MID_TURNS}手 [iPhone SE 320px]`);
        for (const e of mid) console.log(`    ✗ ${e}`);
        failed += mid.length ? 1 : 0;
        const end = await exerciseEndGame(browser, base, file);
        console.log(`${end.length ? "✗" : "✓"} ${file} 終局の振り返り [スマホ 390px]`);
        for (const e of end) console.log(`    ✗ ${e}`);
        failed += end.length ? 1 : 0;
      }
      // スマホで高さ 44px 未満の部品は全ページ ✗ にする（2026-11 の点検で、対戦ページの新しい対局・設定の選択欄が
      // 31〜35px、クイズの問題番号が 30px、コツ集の目次が 39px だった。△ のままだと残り続けたので ✗ で止める）
      if (vp.isMobile)
        for (const w of res.warns.filter((w) => w.includes("高さ 44px 未満"))) problems.push(w);
      // 12px 未満の文字も同じ理由で ✗ にする（残りタイルの ×N・難しさのラベルが 11px のまま残っていた）
      for (const w of res.warns.filter((w) => w.startsWith("12px 未満"))) problems.push(w);
      const errs = [...new Set([...problems, ...res.errors])];
      const warns = [...new Set(res.warns.filter((w) => !problems.includes(w)))];
      const mark = errs.length ? "✗" : "✓";
      console.log(`${mark} ${file} [${vp.name} ${vp.width}px]`);
      for (const e of errs) console.log(`    ✗ ${e}`);
      for (const w of warns) console.log(`    △ ${w}`);
      failed += errs.length ? 1 : 0;
      await page.close();
    }
    for (const file of pages.filter((f) => f.endsWith("games.html"))) {
      const errs = await exerciseManyGames(await ctxFor(file.startsWith("en/") ? "en-US" : "ja-JP"), base, file, vp.isMobile);
      console.log(`${errs.length ? "✗" : "✓"} ${file} 棋譜${MANY}局 [${vp.name} ${vp.width}px]`);
      for (const e of errs) console.log(`    ✗ ${e}`);
      failed += errs.length ? 1 : 0;
    }
    for (const c of Object.values(ctxs)) await c.close();
  }
  await browser.close();
  server.close();
  if (failed) {
    console.log(`\n${failed} 件のページ×幅で問題があります（✗）。△ は目で見て判断する注意です。`);
    process.exit(1);
  }
  console.log("\nすべてのページで ✗ はありません（△ は目で見て判断）。");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
