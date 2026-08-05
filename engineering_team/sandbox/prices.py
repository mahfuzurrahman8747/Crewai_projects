"""Test implementation of share price lookups for the trading simulation.

Provides a deterministic ``get_share_price`` for the rest of the system.
In production this would call out to a market data provider; for the
simulation we hard-code three tickers and reject anything else loudly so
the domain layer can surface bad input cleanly.
"""

from __future__ import annotations


# Fixed price table. Kept module-level for clarity; in a real system this
# would be replaced by an API client.
_PRICES = {
    "AAPL": 150.0,
    "TSLA": 700.0,
    "GOOGL": 2800.0,
}


def get_share_price(symbol: str) -> float:
    """Return the current per-share price for ``symbol``.

    The lookup is case-insensitive. Known symbols (``AAPL``, ``TSLA``,
    ``GOOGL``) return a fixed price; any other input raises
    :class:`ValueError` so the caller can convert that into a domain-level
    :class:`UnknownSymbolError`.
    """
    if not isinstance(symbol, str) or not symbol:
        raise ValueError("Symbol must be a non-empty string")

    key = symbol.upper()
    if key not in _PRICES:
        raise ValueError(f"Unknown share symbol: {symbol!r}")

    return float(_PRICES[key])
