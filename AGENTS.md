# AGENTS.md

<!-- AI エージェント共通の指示（Claude・Codex・Gemini・Copilot などが読む）。CLAUDE.md はこれを取り込むだけ。 -->

カルカソンヌ（基本セット・2人対戦）の強いAIを作る研究リポジトリ。背景とロードマップは README.md と docs/ROADMAP.md。

## 準備（最初に一度）

```bash
bash scripts/setup.sh   # .venv を作り requirements.txt を入れる（Python の版は .python-version）。何度実行してもよい（Windows は Git Bash で）
```

以後のコマンドは .venv の Python で動かす。Claude Code のクラウドセッションでは `.claude/settings.json` のフックが自動で実行し、.venv を PATH の先頭に置く。

## push する前の確認

```bash
python scripts/check.py --quick   # ruff・整形・公開ページ・slow 以外のテスト
```

このリポジトリだけの PR の決まり（確認コマンド・公開ページの作り直し）は `.claude/skills/steward/SKILL.md`（共通の手順より優先）。

## 公開

- GitHub Pages は `main` の `/docs` を公開する。`docs/*.html` は `scripts/build_pages.py` で作り直す（`docs/index.html` だけ手書き）。
- 対戦ページ・コツ集・クイズのAIは、いつも最新チャンピオン（`models/eval_champion.npy`）。チャンピオンが変わると `selfplay.yml` と `ai-content.yml` が自動で作り直す。AIの成績や判断例を本文に手で書かない（集計値から組み立て、`build_tips_page.py` の check_claims で確かめる）。

## 共通のきまり

- PR の作り方・マージの仕方は satou-aaaaa/shared-workflows の `routines/pr.md`、全体のきまりは `routines/common.md` に従う。
- CI の部品（CI失敗Issue・ブランチ片付け）は shared-workflows の共通部品を呼ぶ。
  リポジトリ側の .github/workflows には呼び出しと設定値だけを書く。
- Claude 以外の AI・人が作業するときは、shared-workflows の `routines/tool-map.md`（道具の置き換え）と `routines/without-claude.md` を読む。
