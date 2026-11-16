# 人との対局のまとめ（自動）

対戦ページから送ってもらった棋譜（data/human_games.jsonl）の集計。`python scripts/human_games.py report` で作り直す。

受け取った対局: 19局

| AIの強さ | 局数 | 人の勝ち | 引き分け | 人から見た平均得点差 | うちヒント等あり |
|---|---:|---:|---:|---:|---:|
| strong | 11 | 3 | 1 | -6.6 | 11 |
| standard | 8 | 5 | 1 | +4.9 | 8 |

## 対局の一覧（押すと一手ずつ再生）

- [19局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=19): 人（後手）95 − AI 119（strong、70手）
- [18局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=18): 人（後手）84 − AI 110（strong、71手）
- [17局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=17): 人（先手）110 − AI 110（strong、71手）
- [16局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=16): 人（先手）122 − AI 101（strong、71手）
- [15局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=15): 人（先手）86 − AI 91（standard、71手）
- [14局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=14): 人（先手）120 − AI 89（standard、71手）
- [13局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=13): 人（先手）108 − AI 117（strong、71手）
- [12局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=12): 人（先手）126 − AI 101（standard、71手）
- [11局目](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=11): 人（先手）78 − AI 105（standard、71手）
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
| [16](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=16&ply=68) | 69 | (2, -3) | +21.4 |
| [12](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=12&ply=52) | 53 | (4, 2) | +20.8 |
| [14](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=14&ply=70) | 71 | (-3, -7) | +15.0 |
| [17](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=17&ply=64) | 65 | (6, 4) | +13.9 |
| [14](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=14&ply=28) | 29 | (0, 5) | +13.3 |
| [17](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=17&ply=60) | 61 | (6, -1) | +13.1 |
| [5](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=5&ply=66) | 67 | (2, -6) | +13.0 |
| [10](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=10&ply=60) | 61 | (0, 4) | +12.0 |
| [18](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=18&ply=55) | 56 | (3, 3) | +12.0 |
| [16](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=16&ply=58) | 59 | (1, 0) | +11.9 |
