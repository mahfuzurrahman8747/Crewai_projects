"""Core domain logic for the trading simulation account management system.

This module is intentionally framework-free: no Gradio, no I/O. The
:class:`Account` class encapsulates the rules around cash, share holdings
and the chronological transaction log so that the UI and the test suite
can both drive it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import prices


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AccountError(Exception):
    """Base class for any error raised by :class:`Account`."""


class InsufficientFundsError(AccountError):
    """Raised when an operation would drive the cash balance negative."""


class InsufficientSharesError(AccountError):
    """Raised when selling more shares than the account currently holds."""


class UnknownSymbolError(AccountError):
    """Raised when a share symbol is not recognised by the price service."""


# ---------------------------------------------------------------------------
# Transaction record
# ---------------------------------------------------------------------------


@dataclass
class Transaction:
    """Immutable record of a single account event."""

    timestamp: str            # ISO-8601 string, generated at construction
    kind: str                 # "DEPOSIT" | "WITHDRAW" | "BUY" | "SELL"
    symbol: Optional[str]     # None for DEPOSIT/WITHDRAW
    quantity: int | float     # shares for BUY/SELL, units of cash otherwise
    price: float              # per-share price for BUY/SELL, cash amount otherwise
    cash_after: float         # cash balance after the transaction was applied

    @classmethod
    def _now(cls) -> str:
        """Return the current UTC timestamp in ISO-8601 format."""
        return datetime.utcnow().isoformat()

    def to_row(self) -> List:
        """Return a row suitable for display in a ``gr.Dataframe``."""
        return [
            self.timestamp,
            self.kind,
            self.symbol if self.symbol is not None else "",
            self.quantity,
            self.price,
            self.cash_after,
        ]


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


class Account:
    """A simple trading-sim account tracking cash, holdings and transactions."""

    def __init__(self, initial_deposit: float = 0.0) -> None:
        if initial_deposit < 0:
            raise ValueError("initial_deposit must be non-negative")

        initial_deposit = float(initial_deposit)

        # Private state. Tests/UI only touch these via the public API.
        self._cash: float = initial_deposit
        self._holdings: Dict[str, int] = {}
        self._transactions: List[Transaction] = []
        self._total_deposited: float = initial_deposit

        # Log the opening deposit so the history reflects every state change,
        # including the very first one.
        if initial_deposit > 0:
            self._transactions.append(
                Transaction(
                    timestamp=Transaction._now(),
                    kind="DEPOSIT",
                    symbol=None,
                    quantity=initial_deposit,
                    price=initial_deposit,
                    cash_after=self._cash,
                )
            )

    # ------------------------------------------------------------------
    # Cash operations
    # ------------------------------------------------------------------

    def deposit_funds(self, amount: float) -> float:
        """Add ``amount`` to the cash balance and log a DEPOSIT row."""
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")

        self._cash += amount
        self._total_deposited += amount
        self._transactions.append(
            Transaction(
                timestamp=Transaction._now(),
                kind="DEPOSIT",
                symbol=None,
                quantity=amount,
                price=amount,
                cash_after=self._cash,
            )
        )
        return self._cash

    def withdraw_funds(self, amount: float) -> float:
        """Subtract ``amount`` from the cash balance, refusing to overdraw."""
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        if self._cash - amount < 0:
            raise InsufficientFundsError(
                f"Cannot withdraw {amount:.2f}: balance is only {self._cash:.2f}"
            )

        self._cash -= amount
        self._transactions.append(
            Transaction(
                timestamp=Transaction._now(),
                kind="WITHDRAW",
                symbol=None,
                quantity=amount,
                price=amount,
                cash_after=self._cash,
            )
        )
        return self._cash

    # ------------------------------------------------------------------
    # Trade operations
    # ------------------------------------------------------------------

    def buy_shares(self, symbol: str, quantity: int) -> float:
        """Buy ``quantity`` shares of ``symbol`` at the current price."""
        self._validate_trade_inputs(symbol, quantity)

        symbol = symbol.upper()
        price = self._lookup_price(symbol)
        cost = price * quantity

        if cost > self._cash:
            raise InsufficientFundsError(
                f"Cannot buy {quantity} shares of {symbol} at {price:.2f} "
                f"(cost {cost:.2f}): balance is only {self._cash:.2f}"
            )

        self._cash -= cost
        self._holdings[symbol] = self._holdings.get(symbol, 0) + int(quantity)
        self._transactions.append(
            Transaction(
                timestamp=Transaction._now(),
                kind="BUY",
                symbol=symbol,
                quantity=int(quantity),
                price=price,
                cash_after=self._cash,
            )
        )
        return self._cash

    def sell_shares(self, symbol: str, quantity: int) -> float:
        """Sell ``quantity`` shares of ``symbol`` at the current price."""
        self._validate_trade_inputs(symbol, quantity)

        symbol = symbol.upper()
        price = self._lookup_price(symbol)
        held = self._holdings.get(symbol, 0)

        if held < quantity:
            raise InsufficientSharesError(
                f"Cannot sell {quantity} shares of {symbol}: only {held} held"
            )

        proceeds = price * quantity
        self._cash += proceeds
        new_qty = held - int(quantity)
        if new_qty > 0:
            self._holdings[symbol] = new_qty
        else:
            self._holdings.pop(symbol, None)

        self._transactions.append(
            Transaction(
                timestamp=Transaction._now(),
                kind="SELL",
                symbol=symbol,
                quantity=int(quantity),
                price=price,
                cash_after=self._cash,
            )
        )
        return self._cash

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_cash_balance(self) -> float:
        """Return the current cash balance."""
        return self._cash

    def get_holdings(self) -> Dict[str, int]:
        """Return a copy of the holdings, omitting any symbols at zero."""
        return {sym: qty for sym, qty in self._holdings.items() if qty > 0}

    def calculate_portfolio_value(self) -> float:
        """Total value = cash + market value of every held position."""
        holdings = self.get_holdings()
        market_value = 0.0
        for sym, qty in holdings.items():
            market_value += qty * self._lookup_price(sym)
        return self._cash + market_value

    def calculate_profit_or_loss(self) -> float:
        """Profit/loss = current portfolio value - total deposited."""
        return self.calculate_portfolio_value() - self._total_deposited

    def get_transaction_history(self) -> List[Transaction]:
        """Return a chronological copy of the transaction log."""
        return list(self._transactions)

    # ------------------------------------------------------------------
    # Convenience helpers for tabular UIs
    # ------------------------------------------------------------------

    def to_holdings_rows(self) -> List[List]:
        """Holdings rendered as ``list[list]`` rows for ``gr.Dataframe``."""
        rows: List[List] = []
        for sym, qty in self.get_holdings().items():
            price = self._lookup_price(sym)
            rows.append([sym, int(qty), price, qty * price])
        return rows

    def to_transaction_rows(self) -> List[List]:
        """Transaction log rendered as ``list[list]`` rows for ``gr.Dataframe``."""
        return [t.to_row() for t in self._transactions]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_trade_inputs(symbol: str, quantity: int) -> None:
        """Validate the common inputs to buy/sell; raise ``ValueError`` on bad input."""
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("Symbol must be a non-empty string")
        # ``bool`` is a subclass of ``int``; reject it explicitly so users
        # can't accidentally pass ``True`` for a quantity.
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise ValueError("Quantity must be a positive integer")
        if quantity <= 0:
            raise ValueError("Quantity must be a positive integer")

    @staticmethod
    def _lookup_price(symbol: str) -> float:
        """Wrap ``prices.get_share_price`` and convert ``ValueError``."""
        try:
            return prices.get_share_price(symbol)
        except ValueError as exc:
            raise UnknownSymbolError(f"Unknown share symbol: {symbol!r}") from exc
