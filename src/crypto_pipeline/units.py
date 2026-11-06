"""Explicit native-unit arithmetic. No symbol-derived or implicit FX conversions."""
# Import Decimal, localcontext from decimal for use below.
from decimal import Decimal, localcontext
# Import decimal_text from .normalization for use below.
from .normalization import decimal_text


# Aggressive buy minus sell turnover, in the original quote asset.
def quote_delta(total_quote, taker_buy_quote):
    """Aggressive buy minus sell turnover, in the original quote asset."""
    # Construct an exact decimal from the supplied value; store the result in total.
    total = Decimal(decimal_text(total_quote, 'quote volume'))
    # Construct an exact decimal from the supplied value; store the result in buy.
    buy = Decimal(decimal_text(taker_buy_quote, 'taker-buy quote volume'))
    # Enter this branch only when buy > total.
    if buy > total:
        # Stop this operation with ValueError('Taker-buy quote exceeds total volume').
        raise ValueError('Taker-buy quote exceeds total volume')
    # Use local Decimal precision without changing the caller's arithmetic settings.
    with localcontext() as ctx:
        # Retain the widest integer/fractional span plus carry digits when subtracting large values.
        ctx.prec = max(28, max(total.adjusted(), buy.adjusted()) - min(total.as_tuple().exponent, buy.as_tuple().exponent) + 3)
        # Selling turnover is total minus buy; buy minus sell therefore equals twice buy minus total.
        return 2 * buy - total


# Opt-in conversion requiring an externally verified factor and its source.
def underlying_quantity(native_quantity, multiplier, evidence):
    """Opt-in conversion requiring an externally verified factor and its source."""
    # Block underlying-token conversion until both a factor and its evidence are supplied.
    if multiplier is None or not evidence:
        # Stop this operation with ValueError('A verified multiplier and evidence are required').
        raise ValueError('A verified multiplier and evidence are required')
    # Construct an exact decimal from the supplied value; store the result in quantity.
    quantity = Decimal(decimal_text(native_quantity, 'native quantity'))
    # Construct an exact decimal from the supplied value; store the result in factor.
    factor = Decimal(decimal_text(multiplier, 'underlying multiplier', True))
    # Use local Decimal precision without changing the caller's arithmetic settings.
    with localcontext() as ctx:
        # Multiplication can require the sum of both inputs' digit counts; retain that precision.
        ctx.prec = max(28, len(quantity.as_tuple().digits) + len(factor.as_tuple().digits))
        # Scale native quantity by the supplied underlying-token factor; do not scale quote notional.
        return quantity * factor
