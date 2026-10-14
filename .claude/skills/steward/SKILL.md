---
name: steward
description: このリポジトリでPRを作る・直す・CIを通す・マージするときの手順。push前の確認、公開ページの作り直し、マージの仕方を決めている。
---

# PR の手順（carcassonne-research）

## push する前
1. `python scripts/check.py --quick` を実行する（ruff・整形・公開ページ・slow 以外のテスト、約20秒）。
   - lint や整形で落ちたら `python scripts/check.py --fix --quick` で直してから見直す。
   - エンジン（`src/carcassonne/fast*.py`, `state.py`, `mcts.py`）を触ったときは `--quick` を付けずに全テストを回す。
2. `data/`、`web/*_template.html`、`scripts/build_*.py`、`scripts/site_nav.py`、`scripts/board_svg.py` を
   変えたら `python scripts/build_pages.py` で `docs/` を作り直し、同じコミットに入れる。
   `docs/*.html` は手で直さない（`docs/index.html` だけは手書き）。
3. 本文に数値を書くページ（`docs/rules.html` など）は、組み立てスクリプトがエンジンで検算する。
   検算で止まったら、数値か局面を直す。検算を外さない。

## CI
- `.github/workflows/test.yml` が `python scripts/check.py`（全テスト込み、約2分）を実行する。
- 落ちたら、ローカルで同じ `scripts/check.py` を再現してから直す。`slow` マークのテストを
  CI で飛ばしたり、テストを無効にしたりしない。

## マージ
- 持ち主（satou-aaaaa）が「マージして」と言ったPRは、CI が緑で未解決のレビューがなければ、
  ドラフトを解除して squash マージする。タイトルは PR のタイトルをそのまま使う。
- マージ後にブランチを再利用するときは、`origin/main` から作り直す。

## 公開
- GitHub Pages は `main` の `/docs` を公開する設定（Settings → Pages）。マージすれば反映される。
