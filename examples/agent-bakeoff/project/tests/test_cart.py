from cart import subtotal


def test_subtotal():
    assert subtotal([(2.5, 2), (1.0, 3)]) == 8.0


def test_subtotal_empty():
    assert subtotal([]) == 0
