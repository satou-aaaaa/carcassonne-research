import random

from carcassonne import State
from carcassonne.agents import GreedyAgent, RandomAgent
from carcassonne.arena import run_match, summarize, wilson
from carcassonne.mcts import MCTSAgent, determinize


def test_agents_return_legal_moves():
    st = State.new_game(11)
    rng = random.Random(0)
    for agent in (RandomAgent(), GreedyAgent(), MCTSAgent(n_sims=8, n_det=2)):
        assert agent.act(st, rng) in st.legal_moves()


def test_agents_do_not_mutate_state():
    st = State.new_game(12)
    before = (dict(st.board), list(st.scores), st.draw_pos, list(st.supply))
    rng = random.Random(1)
    GreedyAgent().act(st, rng)
    MCTSAgent(n_sims=8, n_det=2).act(st, rng)
    assert (dict(st.board), list(st.scores), st.draw_pos, list(st.supply)) == before


def test_determinize_keeps_public_information():
    st = State.new_game(13)
    rng = random.Random(2)
    for _ in range(5):
        st.apply(rng.choice(st.legal_moves()))
    d = determinize(st, rng)
    assert d.board == st.board and d.current == st.current
    assert sorted(d.deck[d.draw_pos :]) == sorted(st.deck[st.draw_pos :])
    assert d.deck[: d.draw_pos] == st.deck[: st.draw_pos]
    assert d.remaining_counts() == st.remaining_counts()


def test_projected_scores_equal_final_scores_at_end():
    st = State.new_game(14)
    rng = random.Random(3)
    while not st.over:
        proj = st.projected_scores()
        assert all(p >= s for p, s in zip(proj, st.scores))
        st.apply(rng.choice(st.legal_moves()))
    assert st.projected_scores() == st.scores


def test_projected_scores_equal_forced_finish():
    """予測得点は、その場で終局処理した複製の確定得点と常に一致する。"""
    rng = random.Random(4)
    for seed in range(10):
        st = State.new_game(seed)
        while not st.over:
            forced = st.copy()
            forced._finish()
            assert st.projected_scores() == forced.scores
            st.apply(rng.choice(st.legal_moves()))


def test_greedy_beats_random():
    summary = run_match(GreedyAgent, RandomAgent, range(8))
    assert summary.win_rate > 0.9 and summary.mean_diff_a > 20


def test_match_is_reproducible_and_logs(tmp_path):
    log = tmp_path / "m.jsonl"
    a = run_match(RandomAgent, RandomAgent, range(4), log_path=log)
    b = run_match(RandomAgent, RandomAgent, range(4))
    assert a == b
    assert len(log.read_text(encoding="utf-8").splitlines()) == 8


def test_parallel_match_equals_serial():
    serial = run_match(RandomAgent, GreedyAgent, range(4))
    parallel = run_match(RandomAgent, GreedyAgent, range(4), workers=2)
    assert serial == parallel


def test_wilson_interval_bounds():
    lo, hi = wilson(5, 10)
    assert 0 < lo < 0.5 < hi < 1
    assert wilson(0, 0) == (0.0, 1.0)
    lo, hi = wilson(10, 10)
    assert hi == 1.0 or abs(hi - 1.0) < 1e-12


def test_summarize_perspective():
    from carcassonne.arena import GameResult

    win_first = GameResult(0, "a", "b", [10, 0], 1, 0)
    win_second = GameResult(0, "b", "a", [0, 10], 1, 0)  # Aは後手で勝ち
    s = summarize([win_first], [win_second])
    assert s.win_rate == 1.0 and s.mean_diff_a == 10


def test_sprt_decisions():
    from carcassonne.arena import sprt_decision

    assert sprt_decision(0, 0) == "continue"
    assert sprt_decision(40, 60) == "accept"
    assert sprt_decision(20, 60) == "reject"
    assert sprt_decision(31, 60) == "continue"


def test_merge_summaries_matches_pooled_summary():
    from carcassonne.arena import GameResult, merge_summaries

    def res(d):
        return GameResult(0, "a", "b", [d, 0], 0, 0)

    xs = [3, -2, 5, 0, 7, -4, 1, 2]
    whole = summarize([res(d) for d in xs], [])
    parts = [summarize([res(d) for d in xs[:3]], []), summarize([res(d) for d in xs[3:]], [])]
    merged = merge_summaries(parts)
    assert merged.games == whole.games
    assert abs(merged.mean_diff_a - whole.mean_diff_a) < 1e-9
    assert abs(merged.se_diff - whole.se_diff) < 1e-9
    assert abs(merged.win_rate - whole.win_rate) < 1e-9
