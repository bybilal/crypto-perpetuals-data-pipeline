"""Explicit native-unit arithmetic. No symbol-derived or implicit FX conversions."""
from decimal import Decimal, localcontext
from .normalization import decimal_text


def quote_delta(total_quote, taker_buy_quote):
    """Aggressive buy minus sell turnover, in the original quote asset."""
    total = Decimal(decimal_text(total_quote, 'quote volume'))
    buy = Decimal(decimal_text(taker_buy_quote, 'taker-buy quote volume'))
    if buy > total:
        raise ValueError('Taker-buy quote exceeds total volume')
    with localcontext() as ctx:
        ctx.prec = max(28, max(total.adjusted(), buy.adjusted()) - min(total.as_tuple().exponent, buy.as_tuple().exponent) + 3)
        return 2 * buy - total


def underlying_quantity(native_quantity, multiplier, evidence):
    """Opt-in conversion requiring an externally verified factor and its source."""
    if multiplier is None or not evidence:
        raise ValueError('A verified multiplier and evidence are required')
    quantity = Decimal(decimal_text(native_quantity, 'native quantity'))
    factor = Decimal(decimal_text(multiplier, 'underlying multiplier', True))
    with localcontext() as ctx:
        ctx.prec = max(28, len(quantity.as_tuple().digits) + len(factor.as_tuple().digits))
        return quantity * factor
