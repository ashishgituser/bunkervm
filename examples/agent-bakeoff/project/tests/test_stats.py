from stats import average, total


def test_average_basic():
    assert average([1, 2, 3]) == 2


def test_total_basic():
    assert total([1, 2, 3]) == 6


def test_average_of_empty_is_zero():
    # Reported by a user: the dashboard crashes on a brand-new account,
    # because it averages an empty list of orders.
    assert average([]) == 0.0
