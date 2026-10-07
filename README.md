# carcassonne-research

カルカソンヌ（基本ルール・2人対戦）の強いAIを作るための研究プロジェクト。

## スコープ

- 対象: 基本セット（72枚）・2人対戦のみ。拡張・3人以上は対象外。
- 主目的: 強いAIエージェントの構築と手法比較（MCTS／評価関数付き探索／強化学習）。
- 副次的に、自己対戦ログから戦略の統計分析（先手有利、農民運用など）を行う。

## 方針

- ルールエンジンを最優先で作り、テストで正しさを担保する（AIの強さの前提）。
- すべての対戦は乱数シードで再現可能にし、ログ（JSONL）を保存する。
- 実験は設定ファイルとシード付きで記録し、結果を再現できるようにする。

ロードマップは [docs/ROADMAP.md](docs/ROADMAP.md) を参照。
ゲームの歴史・競技シーン・著名プレイヤーは [docs/BACKGROUND.md](docs/BACKGROUND.md) を参照。
強いAIの指し方から初心者向けのコツをまとめたページは [docs/ai_tips.html](docs/ai_tips.html)（作り方はページ末尾）。

## 現状（2026-10-07）

- ルールエンジン（Python版・Numba高速版、全手で一致を検証）、ベースライン、決定化MCTS、
  自己対戦による評価関数の方策反復まで実装済み。
- 最強設定（線形評価関数v6＋MCTS 12000回/手＋評価前に10手のロールアウト）は、200局の検証で
  貪欲法に勝率87%（+27点）、以前の最強（ロールアウト無し）に勝率65%（+9点）。詳細は [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md)。

```bash
py -m venv .venv && .venv\Scripts\pip install pytest hypothesis ruff numpy numba pypdf
.venv\Scripts\python -m pytest -q
.venv\Scripts\python scripts/run_match.py "fmcts:sims=12000,depth=10,eval=models/eval_v6_lin.npy" greedy --seeds 20 --workers 8
```

## 人間と対戦する

ブラウザ上でAIと対戦できる（対局は `runs/human/games.jsonl` に記録される）。手順と評価方法は
[docs/HUMAN_EVAL.md](docs/HUMAN_EVAL.md)。

```bash
.venv\Scripts\python scripts/play_human.py
.venv\Scripts\python scripts/summarize_human.py
```
