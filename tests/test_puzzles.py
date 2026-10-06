import random

from carcassonne.fast_mcts import FastMCTSAgent
from carcassonne.puzzles import analyze, move_facts, pick_options, reward_to_diff
from carcassonne.state import State


def test_reward_to_diff_inverts_reward():
    assert abs(reward_to_diff(0.5, 30.0)) < 1e-9
    assert reward_to_diff(0.8, 30.0) > 0 > reward_to_diff(0.2, 30.0)


def test_analyze_returns_legal_options_and_best_first():
    st = State.new_game(3)
    rng = random.Random(0)
    for _ in range(6):
        st.apply(rng.choice(st.legal_moves()))
    agent = FastMCTSAgent(n_sims=400)
    opts = analyze(agent, st, seed=1)
    legal = set(st.legal_moves())
    assert opts and all(o.move in legal for o in opts)
    assert 300 < sum(o.visits for o in opts) <= 400  # 着手節点が葉になった訪問は断片別に数えない
    chosen = pick_options(opts)
    assert chosen[0].visits == max(o.visits for o in opts)
    assert all(o.diff < chosen[0].diff for o in chosen[1:])
    facts = move_facts(st, chosen[0].move)
    assert {"gain_me", "gain_opp", "proj_me", "proj_opp", "meeple"} <= facts.keys()
