import numpy as np

from carcassonne.td import td_lambda_targets


def test_lambda_one_is_final_score():
    v = np.array([1.0, 2.0, 3.0, 4.0])
    finals = np.array([10.0, -10.0, 10.0, -10.0])
    p = np.array([0, 1, 0, 1])
    g = np.zeros(4, np.int64)
    assert np.allclose(td_lambda_targets(v, finals, p, g, 1.0), finals)


def test_lambda_zero_is_next_value_from_movers_view():
    v = np.array([1.0, 2.0, 3.0])
    finals = np.array([5.0, -5.0, 5.0])
    p = np.array([0, 1, 0])
    g = np.zeros(3, np.int64)
    # 次の局面は相手の手番なので符号が反転する。最後の局面は終局得点差
    assert np.allclose(td_lambda_targets(v, finals, p, g, 0.0), [-2.0, -3.0, 5.0])


def test_games_are_independent():
    v = np.array([1.0, 2.0, 7.0, 8.0])
    finals = np.array([4.0, -4.0, 9.0, -9.0])
    p = np.array([0, 1, 0, 1])
    g = np.array([0, 0, 1, 1])
    out = td_lambda_targets(v, finals, p, g, 0.5)
    assert out[1] == -4.0 and out[3] == -9.0
    assert np.isclose(out[0], -(0.5 * 2.0 + 0.5 * -4.0))
