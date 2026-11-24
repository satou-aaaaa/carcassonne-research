// SNS でリンクを貼ったときに出るカードの画像（docs/og-card.png・docs/en/og-card.png、1200×630）を作る。
//
//   node scripts/make_og_card.mjs
//
// 絵は対戦ページ（docs/play.html）の盤の描き方そのまま。送ってもらった対局（みんなの対局の1局目）の最終盤面を使う。
// 画像は手で作り直すもの（build_pages.py では作らない: 描画の環境で画素が変わり「docs が最新でない」にならないように）。
// カードの <meta> は scripts/i18n.py の social_head が全ページの <head> に入れる。
// X のカード: https://developer.x.com/en/docs/x-for-websites/cards/overview/markup（summary_large_image、画像は 2:1 前後・5MB 未満）

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DOCS = path.join(ROOT, "docs");
const GAME = 1; // みんなの対局の何局目を使うか

function loadPlaywright() {
  const require = createRequire(import.meta.url);
  const tries = ["playwright"];
  try {
    tries.push(path.join(require("child_process").execSync("npm root -g", { encoding: "utf8" }).trim(), "playwright"));
  } catch {}
  for (const t of tries) {
    try {
      return require(t);
    } catch {}
  }
  console.error("playwright が見つかりません（npm i -g playwright）");
  process.exit(2);
}

const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".json": "application/json" };
function serve() {
  const server = http.createServer((req, res) => {
    const p = path.join(DOCS, decodeURIComponent(new URL(req.url, "http://x").pathname));
    if (!p.startsWith(DOCS) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { "content-type": TYPES[path.extname(p)] || "application/octet-stream" });
    fs.createReadStream(p).pipe(res);
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok(server)));
}

const TEXT = {
  ja: { title: "カルカソンヌ", lines: ["強いAIと対戦", "ブラウザで無料・登録なし", "ルール入門・戦略・クイズも"] },
  en: { title: "Carcassonne", lines: ["Play a strong AI", "Free in your browser, no sign-up", "Rules, strategy and quizzes too"] },
};

const { chromium } = loadPlaywright();
const server = await serve();
const base = `http://127.0.0.1:${server.address().port}/`;
const browser = await chromium.launch();
for (const lang of ["ja", "en"]) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, locale: lang === "ja" ? "ja-JP" : "en-US" });
  await page.goto(`${base}${lang === "en" ? "en/" : ""}play.html#replay=${GAME}&ply=999`);
  await page.waitForFunction(() => typeof G !== "undefined" && G && G.replay && G.board.length > 60, null, { timeout: 60000 });
  const url = await page.evaluate((t) => {
    const W = 1200, H = 630, c = document.createElement("canvas");
    c.width = W; c.height = H;
    const g = c.getContext("2d");
    const font = (px, b = "bold ") => `${b}${px}px system-ui, "Hiragino Sans", "Noto Sans CJK JP", "Noto Sans JP", sans-serif`;
    g.fillStyle = "#f4efe4"; g.fillRect(0, 0, W, H);
    // 左: 最終盤面（ミープルは終局前に盤にいたもの）
    const xs = G.board.map((b) => b.x), ys = G.board.map((b) => b.y);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y1 = Math.max(...ys), y0 = Math.min(...ys);
    const cols = x1 - x0 + 1, rows = y1 - y0 + 1, box = 590;
    const S = Math.floor(box / Math.max(cols, rows));
    const ox = 20 + Math.round((box - cols * S) / 2), oy = 20 + Math.round((box - rows * S) / 2);
    for (const b of G.board) g.drawImage(tileCanvas(b.t, b.v), ox + (b.x - x0) * S, oy + (y1 - b.y) * S, S, S);
    const ms = G.end_meeples && G.end_meeples.length ? G.end_meeples : G.meeples, keep = ctx;
    ctx = g;
    try {
      for (const m of ms) {
        const b = G.board.find((q) => q.x === m.x && q.y === m.y);
        if (!b) continue;
        const [ax, ay] = anchors(b.t, b.v)[m.piece];
        meepleGlyph(ox + (m.x - x0 + ax) * S, oy + (y1 - m.y + ay) * S, Math.max(12, S * 0.3), PCOL[m.player], LIB[b.t].variants[b.v].pieces[m.piece].kind === "F");
      }
    } finally { ctx = keep; }
    // 右: ページ名と一言
    const L = 660;
    g.fillStyle = "#2f6b2f"; g.fillRect(L - 24, 150, 8, 330);
    g.fillStyle = "#222"; g.font = font(76); g.fillText(t.title, L, 240);
    g.font = font(46); g.fillStyle = "#b5432f"; g.fillText(t.lines[0], L, 320);
    g.font = font(32, "500 "); g.fillStyle = "#333";
    g.fillText(t.lines[1], L, 390); g.fillText(t.lines[2], L, 445);
    return c.toDataURL("image/png");
  }, TEXT[lang]);
  const out = path.join(DOCS, lang === "en" ? "en" : "", "og-card.png");
  fs.writeFileSync(out, Buffer.from(url.split(",")[1], "base64"));
  console.log(`${path.relative(ROOT, out)} を書き出しました`);
  await page.close();
}
await browser.close();
server.close();
