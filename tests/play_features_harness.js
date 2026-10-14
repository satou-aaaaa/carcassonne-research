// tests/test_play_js.py から node で呼ぶ: 対戦画面の特徴計算（docs/play_features.js）を確かめる。
// 標準入力の JSON {tiles, cases: [{board, meeples}]} を読み、各局面の「今終局した場合に加わる点数」を返す。
"use strict";
const path = require("path");
const F = require(path.join(__dirname, "..", "docs", "play_features.js"));

let buf = "";
process.stdin.on("data", d => (buf += d));
process.stdin.on("end", () => {
  const args = JSON.parse(buf);
  const out = args.cases.map(c => F.endScores(args.tiles, c.board, c.meeples));
  process.stdout.write(JSON.stringify(out));
});
