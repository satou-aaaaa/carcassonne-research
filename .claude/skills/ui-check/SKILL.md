---
name: ui-check
description: 公開ページ（docs/ の対戦ページ・学習ページ）や、それを作る web/・scripts/build_*.py を変えたときに、スマホ幅とPC幅で表示と使いやすさを点検して直す手順。
---

# サイトの UI/UX 点検（carcassonne-research）

サイトの目的は**カルカソンヌプレイヤーの教育**。ページを変えたら毎回、同じ作業の中で点検して直す。

## 1. 機械の点検（必ず）
```bash
node scripts/ui_check.mjs --shots ui-shots   # 全ページ × スマホ幅390px・PC幅1280px
node scripts/ui_check.mjs play.html          # 1ページだけ
```
- ✗ は直す（CI の test.yml `ui` ジョブと `tests/test_ui.py` も同じ点検で落ちる）。
  - コンソールエラー・読み込み失敗
  - 横のはみ出し（ページ全体が横スクロールする）
  - 押す場所が 24×24px 未満（WCAG 2.2 達成基準 2.5.8）、名前のないボタン・入力欄、alt のない画像
  - 対戦ページ: 新しい対局→1枚置いて確定→AIが返す、まで動かない
- △ は目で見て判断する（スマホで高さ 44px 未満＝Apple HIG の目安、12px 未満の文字、横スクロールが要る表）。
- Playwright と Chromium はクラウドセッションに入っている。手元では `npm i -g playwright && npx playwright install chromium`。

## 2. 目で見る点検（スクリーンショット ui-shots/*.png を開く）
- スマホ幅で、表・図・グラフの文字が切れたり小さすぎたりしないか（図の中の文字は約11px以上）。
- 見出しが変なところで折り返していないか（共通 CSS で `word-break: auto-phrase`）。
- 対戦ページ（play_ingame_*.png）: 盤・引いたタイル・確定ボタンがスマホで1画面に収まるか。
- ページ間の行き来ができるか（共通ナビ `scripts/site_nav.py`、対戦ページは下の #home）。
- 学びに役立つか: 本文と図の対応、次に読むページへの案内、用語の揺れ。
- ダーク表示（prefers-color-scheme: dark）で読めない色がないか（気になる変更のときだけ）。

## 3. 直し方
- `docs/*.html` は手で直さない。元（`web/*_template.html`, `web/play.html`, `scripts/build_*.py`,
  `scripts/site_nav.py`）を直して `python scripts/build_pages.py`。`docs/index.html` だけ手書き（共通ナビの CSS を手で合わせる）。
- 全ページに効かせたい CSS は `scripts/site_nav.py` の `NAV_CSS`（index.html と play.html には手で合わせる）。
- 直したらもう一度 1. を回し、スクリーンショットで前後を見比べる。

## 4. 報告
- 直した点を「問題: 何をどう直したか（数値があれば前→後）」で短く書く。
