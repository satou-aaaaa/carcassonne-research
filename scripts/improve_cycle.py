"""改善サイクルを1回実行する（定期実行用）。

1. 現行ベスト評価関数（models/best.json）の評価関数版MCTS自己対戦でデータを収集する。
2. 過去の蓄積データ（runs/data_*.npz のうち特徴量数が一致するもの）と合わせて線形評価関数を再学習する。
3. 候補をベストと同じ探索予算で対戦させ（先後入替・新しいシード）、勝率が閾値以上なら昇格する
   （AlphaZero型のゲーティング。閾値は既定0.55）。
4. 結果を docs/EXPERIMENTS.md に追記し、models/best.json を更新する。コミット/pushは呼び出し側で行う。

    py scripts/improve_cycle.py --games 440 --eval-seeds 30 --workers 11
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from datetime import date
from functools import partial
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne.arena import run_match
from carcassonne.fast_eval import NF, fit_ridge
from carcassonne.fast_mcts import FastMCTSAgent
from carcassonne.selfplay import generate

BEST_JSON = ROOT / "models" / "best.json"
EXPERIMENTS = ROOT / "docs" / "EXPERIMENTS.md"


def load_best() -> dict:
    return json.loads(BEST_JSON.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=440, help="データ収集の自己対戦局数")
    ap.add_argument("--gen-sims", type=int, default=4000)
    ap.add_argument("--eval-sims", type=int, default=12000, help="対戦評価の探索回数/手")
    ap.add_argument("--eval-seeds", type=int, default=30, help="シード数（先後入替で2倍）")
    ap.add_argument("--threshold", type=float, default=0.55, help="昇格に必要な勝率")
    ap.add_argument("--lam", type=float, default=10.0)
    ap.add_argument(
        "--max-files", type=int, default=8, help="学習に使うデータファイルの最大数（新しい順）"
    )
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true", help="記録・昇格をしない")
    args = ap.parse_args()

    state = load_best()
    best_path = str(ROOT / state["best"])
    cycle = len(state["history"])  # 通し番号（シードの重複を避ける）
    t0 = time.time()

    # 1. データ収集
    X, y = generate(
        {"n_sims": args.gen_sims, "eval_path": best_path},
        args.games,
        args.workers,
        seed=10_000 + cycle,
    )
    data_path = ROOT / "runs" / f"data_c{cycle}.npz"
    data_path.parent.mkdir(exist_ok=True)
    np.savez_compressed(data_path, X=X, y=y)

    # 2. 蓄積データで再学習
    xs, ys = [], []
    files = sorted(
        glob.glob(str(ROOT / "runs" / "data_*.npz")), key=lambda f: Path(f).stat().st_mtime
    )
    for f in files[-args.max_files :]:  # 新しい方策のデータを優先して直近のみ使う
        d = np.load(f)
        if d["X"].shape[1] == NF:
            xs.append(d["X"])
            ys.append(d["y"])
    Xa, ya = np.concatenate(xs), np.concatenate(ys)
    model = fit_ridge(Xa, ya, args.lam)
    r2 = 1 - ((ya - Xa @ model.w) ** 2).sum() / ((ya - ya.mean()) ** 2).sum()
    version = f"c{cycle}_lin"
    cand = ROOT / "models" / f"eval_{version}.npy"
    model.save(str(cand))

    # 3. ゲーティング対戦（候補A vs ベストB、同じ探索予算）
    seeds = range(50_000 + cycle * 1000, 50_000 + cycle * 1000 + args.eval_seeds)
    summary = run_match(
        partial(FastMCTSAgent, args.eval_sims, eval_path=str(cand)),
        partial(FastMCTSAgent, args.eval_sims, eval_path=best_path),
        seeds,
        workers=args.workers,
    )
    promoted = summary.win_rate >= args.threshold
    elapsed = (time.time() - t0) / 60

    # 4. 記録
    today = date.today().isoformat()  # noqa: DTZ011
    line = (
        f"\n### 自動改善サイクル #{cycle}（{today}）\n"
        f"- データ: 新規{len(y)}局面（累計{len(ya)}）、線形R²={r2:.3f}、所要{elapsed:.0f}分\n"
        f"- 候補 `{cand.name}` vs 現ベスト `{Path(best_path).name}`"
        f"（各{args.eval_sims}回/手、{summary}）\n"
        f"- 判定: {'**昇格**' if promoted else '据え置き'}（閾値 勝率{args.threshold:.2f}）\n"
    )
    print(line)
    if args.dry_run:
        return
    with EXPERIMENTS.open("a", encoding="utf-8") as f:
        f.write(line)
    state["history"].append(
        {
            "version": version,
            "win_rate_vs_best": round(summary.win_rate, 3),
            "mean_diff": round(summary.mean_diff_a, 2),
            "promoted": promoted,
            "date": today,
        }
    )
    if promoted:
        state["best"] = f"models/eval_{version}.npy"
    BEST_JSON.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
