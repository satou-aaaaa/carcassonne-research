# CLAUDE.md

カルカソンヌ（基本セット・2人対戦）の強いAIを作る研究リポジトリ。背景とロードマップは README.md と docs/ROADMAP.md。

## push する前の確認

```bash
python scripts/check.py --quick   # ruff・整形・公開ページ・slow 以外のテスト
```

PR の作り方・公開ページの作り直し・マージの仕方は `.claude/skills/steward/SKILL.md` が正（こちらが優先）。

## 公開

- GitHub Pages は `main` の `/docs` を公開する。`docs/*.html` は `scripts/build_pages.py` で作り直す（`docs/index.html` だけ手書き）。

## 共通のきまり

- PR の作り方・マージの仕方は共通スキル（PR の手順）と、satou-aaaaa/shared-workflows の `routines/common.md` に従う。
- CI の部品（CI失敗Issue・ブランチ片付け）は shared-workflows の共通部品を呼ぶ。
  リポジトリ側の .github/workflows には呼び出しと設定値だけを書く。
