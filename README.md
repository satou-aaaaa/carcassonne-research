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

## 初心者向けの公開ページ（docs/）

`docs/` の HTML はそのままブラウザで開け、GitHub Pages で公開することもできる。

| ページ | 内容 | 作り方 |
|---|---|---|
| [docs/index.html](docs/index.html) | トップ（各ページへの入口） | 手書き |
| [docs/rules.html](docs/rules.html) | ルール入門（図と点数はエンジンで検算） | `scripts/build_rules_page.py` |
| [docs/strategy.html](docs/strategy.html) | 戦略ガイド（考え方、タイルの内訳、穴の埋まりやすさ、序盤〜終盤、失敗例、用語集） | `scripts/build_strategy_page.py` |
| [docs/ai_tips.html](docs/ai_tips.html) | 強いAIの対局から学ぶコツ | `scripts/build_tips_page.py`（集計は `docs/results/`） |
| [docs/quiz.html](docs/quiz.html) | 次の一手クイズ（入門編・実戦編） | `scripts/build_puzzles.py` |
| [docs/play.html](docs/play.html) | AIと対戦（AIはブラウザの中で計算。サーバー不要） | `scripts/build_play_page.py` |

共通のナビゲーションは `scripts/site_nav.py`。データやテンプレート（`web/*_template.html`）を直したら
`scripts/build_pages.py` で作り直して `docs/` もコミットする（CI が作り直して差分がないか確かめる）。

GitHub Pages で公開するには、リポジトリの Settings → Pages で「Deploy from a branch」、
ブランチ `main`・フォルダ `/docs` を選ぶ。URL は `https://satou-aaaaa.github.io/carcassonne-research/`。

## 現状（2026-10-07）

- ルールエンジン（Python版・Numba高速版、全手で一致を検証）、ベースライン、決定化MCTS、
  自己対戦による評価関数の方策反復まで実装済み。
- 最強設定（線形評価関数＋MCTS 12000回/手＋評価前に10手のロールアウト）は、v6 の200局の検証で
  貪欲法に勝率87%（+27点）、以前の最強（ロールアウト無し）に勝率65%（+9点）。詳細は [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md)。

## 環境構築

以下のコマンド例は Windows（`py`・`.venv\Scripts\python`）で書いている。Linux / macOS では
`.venv\Scripts\python` を `.venv/bin/python` に読み替える。

```bash
# Windows
py -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m pytest -q
.venv\Scripts\python scripts/run_match.py "fmcts:sims=12000,depth=10,eval=models/eval_v9_block.npy" greedy --seeds 20 --workers 8

# Linux / macOS
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_match.py "fmcts:sims=12000,depth=10,eval=models/eval_v9_block.npy" greedy --seeds 20 --workers 8
```

PRを出す前やマージの前の確認は1コマンドでできる（CI も同じものを実行する）。

```bash
python scripts/check.py --quick   # lint・整形・公開ページ・時間のかかるテスト以外（約20秒）
python scripts/check.py           # 全テスト込み（約2分。CI はこちら）
python scripts/check.py --fix     # ruff の自動修正と整形をかけてから確認
python scripts/build_pages.py     # 公開ページ（docs/）をまとめて作り直す
```

PR の進め方（push 前の確認、ページの作り直し、マージの仕方）は `.claude/skills/steward/SKILL.md` にまとめている。

## 人間と対戦する

公開ページの [AIと対戦](https://satou-aaaaa.github.io/carcassonne-research/play.html) なら、インストールなしでブラウザだけで遊べる。
AI（評価関数v9＋MCTS 12000回＋10手のロールアウト）を JavaScript に移したもの（`web/carcassonne_engine.js`）が
ブラウザの中で考える。ルールと特徴量は Python 版と毎手一致することを `tests/test_play_js.py` で確かめている（node が必要）。
ブラウザ版の対局は記録されない。記録を取る人間評価は、次のローカル版で行う。

ブラウザ上でAIと対戦できる（対局は `runs/human/games.jsonl` に記録される）。手順と評価方法は
[docs/HUMAN_EVAL.md](docs/HUMAN_EVAL.md)。新しい対局の画面で「初心者モード」を選ぶと、自分の手のたびに
AIの評価（最善手より何点損したか）と、AIならどこに置いたかが表示される。

```bash
.venv\Scripts\python scripts/play_human.py
.venv\Scripts\python scripts/summarize_human.py
```

## 自己対戦で強くなり続けるループ

AlphaZero と同じ「自己対戦 → 学習 → 旧版と対戦 → 強ければ採用」を、CPUで回る規模で繰り返す
（`src/carcassonne/selfplay_loop.py`）。1試行は、チャンピオン同士の自己対戦200局（2000回/手・depth=10）、
直近4試行分のデータでの学習（TD(λ) の目標、線形はチャンピオンの重みへ正則化）、候補とチャンピオンの200局の対戦
（勝率0.55以上で採用）。採用したら初代（`models/best.json` の最強の評価関数）とも40局対戦して、通算の伸びを記録する。
4コアで1試行あたり約30分。判定が100局だと、初代に勝てない候補が運で採用されることがあった（2026-10-08、v6 から始めた8試行）。

作業は数分単位に分かれていて、止まっても次の `run` で続きから再開する。状態・データ・世代ごとの重みは `--root` に置き、
成績表は `--root/progress.md` に書く。

```bash
python scripts/selfplay_loop.py run --root /mnt/project-files/carcassonne-runs/loop --minutes 50
python scripts/selfplay_loop.py status --root /mnt/project-files/carcassonne-runs/loop
```

## 練習問題「次の一手」

AIの自己対戦から「この局面ならどこに置く？」形式の初心者向け問題を作り、AIの評価と解説つきの
1ファイルのページ `docs/quiz.html` にまとめている（ブラウザで直接開ける）。`"level": "入門"` の問題は先頭に入門編として出る。

```bash
.venv\Scripts\python scripts/make_puzzles.py --seeds 0-23 --workers 4   # 候補局面を runs/puzzles/ に集める
.venv\Scripts\python scripts/build_puzzles.py                            # data/puzzles.json から docs/quiz.html を作る
```

採用する局面と解説は `data/puzzles.json` に手で書く。AIの評価は、根の候補手ごとの平均報酬を予想最終点差に
換算したもの（`src/carcassonne/puzzles.py`）。
