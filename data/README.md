# data/

## tiles.json

基本セット72枚を、回転同値・絵柄違い（花の有無）を統合した24種にまとめたタイル表。
`merged_from` に統合元の名前、`count` に枚数、`start_tile` に開始タイルの種別を持つ。

- 辺の順序は N,E,S,W = 0,1,2,3（時計回り）。半辺は `side*2 + h`（時計回り順）。
- `cities` / `roads`: その断片が接する辺。道は分岐点で終端するため交差点では別々の道になる。
- `fields`: 草原断片が接する半辺と、隣接する都市断片の index。
- `monastery`: 修道院の有無。

### 出自と検証
- 元データは wingedsheep/carcassonne（MIT）の `tile_sets/base_deck.py`。コードは取り込まず、
  タイル定義だけを一回限りのスクリプトで変換した（`merged_from` が元名）。
- 元データには都市辺上の半辺を草原に含める誤りが1タイル（`city_top_straight_road`）にあったため除外した。
- 検証: 合計72枚・24種・盾付き10枚・修道院6枚・各タイルの半辺が草原にちょうど1回属すること
  （`tests/test_tiles.py`）。Wikipedia「Carcassonne (board game)」の枚数表とも全種で一致（合計72）。**印刷版ルールブック／現物との照合は未了。**

## human_games.jsonl（人がAIと指した対局）

対戦ページから送ってもらった棋譜（1局1行、形は `src/carcassonne/human_games.py`）。
**ライセンスは CC BY 4.0**（https://creativecommons.org/licenses/by/4.0/ 、扱いは docs/terms.html）。名前などの個人情報は入っていない。

- 足すだけで、消したり書き換えたりしない。棋譜が減る変更は CI（test.yml の data ジョブ、`scripts/check_data_append_only.py`）が止める。
- 週に一度、控えを GitHub の Release「data-backup」に足す（`.github/workflows/data-backup.yml`）。

## endgame_puzzles.jsonl（終盤で勝率が大きく動く局面）

`scripts/endgame_puzzles.py` が自己対戦の棋譜から集めた、山札の残り1〜3枚で「最善手と次善手の勝率の差が0.15以上」の局面（1局面1行）。
`deck`（山札）と `history`（着手 [x, y, 種別, 向き, 断片]、data/puzzles.json と同じ形）で盤面を再現できる。
`best_move`・`greedy`（目先の点）・`diff`（点差最大）・`champ`（最強AIの探索）の手と、それぞれの厳密な勝率を持つ。
終盤クイズの材料（BACKLOG R-007）。作り直しは `--refresh`。
