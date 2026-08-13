"""Shopping cart maths."""


def subtotal(items):
    """Sum (unit_price, quantity) pairs."""
    return sum(price * qty for price, qty in items)
