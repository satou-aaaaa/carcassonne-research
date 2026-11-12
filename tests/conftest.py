"""テスト全体の共通設定。"""

import sys

import pytest


@pytest.fixture(autouse=True)
def _ignore_repo_human_games(monkeypatch):
    """テストはリポジトリの data/human_games.jsonl（人から届く本物の棋譜。増え続ける）を読まない。

    Config の既定がこのファイルを指すので、棋譜が1局届いただけで学習データの件数を
    数えるテストが落ち、棋譜の取り込み PR が止まった（Issue #176）。人の棋譜を混ぜる
    テストは human_games= に自分で作ったファイルを渡す。
    """
    mod = sys.modules.get("carcassonne.selfplay_loop")
    if mod is None:
        return
    orig = mod.Loop.load_human

    def load_human(self):
        if self.cfg.human_games == mod.Config.human_games:
            return None
        return orig(self)

    monkeypatch.setattr(mod.Loop, "load_human", load_human)
