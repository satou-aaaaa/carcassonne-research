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

## 現状（2026-10-05）

- ルールエンジン（Python版・Numba高速版、全手で一致を検証）、ベースライン、決定化MCTS、
  自己対戦による評価関数の方策反復まで実装済み。
- 最強設定（線形評価関数v6＋MCTS 12000回/手）は貪欲法に勝率79%（+16点）、ロールアウト版MCTSと同等の強さを
  約1/2.5の時間で達成。詳細は [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md)。

## セットアップと実行

```bash
# Linux / macOS
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
python -m pytest -q                      # 約2.5分（初回はNumbaのコンパイル込み）
python -m pytest -q -m "not slow"        # 高速版

# Windows（PowerShell）
py -m venv .venv; .venv\Scripts\pip install -e ".[dev]"; .venv\Scripts\python -m pytest -q
```

```bash
python scripts/run_match.py "fmcts:sims=12000,eval=models/eval_v6_lin.npy" greedy --seeds 20 --workers 8
python scripts/first_player.py fmcts:sims=2000 --games 400 --workers 4   # 先手有利の検定
```

- 対戦ログ（JSONL）は `--log docs/results/<name>.jsonl` でリポジトリに残す（`runs/` はgit管理外の作業用）。
- 探索の既定は従来の固定山札版。`chance=1` でタイル引きを確率節点としてモデル化できる（同回数では優位を示せていない。`docs/EXPERIMENTS.md`）。
- 自動改善サイクル（`scripts/improve_cycle.py`）の昇格判定はSPRT（逐次確率比検定）。
