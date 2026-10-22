# 盤面を見る価値ネットの実験（2026-10-21）

結果と結論は `docs/EXPERIMENTS.md` の「盤面を見る価値ネットと、次のタイルで平均した評価での選び直し」。
PyTorch が要る（`download.pytorch.org` に届かない環境では PyPI の `torch` を入れる）。作業フォルダは `runs/az/`。

```bash
mkdir -p runs/az/rec
git show origin/selfplay-state:loop/models/gen386.npy > runs/az/gen386.npy
python scripts/board_net/gen.py 600 10000 300 10 4      # 600回/手の自己対戦 3000局（10局×300塊、4並列、約1時間）
python scripts/board_net/enc.py 'runs/az/rec/r*.npz'     # 棋譜を盤面（26層×25×25）に符号化
python scripts/board_net/train.py --c 48 --b 4 --epochs 4 --out runs/az/vnet48.pt   # 約1時間
python scripts/board_net/match.py --vnet runs/az/vnet48.pt --sims 2000 --alpha 0.3 --topk 6 --seeds 100
python scripts/board_net/match.py --vnet lin ...         # 同じ選び直しを gen386 の式で（main の `rsel` と同じ計算）
```

- `gen.py`: 棋譜（山札・指し手）と根の探索統計。`enc.py`: 再生して盤面を作る。8通りの回転・反転（`transform`）。
- `train.py`: 価値ネット（終局得点差/30 を予測）。gen386 の式と、盤全体の情報84個の線形を同じ検証局面で比べる。
- `netagent.py`: 探索の上位候補を、次に相手が引くタイルで平均した価値ネットの値で選び直す。
