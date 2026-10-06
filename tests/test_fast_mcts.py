import random

import pytest

from carcassonne import State
from carcassonne.agents import GreedyAgent
from carcassonne.arena import run_match
from carcassonne.fast_mcts import FastMCTSAgent


def test_returns_legal_move_throughout_a_game():
    agent = FastMCTSAgent(n_sims=60)
    st = State.new_game(21)
    rng = random.Random(0)
    while not st.over:
        m = agent.act(st, rng)
        assert m in st.legal_moves()
        st.apply(m)


def test_reproducible_with_same_rng_seed():
    st = State.new_game(22)
    rng0 = random.Random(5)
    for _ in range(8):
        st.apply(rng0.choice(st.legal_moves()))
    a = FastMCTSAgent(n_sims=200).act(st, random.Random(1))
    b = FastMCTSAgent(n_sims=200).act(st, random.Random(1))
    assert a == b


def test_does_not_mutate_python_state():
    st = State.new_game(23)
    before = (dict(st.board), list(st.scores), st.draw_pos, list(st.history))
    FastMCTSAgent(n_sims=50).act(st, random.Random(2))
    assert (dict(st.board), list(st.scores), st.draw_pos, list(st.history)) == before


@pytest.mark.parametrize("n_det", [1, 3])
def test_determinization_variants_work(n_det):
    st = State.new_game(24)
    m = FastMCTSAgent(n_sims=90, n_det=n_det).act(st, random.Random(3))
    assert m in st.legal_moves()


def test_truncated_rollouts_work():
    st = State.new_game(25)
    m = FastMCTSAgent(n_sims=60, rollout_depth=6).act(st, random.Random(4))
    assert m in st.legal_moves()


@pytest.mark.parametrize("chance", [True, False])
def test_chance_nodes_toggle_gives_legal_moves(chance):
    st = State.new_game(26)
    rng = random.Random(6)
    for _ in range(10):
        st.apply(rng.choice(st.legal_moves()))
    m = FastMCTSAgent(n_sims=150, chance=chance).act(st, random.Random(7))
    assert m in st.legal_moves()


def test_chance_search_plays_full_game_to_the_end():
    agent = FastMCTSAgent(n_sims=40, chance=True)
    st = State.new_game(27)
    rng = random.Random(8)
    while not st.over:
        st.apply(agent.act(st, rng))
    assert st.over


@pytest.mark.slow
def test_beats_greedy_with_modest_budget():
    from functools import partial

    s = run_match(partial(FastMCTSAgent, 800, 1, 0.3), GreedyAgent, range(6), workers=1)
    assert s.mean_diff_a > 0
