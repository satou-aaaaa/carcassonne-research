# 人との対局のまとめ（自動）

対戦ページから送ってもらった棋譜（data/human_games.jsonl）の集計。`python scripts/human_games.py report` で作り直す。

受け取った対局: 5局

| AIの強さ | 局数 | 人の勝ち | 引き分け | 人から見た平均得点差 | うちヒント等あり |
|---|---:|---:|---:|---:|---:|
| strong | 3 | 1 | 0 | -13.3 | 3 |
| standard | 2 | 2 | 0 | +6.0 | 2 |

## 対局の一覧（押すと一手ずつ再生）

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
| [1](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=1&ply=44) | 45 | (3, -1) | +9.7 |
| [3](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=3&ply=48) | 49 | (7, -2) | +9.2 |
| [5](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=5&ply=62) | 63 | (4, -7) | +9.1 |
| [2](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=2&ply=32) | 33 | (5, 1) | +7.3 |
| [5](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=5&ply=26) | 27 | (1, -2) | +7.3 |
| [4](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=4&ply=22) | 23 | (3, -2) | +7.1 |
| [1](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=1&ply=38) | 39 | (5, -4) | +6.4 |
| [2](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=2&ply=64) | 65 | (3, 5) | +6.3 |
| [1](https://satou-aaaaa.github.io/carcassonne-research/play.html#replay=1&ply=22) | 23 | (2, 1) | +6.2 |
