# 人との対局のまとめ（自動）

対戦ページから送ってもらった棋譜（data/human_games.jsonl）の集計。`python scripts/human_games.py report` で作り直す。

受け取った対局: 10局

| AIの強さ | 局数 | 人の勝ち | 引き分け | 人から見た平均得点差 | うちヒント等あり |
|---|---:|---:|---:|---:|---:|
| strong | 6 | 2 | 0 | -5.8 | 6 |
| standard | 4 | 3 | 1 | +3.8 | 4 |

## 対局の一覧（押すと一手ずつ再生）

- [10局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=10): 人（先手）97 − AI 71（strong、71手）
- [9局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=9): 人（先手）114 − AI 124（strong、71手）
- [8局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=8): 人（先手）98 − AI 98（standard、71手）
- [7局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=7): 人（先手）88 − AI 99（strong、71手）
- [6局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=6): 人（先手）100 − AI 97（standard、71手）
- [5局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=5): 人（先手）105 − AI 95（standard、71手）
- [4局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=4): 人（先手）69 − AI 67（standard、71手）
- [3局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=3): 人（先手）91 − AI 89（strong、71手）
- [2局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=2): 人（先手）81 − AI 82（strong、71手）
- [1局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=1): 人（先手）87 − AI 128（strong、70手）

## AIの読みが外れた人の手（AIの見積もりが大きく下がった順）

AI視点の評価（最新チャンピオンの線形評価、単位は得点差）が、人の手の直前と直後でどれだけ下がったか。大きいものは、AIがその手の価値を低く見ていた候補（弱点探しの出発点）。

対局の番号を押すと、対戦ページでその手の直前から一手ずつ再生できる。

| 対局 | 手数 | 置いた場所 (x, y) | 下がり幅 |
|---:|---:|---|---:|
| [5](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=5&ply=66) | 67 | (2, -6) | +12.2 |
| [10](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=10&ply=60) | 61 | (0, 4) | +11.9 |
| [9](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=9&ply=58) | 59 | (3, 3) | +10.8 |
| [10](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=10&ply=62) | 63 | (-2, 3) | +10.5 |
| [1](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=1&ply=44) | 45 | (3, -1) | +9.7 |
| [3](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=3&ply=48) | 49 | (7, -2) | +9.2 |
| [5](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=5&ply=62) | 63 | (4, -7) | +9.1 |
| [8](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=8&ply=28) | 29 | (-1, -2) | +8.3 |
| [9](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=9&ply=20) | 21 | (-2, -1) | +8.1 |
| [7](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=7&ply=60) | 61 | (3, -1) | +7.6 |
