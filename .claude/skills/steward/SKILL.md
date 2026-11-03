---
name: steward
description: このリポジトリでPRを作る・直す・CIを通す・マージするときの手順。push前の確認、公開ページの作り直し、マージの仕方を決めている。
---

# PR の手順（carcassonne-research）

共通の手順（PR の書き方・CI・コンフリクト・マージ）は satou-aaaaa/shared-workflows の `routines/pr.md`。ここにはこのリポジトリだけの決まりを書く（食い違ったらこちらが優先）。

## push する前
1. `python scripts/check.py --quick` を実行する（ruff・整形・公開ページ・slow 以外のテスト、約20秒）。
   - lint や整形で落ちたら `python scripts/check.py --fix --quick` で直してから見直す。
   - エンジン（`src/carcassonne/fast*.py`, `state.py`, `mcts.py`）を触ったときは `--quick` を付けずに全テストを回す。
2. `data/`、`web/*_template.html`、`scripts/build_*.py`、`scripts/site_nav.py`、`scripts/board_svg.py` を
   変えたら `python scripts/build_pages.py` で `docs/` を作り直し、同じコミットに入れる。
   `docs/*.html` は手で直さない（`docs/index.html` だけは手書き）。
3. 公開ページ（docs/）やその元を変えたら、`.claude/skills/ui-check/SKILL.md` の手順でスマホ幅・PC幅の
   UI 点検をする（`node scripts/ui_check.mjs --shots ui-shots` と、スクリーンショットの目視）。
4. 本文に数値を書くページ（`docs/rules.html` など）は、組み立てスクリプトがエンジンで検算する。
   検算で止まったら、数値か局面を直す。検算を外さない。

## CI
- `.github/workflows/test.yml` が `python scripts/check.py`（全テスト込み、約2分）と、UI 点検（`ui` ジョブ、`node scripts/ui_check.mjs`）を実行する。
- 落ちたら、ローカルで同じ `scripts/check.py` を再現してから直す。`slow` マークのテストを
  CI で飛ばしたり、テストを無効にしたりしない。

## 自動の PR（auto/*）
- selfplay・AI content が作る PR は `scripts/merge_via_pr.sh` が作る。GITHUB_TOKEN の PR では pull_request の実行が承認待ちになるので、
  コミットに CI を飛ばす印を付けて承認待ちを作らせず、test・Secret scan を workflow_dispatch で回して、通ったときだけマージする。
  入れてよいのは生成物だけ（`AUTO_PATHS`）。
- 人が書くコミットの題・本文には、CI を飛ばす印（`[skip ci]` など）を書かない。書くとその push・PR の CI が全部動かなくなる。
- CI から gh を呼ぶときは `source scripts/gh_retry.sh` して `ghr gh ...`（5xx をやり直す）。Issue を作るのは `gh_issue_create_once`。
- selfplay・AI content に gh を呼ぶ手順を足したら、`tests/test_workflow_rehearsal.py` の REHEARSED に足し、にせものの gh（本物の上限・1回目は 504）で通しで動かす。本番でしか動かない手順は、ここで動かさないと数時間後に初めて落ちる（#92・#110・#118）。ワークフローは CI の actionlint も見る。
- コツ集の言い切りが新しい集計と合わないと `data/tips_blocked.json` と Issue ができる。直し方は Issue に書いてある。

## マージ
- 共通の手順（`routines/pr.md`）どおり、CI が緑で未解決のレビューが無ければ squash マージしてよい（satou さん 2026-10-10 にマージを任されている）。

## 公開
- GitHub Pages は `main` の `/docs` を公開する設定（Settings → Pages）。マージすれば反映される。
