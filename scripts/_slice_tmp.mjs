import { createRequire } from "module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const [S, base, ...pages] = process.argv.slice(2);
const b = await chromium.launch();
import fs from "fs"; fs.mkdirSync(`${S}/slices`, { recursive: true });
for (const spec of pages) {
  const [pg, w, sel] = spec.split("|");
  const ctx = await b.newContext({ viewport: { width: +w, height: 844 }, locale: pg.startsWith("en/") ? "en-US" : "ja-JP" });
  const p = await ctx.newPage();
  await p.goto(`${base}/${pg}`, { waitUntil: "networkidle" });
  await p.waitForTimeout(1500);
  const name = (pg + "_" + w + (sel ? "_" + sel : "")).replace(/[^a-z0-9_]/gi, "_");
  if (sel) await p.locator("#" + sel).screenshot({ path: `${S}/slices/${name}.png` });
  else await p.screenshot({ path: `${S}/slices/${name}.png` });
  console.log(name);
  await ctx.close();
}
await b.close();
