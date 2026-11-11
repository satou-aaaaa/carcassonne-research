"""人がAIと指した棋譜（対戦ページから送ってもらったもの）を受け取る・ためる・まとめる。

    py scripts/human_games.py add 棋譜.json ...          # ファイルで受け取った棋譜を検査して足す
    py scripts/human_games.py ingest-issue --event イベント.json --result 結果.json
                                                        # GitHub の Issue で届いた棋譜（human-games.yml から呼ぶ）
    py scripts/human_games.py report                    # docs/results/human_games.md を作り直す

棋譜は data/human_games.jsonl に1局1行でためる（形と検査は src/carcassonne/human_games.py）。
ためた棋譜は自己対戦ループの学習に混ざる（selfplay_loop.Config.human_games）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne import human_games as hg

GAMES = ROOT / "data" / "human_games.jsonl"
REPORT = ROOT / "docs" / "results" / "human_games.md"


def cmd_add(a) -> int:
    bad = 0
    for f in a.files:
        text = Path(f).read_text(encoding="utf-8")
        try:
            rec = hg.normalize(json.loads(text))
        except (hg.RecordError, json.JSONDecodeError) as e:
            print(f"{f}: 受け取れません: {e}")
            bad += 1
            continue
        print(f"{f}: {'足しました' if hg.add(a.games, rec) else '同じ対局がもうあります'}")
    return 1 if bad else 0


def cmd_ingest_issue(a) -> int:
    event = json.loads(Path(a.event).read_text(encoding="utf-8"))
    issue = event.get("issue") or {}
    status, message = hg.ingest_issue(issue.get("body") or "", a.games)
    Path(a.result).write_text(
        json.dumps({"status": status, "message": message}, ensure_ascii=False), encoding="utf-8"
    )
    print(status, message)
    return 0


def cmd_report(a) -> int:
    from carcassonne.fast import Fast
    from carcassonne.fast_eval import load_eval
    from carcassonne.webplay import champion_eval_path

    w, mode = load_eval(champion_eval_path())
    if mode != 1:
        raise SystemExit("弱点分析は線形の評価関数だけに対応しています")
    text = hg.report_md(Fast(), hg.load(a.games), w)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(text, encoding="utf-8")
    print(f"{a.out} を書きました")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--games", default=str(GAMES), help="棋譜をためるファイル")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=cmd_add)
    p = sub.add_parser("ingest-issue")
    p.add_argument("--event", required=True, help="GitHub のイベント（$GITHUB_EVENT_PATH）")
    p.add_argument("--result", required=True, help="結果（status・message）を書く JSON")
    p.set_defaults(func=cmd_ingest_issue)
    p = sub.add_parser("report")
    p.add_argument("--out", default=str(REPORT))
    p.set_defaults(func=cmd_report)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
