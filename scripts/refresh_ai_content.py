"""学習ページ（コツ集・次の一手クイズ）を、いまの最新AI（チャンピオン）で作り直す。

    py scripts/refresh_ai_content.py --check      # 古くなっていれば「stale」、最新なら「fresh」と出す
    py scripts/refresh_ai_content.py              # 古くなっていれば作り直す（--force で必ず）

対戦ページのAIは models/eval_champion.npy（scripts/update_champion.py が差し替える）。
コツ集（docs/ai_tips.html）とクイズ（docs/quiz.html）は、そのAIの対局や解析から作るので、
チャンピオンが変わったら次をやり直す（.github/workflows/ai-content.yml が自動で行う）。

1. 最新AI同士で48局指して記録する（scripts/record_habits.py）。
2. 集計して docs/results/habits_summary.json の強いAIの分を差し替える（目先の点だけのAIの分は
   チャンピオンに関係しないので残す）。図版の局面も選び直す（scripts/pick_examples.py）。
3. クイズの全問を最新AIで解析し直す（scripts/recheck_puzzles.py）。答えが変わった問題は外れる。
4. 公開ページを作り直す（scripts/build_pages.py）。

本文の言い切り（scripts/build_tips_page.py の check_claims）が新しい集計と合わないときは、コツ集だけ
前の版（前のAIの集計と図版）のまま残し、クイズと対戦ページは進める。合わなかった言い切りと新しい集計は
data/tips_blocked.json に残し、ai-content.yml が Issue で知らせる（同じAIでは毎日作り直さない）。
以前はここでジョブを止めていたので、48局のぶれで言い切りが1つ外れるたびに、文を直すまで毎日赤になった
（gen419・gen576・gen836・gen926、2026-10-24〜11-03 に 11 回）。止めずに Issue で直しを頼む形にする。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts"))

import build_tips_page

from carcassonne.webplay import champion_info

RESULTS = ROOT / "docs" / "results"
SUMMARY = RESULTS / "habits_summary.json"
EXAMPLES = RESULTS / "habits_examples.json"
PUZZLES = ROOT / "data" / "puzzles.json"
BLOCKED = ROOT / "data" / "tips_blocked.json"


def content_ai() -> dict:
    """いまのコツ集・クイズを作ったAIの名前（{"tips": 名前, "quiz": [名前...]}）。"""
    summ = json.loads(SUMMARY.read_text(encoding="utf-8"))
    puzzles = json.loads(PUZZLES.read_text(encoding="utf-8"))
    return {
        "tips": (summ.get("ai") or {}).get("name"),
        "quiz": sorted({(p.get("checked_by") or {}).get("name") or "" for p in puzzles}),
    }


def blocked() -> dict | None:
    """コツ集を前の版のまま残している理由（data/tips_blocked.json）。無ければ None。"""
    if not BLOCKED.exists():
        return None
    return json.loads(BLOCKED.read_text(encoding="utf-8"))


def is_stale() -> bool:
    name = champion_info()["name"]
    have = content_ai()
    held = (blocked() or {}).get("ai", {}).get(
        "name"
    ) == name  # このAIでは言い切りが合わず、前の版で止めた
    return (have["tips"] != name and not held) or have["quiz"] != [name]


def run(*args: str) -> None:
    print("$", " ".join(args), flush=True)
    subprocess.run([sys.executable, *args], check=True, cwd=ROOT)


def refresh(games: int, workers: int) -> None:
    ai = champion_info()
    runs = ROOT / "runs"
    runs.mkdir(exist_ok=True)
    rec = runs / "habits_strong.jsonl"
    rec.unlink(missing_ok=True)  # record_habits.py は追記するので、前の記録を消してから
    run("scripts/record_habits.py", "strong", "--seeds", str(games), "--workers", str(workers),
        "--out", str(rec))  # fmt: skip
    new = runs / "habits_strong_summary.json"
    run("scripts/summarize_habits.py", str(rec), "--json", str(new))
    summ = json.loads(SUMMARY.read_text(encoding="utf-8"))
    summ["habits_strong"] = json.loads(new.read_text(encoding="utf-8"))["habits_strong"]
    summ["ai"] = ai
    bad = build_tips_page.summary_failed_claims(summ)
    if bad:
        # コツ集は前の版のまま（SUMMARY・EXAMPLES を書き換えない）。新しい集計は直すときのために残す
        hold(summ, bad)
    else:
        BLOCKED.unlink(missing_ok=True)
        SUMMARY.write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
        run("scripts/pick_examples.py", str(rec), "--out", str(EXAMPLES))
    run("scripts/recheck_puzzles.py", "--workers", str(workers))
    run("scripts/build_pages.py")


def hold(summ: dict, bad: list[str]) -> None:
    """言い切りが合わないので、コツ集を前の版のまま残す。理由と新しい集計を BLOCKED に書く。"""
    BLOCKED.write_text(
        json.dumps({"ai": summ["ai"], "failed_claims": bad, "habits_strong": summ["habits_strong"],
                    "habits_greedy": summ["habits_greedy"]}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )  # fmt: skip
    print(
        f"::warning title=コツ集は前の版のままです::{summ['ai']['name']} の集計が本文の言い切りと合いません: "
        + " / ".join(bad)
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--games", type=int, default=48)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    stale = is_stale()
    if args.check:
        print("stale" if stale else "fresh")
        return
    if not (stale or args.force):
        print("fresh（作り直し不要）")
        return
    refresh(args.games, args.workers)
    print(f"作り直した: {champion_info()['name']}")


if __name__ == "__main__":
    main()
