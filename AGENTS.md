# AGENTS.md

<!-- AI エージェント共通の指示（Claude・Codex・Gemini・Copilot などが読む）。CLAUDE.md はこれを取り込むだけ。 -->

カルカソンヌ（基本セット・2人対戦）の強いAIを作る研究リポジトリ。背景とロードマップは README.md と docs/ROADMAP.md。

## push する前の確認

```bash
python scripts/check.py --quick   # ruff・整形・公開ページ・slow 以外のテスト
```

このリポジトリだけの PR の決まり（確認コマンド・公開ページの作り直し）は `.claude/skills/steward/SKILL.md`（共通の手順より優先）。

## 公開

- GitHub Pages は `main` の `/docs` を公開する。`docs/*.html` は `scripts/build_pages.py` で作り直す（`docs/index.html` だけ手書き）。

## 共通のきまり

- PR の作り方・マージの仕方は satou-aaaaa/shared-workflows の `routines/pr.md`、全体のきまりは `routines/common.md` に従う。
- CI の部品（CI失敗Issue・ブランチ片付け）は shared-workflows の共通部品を呼ぶ。
  リポジトリ側の .github/workflows には呼び出しと設定値だけを書く。
- Claude 以外の AI・人が作業するときは、shared-workflows の `routines/tool-map.md`（道具の置き換え）と `routines/without-claude.md` を読む。
