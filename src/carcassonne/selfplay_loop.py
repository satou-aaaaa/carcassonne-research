"""自己対戦で強くなり続けるループ（AlphaZero型の「自己対戦→学習→旧版と対戦→強ければ採用」）。

1世代（試行）の流れ:
  1. 自己対戦: 現チャンピオンの評価関数を使う MCTS 同士で `games` 局指し、局面の特徴量と結果を保存する。
  2. 学習: 直近 `window` 試行分のデータで、TD(λ) の目標（`td.py`）を使って候補の評価関数を作る。
     線形（`lin`）はチャンピオンの重みに向かって正則化する（学び直しで弱くなるのを防ぐ）。
     `mlp` は1隠れ層のMLP（`fast_eval.fit_mlp`）。
  3. 判定: 候補とチャンピオンを同じ探索予算で `gate_seeds` 組（先後入替で2倍の局数）対戦させ、
     勝率が `threshold` 以上なら候補を新しいチャンピオンにする。
     採用したときは、初代チャンピオンとも `anchor_seeds` 組対戦させ、通算でどれだけ伸びたかを記録する。

作業は数分で終わる「単位」（自己対戦の塊・学習・対戦の塊）に分け、単位ごとに状態を `state.json` に
保存する。途中で止まっても、次に `run` したときに続きから再開する。状態・データ・各世代の重みは
すべて `root` の下に置く（リポジトリの外の共有フォルダを想定）。
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path

import numpy as np

from .arena import run_match
from .fast_eval import NF, fit_mlp, load_eval
from .fast_mcts import FastMCTSAgent
from .ridge_stats import solve_ridge, stats_of
from .selfplay import generate
from .td import td_lambda_targets


@dataclass
class Config:
    games: int = 200  # 1試行の自己対戦局数
    chunk: int = 50  # 自己対戦の1単位の局数
    sims: int = 2000  # 自己対戦・判定の探索回数/手
    depth: int = 10  # 評価前に進めるランダム手数（最強設定と同じ）
    window: int = 4  # 学習に使う直近の試行数
    model: str = "lin"  # lin / mlp
    hidden: int = 32  # mlp の隠れ層
    lam: float = 0.7  # TD(λ) の λ
    ridge: float = 1000.0  # lin: チャンピオンの重みへの正則化の強さ
    gate_seeds: int = 50  # 判定の組数（局数はその2倍）
    gate_chunk: int = 10  # 判定の1単位の組数
    threshold: float = 0.55  # 採用に必要な勝率
    anchor_seeds: int = 20  # 採用時に初代と対戦する組数（0で省略）
    workers: int = 4


def _write_json(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _save_npz(path: Path, **arrays) -> None:
    tmp = path.with_name(path.name + ".tmp.npz")
    np.savez_compressed(tmp, **arrays)
    os.replace(tmp, path)


def eval_np(params: np.ndarray, mode: int, X: np.ndarray) -> np.ndarray:
    """`fast_eval.eval_value` と同じ値を、局面の行列 X[N,NF] に対してまとめて計算する。"""
    if mode == 1:
        return X @ params[:NF]
    H = mode
    off = 2 * NF
    mean, std = params[:NF], params[NF:off]
    W1 = params[off : off + NF * H].reshape(NF, H)
    b1 = params[off + NF * H : off + NF * H + H]
    W2 = params[off + NF * H + H : off + NF * H + 2 * H]
    b2 = params[off + NF * H + 2 * H]
    return np.maximum((X - mean) / std @ W1 + b1, 0.0) @ W2 + b2


class Loop:
    def __init__(self, root: str | Path, config: Config | None = None, initial: str | None = None):
        """root に状態があれば読み込む。無ければ config と初代チャンピオン initial で始める。"""
        self.root = Path(root)
        self.state_path = self.root / "state.json"
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.cfg = Config(**self.state["config"])
            return
        if config is None or initial is None:
            raise ValueError(f"{self.state_path} が無いので、config と初代の重みが必要です")
        for sub in ("data", "models", "gate"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        shutil.copy(initial, self.root / "models" / "gen000.npy")
        self.cfg = config
        self.state = {
            "config": asdict(config),
            "initial_source": str(initial),
            "attempt": 1,  # 今作っている候補の通し番号
            "champion": "models/gen000.npy",
            "phase": "selfplay",
            "history": [],
        }
        self.save()

    # ---- 状態 ----
    def save(self) -> None:
        _write_json(self.state_path, self.state)

    def path(self, rel: str) -> str:
        return str(self.root / rel)

    def agent(self, eval_rel: str):
        c = self.cfg
        return partial(FastMCTSAgent, c.sims, rollout_depth=c.depth, eval_path=self.path(eval_rel))

    @property
    def attempt(self) -> int:
        return self.state["attempt"]

    def cand_rel(self) -> str:
        return f"models/gen{self.attempt:03d}.npy"

    # ---- 単位作業 ----
    def step(self) -> str:
        """作業を1単位進め、何をしたかを返す。"""
        return getattr(self, f"_{self.state['phase']}")()

    def _selfplay(self) -> str:
        c, a = self.cfg, self.attempt
        n_chunks = -(-c.games // c.chunk)
        for k in range(n_chunks):
            out = self.root / "data" / f"a{a:03d}_{k:02d}.npz"
            if out.exists():
                continue
            n = min(c.chunk, c.games - k * c.chunk)
            kw = {"n_sims": c.sims, "eval_path": self.path(self.state["champion"])}
            kw["rollout_depth"] = c.depth
            X, y, p, g = generate(kw, n, c.workers, seed=100_000 + a * 100 + k, with_meta=True)
            _save_npz(out, X=X, y=y, p=p, g=g)
            if k == n_chunks - 1:
                self.state["phase"] = "train"
                self.save()
            return f"試行{a}: 自己対戦 {k + 1}/{n_chunks}（{n}局, {len(y)}局面）"
        self.state["phase"] = "train"
        self.save()
        return f"試行{a}: 自己対戦は済み"

    def load_window(self):
        a, w = self.attempt, self.cfg.window
        Xs, ys, ps, gs, off = [], [], [], [], 0
        for f in sorted((self.root / "data").glob("a*.npz")):
            if not a - w < int(f.name[1:4]) <= a:
                continue
            with np.load(f) as d:
                Xs.append(d["X"])
                ys.append(d["y"])
                ps.append(d["p"])
                gs.append(d["g"] + off)
            off = int(gs[-1].max()) + 1
        return np.concatenate(Xs), np.concatenate(ys), np.concatenate(ps), np.concatenate(gs)

    def _train(self) -> str:
        c, a = self.cfg, self.attempt
        X, y, p, g = self.load_window()
        champ, mode = load_eval(self.path(self.state["champion"]))
        target = td_lambda_targets(eval_np(champ, mode, X), y, p, g, c.lam)
        if c.model == "lin":
            prior = champ if mode == 1 else None
            w = solve_ridge(stats_of(X, target), c.ridge, prior)
        else:
            w, _ = fit_mlp(X, target, hidden=c.hidden, seed=a)
        np.save(self.path(self.cand_rel()), w)
        # 物差し: 後半20%の対局で、終局得点差をどれだけ当てられるか（チャンピオンと比べる）
        va = g >= np.quantile(g, 0.8)
        cw, cm = load_eval(self.path(self.cand_rel()))

        def r2(pred):
            return float(1 - ((y[va] - pred) ** 2).sum() / ((y[va] - y[va].mean()) ** 2).sum())

        self.state["train"] = {
            "positions": len(y),
            "r2_candidate": round(r2(eval_np(cw, cm, X[va])), 4),
            "r2_champion": round(r2(eval_np(champ, mode, X[va])), 4),
        }
        self.state["phase"] = "gate"
        self.save()
        t = self.state["train"]
        return (
            f"試行{a}: 学習 {t['positions']}局面 検証R² 候補{t['r2_candidate']:.3f}"
            f" / チャンピオン{t['r2_champion']:.3f}"
        )

    def _match_chunks(self, tag: str, a_rel: str, b_rel: str, n_seeds: int, base: int):
        """n_seeds 組のうち未対戦の塊を1つ（gate_chunk 組）指す。

        全部済んだら A 視点の (局数, 勝ち, 得点差の合計) を、まだ残っていれば None を返す。
        """
        c = self.cfg
        n_chunks = -(-n_seeds // c.gate_chunk)
        outs = [self.root / "gate" / f"{tag}_{k:02d}.json" for k in range(n_chunks)]
        todo = [k for k, o in enumerate(outs) if not o.exists()]
        if todo:
            k = todo[0]
            s0 = base + k * c.gate_chunk
            seeds = range(s0, min(s0 + c.gate_chunk, base + n_seeds))
            m = run_match(self.agent(a_rel), self.agent(b_rel), seeds, workers=c.workers)
            r = {"games": m.games, "wins": m.wins_a, "diff_sum": m.mean_diff_a * m.games}
            _write_json(outs[k], r)
            if len(todo) > 1:
                return None, f"{n_chunks - len(todo) + 1}/{n_chunks}"
        done = [json.loads(o.read_text(encoding="utf-8")) for o in outs]
        n = sum(r["games"] for r in done)
        return (n, sum(r["wins"] for r in done), sum(r["diff_sum"] for r in done)), ""

    def _gate(self) -> str:
        c, a = self.cfg, self.attempt
        tag = f"a{a:03d}_gate"
        res, msg = self._match_chunks(
            tag, self.cand_rel(), self.state["champion"], c.gate_seeds, 200_000 + a * 1000
        )
        if res is None:
            return f"試行{a}: 判定 {msg}（候補 vs チャンピオン）"
        n, wins, dsum = res
        rate = wins / n
        promoted = rate >= c.threshold
        entry = {
            "attempt": a,
            "candidate": self.cand_rel(),
            "champion_before": self.state["champion"],
            "games": n,
            "win_rate": round(rate, 3),
            "mean_diff": round(dsum / n, 2),
            "promoted": promoted,
            **self.state.pop("train", {}),
            "date": time.strftime("%Y-%m-%d"),
        }
        self.state["history"].append(entry)
        if promoted:
            self.state["champion"] = self.cand_rel()
        self.state["phase"] = "anchor" if promoted and c.anchor_seeds > 0 else "selfplay"
        if self.state["phase"] == "selfplay":
            self.state["attempt"] = a + 1
        self.save()
        self.write_progress()
        word = "採用" if promoted else "不採用"
        return f"試行{a}: 判定 {n}局 勝率{rate:.3f} 得点差{dsum / n:+.2f} → {word}"

    def _anchor(self) -> str:
        c, a = self.cfg, self.attempt
        tag = f"a{a:03d}_anchor"
        res, msg = self._match_chunks(
            tag, self.state["champion"], "models/gen000.npy", c.anchor_seeds, 300_000 + a * 1000
        )
        if res is None:
            return f"試行{a}: 初代と対戦 {msg}"
        n, wins, dsum = res
        self.state["history"][-1]["vs_initial"] = {
            "games": n,
            "win_rate": round(wins / n, 3),
            "mean_diff": round(dsum / n, 2),
        }
        self.state["phase"] = "selfplay"
        self.state["attempt"] = a + 1
        self.save()
        self.write_progress()
        return f"試行{a}: 初代と対戦 {n}局 勝率{wins / n:.3f} 得点差{dsum / n:+.2f}"

    # ---- 記録 ----
    def write_progress(self) -> None:
        c = self.cfg
        lines = [
            "# 自己対戦ループの成績",
            "",
            f"- チャンピオン: `{self.state['champion']}`（初代は `{self.state['initial_source']}`）",
            (
                f"- 設定: 自己対戦{c.games}局/試行、探索{c.sims}回/手（depth={c.depth}）、"
                f"モデル{c.model}、判定{2 * c.gate_seeds}局で勝率{c.threshold}以上なら採用"
            ),
            "",
            "| 試行 | 日付 | 候補 vs チャンピオン | 得点差 | 判定 | 学習局面 | 検証R²(候補/現) | 初代との対戦 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for h in self.state["history"]:
            vi = h.get("vs_initial")
            vs = f"{vi['win_rate']:.3f}（{vi['mean_diff']:+.1f}点, {vi['games']}局）" if vi else ""
            lines.append(
                f"| {h['attempt']} | {h['date']} | {h['win_rate']:.3f}（{h['games']}局） "
                f"| {h['mean_diff']:+.2f} | {'**採用**' if h['promoted'] else '不採用'} "
                f"| {h.get('positions', '')} | {h.get('r2_candidate', '')}/{h.get('r2_champion', '')} "
                f"| {vs} |"
            )
        (self.root / "progress.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run(self, minutes: float, log=print, stale_minutes: float = 120) -> bool:
        """minutes 分を超えるまで単位作業を繰り返す（単位の途中では止めない）。

        同じフォルダで2つ同時に動かないよう `lock` ファイルを使う。別の実行中なら何もせず False を返す。
        `lock` は単位ごとに更新し、stale_minutes 分更新が無ければ落ちた実行の残りとみなして奪う。
        """
        lock = self.root / "lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.time() - lock.stat().st_mtime < stale_minutes * 60:
                log(f"{lock} があるので、別の実行が進行中とみなして終了します")
                return False
            lock.unlink(missing_ok=True)
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"{os.getpid()} {time.strftime('%Y-%m-%d %H:%M:%S')}\n".encode())
        os.close(fd)
        try:
            t0 = time.time()
            while time.time() - t0 < minutes * 60:
                t = time.time()
                msg = self.step()
                os.utime(lock)
                log(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}（{time.time() - t:.0f}秒）")
        finally:
            lock.unlink(missing_ok=True)
        return True
