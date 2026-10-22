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
//     スマホ幅では高さ 44px 未満を「注意」として数える（Apple HIG の目安）
//   - ボタン・入力欄・画像に名前（文字・aria-label・alt・label）がある
//   - 本文の文字が 12px 未満でない、viewport の指定がある
//   - 対戦ページは「新しい対局」から1手置くところまで動かす

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
async function exercisePlay(page) {
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
  await page.mouse.click(pt.x, pt.y);
  await page.waitForTimeout(300);
  if (!(await page.locator("#btnOk:not([disabled])").count())) return false;
  await page.click("#btnOk");
  // 駒を置くかの選択が出たら「置かない」
  const none = page.locator("#pieceBtns button", { hasText: "置かない" });
  if (await none.count()) await none.first().click();
  if (await page.locator("#btnOk:not([disabled])").count()) await page.click("#btnOk");
  // AI の返し手を待つ（自分の番に戻り、置ける場所が出るまで）
  await page.waitForFunction(() => G && G.board.length >= 3 && myTurn(), null, { timeout: 30000 });
  await page.waitForTimeout(300);
  return true;
}

async function main() {
  const args = process.argv.slice(2);
  const shotDir = args.includes("--shots") ? args[args.indexOf("--shots") + 1] : null;
  if (shotDir) fs.mkdirSync(shotDir, { recursive: true });
  const only = args.filter((a) => a.endsWith(".html"));
  const pages = only.length
    ? only
    : fs.readdirSync(DOCS).filter((f) => f.endsWith(".html")).sort();

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

  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      isMobile: vp.isMobile,
      hasTouch: vp.hasTouch,
      deviceScaleFactor: 1,
      locale: "ja-JP",
    });
    for (const file of pages) {
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
        await page.screenshot({ path: path.join(shotDir, `${file.replace(".html", "")}_${vp.name}.png`), fullPage: true });
      if (file === "play.html") {
        try {
          const placed = await exercisePlay(page);
          if (!placed) problems.push("対戦ページ: 最初の1枚を置ける場所が見つからない");
          const r2 = await page.evaluate(inspect, vp.isMobile);
          res = { errors: [...res.errors, ...r2.errors], warns: [...res.warns, ...r2.warns] };
          if (shotDir)
            await page.screenshot({ path: path.join(shotDir, `play_ingame_${vp.name}.png`), fullPage: true });
        } catch (e) {
          problems.push(`対戦ページの操作に失敗: ${String(e).slice(0, 160)}`);
        }
      }
      const errs = [...new Set([...problems, ...res.errors])];
      const warns = [...new Set(res.warns)];
      const mark = errs.length ? "✗" : "✓";
      console.log(`${mark} ${file} [${vp.name} ${vp.width}px]`);
      for (const e of errs) console.log(`    ✗ ${e}`);
      for (const w of warns) console.log(`    △ ${w}`);
      failed += errs.length ? 1 : 0;
      await page.close();
    }
    await ctx.close();
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
