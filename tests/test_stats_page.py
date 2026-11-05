"""データページ（docs/stats.html）の集計と本文が合っていること。"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import build_stats_page as b
from summarize_game_stats import first_player, sources


def test_committed_stats_match_claims():
    st = json.loads(b.STATS.read_text(encoding="utf-8"))
    assert b.failed_claims(st) == []
    assert len(st["tiles"]) == len(b.TILE_NAME)  # 全種類のタイルに名前がある


def test_other_games_have_sources():
    for g in b.OTHER_GAMES:
        assert g["ai_src"].startswith("https://")
        assert (g["first"] is None) == (g["first_src"] is None)


def _game(scores, awards):
    return {"seed": 0, "play": 0, "scores": scores, "discarded": 0, "awards": awards, "moves": []}


def test_first_player_counts_draw_as_half():
    games = [_game([10, 5], []), _game([5, 10], []), _game([7, 7], []), _game([9, 1], [])]
    fp = first_player(games)
    assert (fp["wins"], fp["losses"], fp["draws"]) == (2, 1, 1)
    assert fp["score"] == 0.625


def test_sources_split_shared_awards_and_end_scoring():
    # 都市を途中で完成（共有なので両者に4点）、終了時に草原3点（先手）
    g = _game([7, 4], [[[0, 1], "C", 4, 0, 5], [[0], "F", 3, 1, 71]])
    s = sources([g])
    assert s["C"]["share"] == round(8 / 11, 4)
    assert s["end_share"] == round(3 / 11, 4)
    assert s["F"]["unfinished_rate"] == 1.0
