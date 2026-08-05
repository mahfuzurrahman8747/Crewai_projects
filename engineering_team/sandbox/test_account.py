"""Unit tests for the backend module.

Covers ``prices.get_share_price`` and every public method of
``account.Account`` plus the three custom exceptions. Uses only the
standard library (``unittest``) and ``unittest.mock`` (still stdlib) to
stub out ``prices.get_share_price`` so the tests are independent of the
hard-coded values defined in ``prices.py``.

Run with:

    python -m unittest test_account.py -v
"""

from __future__ import annotations

import unittest
from unittest import mock

import account
import prices
from account import (
    Account,
    AccountError,
    InsufficientFundsError,
    InsufficientSharesError,
    Transaction,
    UnknownSymbolError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_price_table(table):
    """Return a function that mimics ``prices.get_share_price`` for tests.

    The returned function performs a case-insensitive lookup in ``table`` and
    raises ``ValueError`` for unknown symbols, exactly like the real one.
    """

    def fake_get_share_price(symbol):
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("Symbol must be a non-empty string")
        key = symbol.upper()
        if key not in table:
            raise ValueError(f"Unknown share symbol: {symbol!r}")
        return float(table[key])

    return fake_get_share_price


def _patch_prices(testcase, table):
    """Patch ``prices.get_share_price`` and ``account.prices.get_share_price``.

    The ``Account`` class reaches into ``prices`` through its module-level
    import, so we patch the attribute in both places. We also restore the
    original at teardown via ``addCleanup``.
    """
    fake = _make_price_table(table)
    testcase.addCleanup(mock.patch.object(prices, "get_share_price",
                                          side_effect=None).stop)
    testcase.addCleanup(mock.patch.object(account.prices, "get_share_price",
                                          side_effect=None).stop)
    mock.patch.object(prices, "get_share_price", new=fake).start()
    mock.patch.object(account.prices, "get_share_price", new=fake).start()
    return fake


# ---------------------------------------------------------------------------
# prices.get_share_price
# ---------------------------------------------------------------------------


class TestPrices(unittest.TestCase):
    """Direct tests for the deterministic price lookup."""

    def test_known_symbols_return_fixed_prices(self):
        self.assertEqual(prices.get_share_price("AAPL"), 150.0)
        self.assertEqual(prices.get_share_price("TSLA"), 700.0)
        self.assertEqual(prices.get_share_price("GOOGL"), 2800.0)

    def test_case_insensitive_lookup(self):
        self.assertEqual(prices.get_share_price("aapl"), 150.0)
        self.assertEqual(prices.get_share_price("AaPl"), 150.0)
        self.assertEqual(prices.get_share_price("tsla"), 700.0)

    def test_unknown_symbol_raises_value_error(self):
        with self.assertRaises(ValueError):
            prices.get_share_price("MSFT")

    def test_empty_symbol_raises_value_error(self):
        with self.assertRaises(ValueError):
            prices.get_share_price("")

    def test_non_string_symbol_raises_value_error(self):
        with self.assertRaises(ValueError):
            prices.get_share_price(None)
        with self.assertRaises(ValueError):
            prices.get_share_price(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Account construction
# ---------------------------------------------------------------------------


class TestAccountConstruction(unittest.TestCase):
    """Tests around ``Account.__init__`` and the opening-deposit record."""

    def test_create_with_initial_deposit(self):
        a = Account(1000)
        self.assertEqual(a.get_cash_balance(), 1000.0)

    def test_create_with_zero_initial_deposit(self):
        a = Account(0)
        self.assertEqual(a.get_cash_balance(), 0.0)
        # No transactions should be logged when the initial deposit is 0.
        self.assertEqual(a.get_transaction_history(), [])

    def test_create_with_default_zero(self):
        a = Account()
        self.assertEqual(a.get_cash_balance(), 0.0)

    def test_create_rejects_negative_deposit(self):
        with self.assertRaises(ValueError):
            Account(-1)

    def test_initial_deposit_is_logged(self):
        a = Account(500)
        hist = a.get_transaction_history()
        self.assertEqual(len(hist), 1)
        t = hist[0]
        self.assertEqual(t.kind, "DEPOSIT")
        self.assertIsNone(t.symbol)
        self.assertEqual(t.quantity, 500)
        self.assertEqual(t.price, 500)
        self.assertEqual(t.cash_after, 500)
        # The timestamp is a non-empty string.
        self.assertIsInstance(t.timestamp, str)
        self.assertTrue(t.timestamp)


# ---------------------------------------------------------------------------
# Deposit / withdraw
# ---------------------------------------------------------------------------


class TestDepositWithdraw(unittest.TestCase):
    """Tests for the cash-side methods."""

    def setUp(self):
        self.acct = Account(1000)

    def test_deposit_increases_cash(self):
        new_balance = self.acct.deposit_funds(500)
        self.assertEqual(new_balance, 1500.0)
        self.assertEqual(self.acct.get_cash_balance(), 1500.0)

    def test_deposit_logs_transaction(self):
        self.acct.deposit_funds(250)
        hist = self.acct.get_transaction_history()
        # 1 opening deposit + 1 user deposit
        self.assertEqual(len(hist), 2)
        t = hist[-1]
        self.assertEqual(t.kind, "DEPOSIT")
        self.assertEqual(t.quantity, 250)
        self.assertEqual(t.price, 250)
        self.assertEqual(t.cash_after, 1250)

    def test_deposit_accepts_int_amount(self):
        # Amounts should be coerced to float for arithmetic consistency.
        new_balance = self.acct.deposit_funds(100)  # int input
        self.assertEqual(new_balance, 1100.0)

    def test_deposit_rejects_zero(self):
        with self.assertRaises(ValueError):
            self.acct.deposit_funds(0)

    def test_deposit_rejects_negative(self):
        with self.assertRaises(ValueError):
            self.acct.deposit_funds(-10)

    def test_withdraw_decreases_cash(self):
        new_balance = self.acct.withdraw_funds(200)
        self.assertEqual(new_balance, 800.0)
        self.assertEqual(self.acct.get_cash_balance(), 800.0)

    def test_withdraw_logs_transaction(self):
        self.acct.withdraw_funds(150)
        hist = self.acct.get_transaction_history()
        t = hist[-1]
        self.assertEqual(t.kind, "WITHDRAW")
        self.assertEqual(t.quantity, 150)
        self.assertEqual(t.price, 150)
        self.assertEqual(t.cash_after, 850)

    def test_withdraw_exact_balance(self):
        # Withdrawing the entire balance should be allowed.
        new_balance = self.acct.withdraw_funds(1000)
        self.assertEqual(new_balance, 0.0)
        self.assertEqual(self.acct.get_cash_balance(), 0.0)

    def test_withdraw_rejects_overdraw(self):
        with self.assertRaises(InsufficientFundsError):
            self.acct.withdraw_funds(1000.01)

    def test_withdraw_rejects_zero(self):
        with self.assertRaises(ValueError):
            self.acct.withdraw_funds(0)

    def test_withdraw_rejects_negative(self):
        with self.assertRaises(ValueError):
            self.acct.withdraw_funds(-50)

    def test_exception_hierarchy(self):
        # InsufficientFundsError is a subclass of AccountError.
        self.assertTrue(issubclass(InsufficientFundsError, AccountError))
        self.assertTrue(issubclass(InsufficientSharesError, AccountError))
        self.assertTrue(issubclass(UnknownSymbolError, AccountError))


# ---------------------------------------------------------------------------
# Buying shares
# ---------------------------------------------------------------------------


class TestBuyShares(unittest.TestCase):
    """Tests for ``Account.buy_shares``."""

    def setUp(self):
        # Pin prices for every test in this class.
        _patch_prices(self, {"AAPL": 150.0, "TSLA": 700.0, "GOOGL": 2800.0})
        self.acct = Account(10_000)

    def test_buy_decreases_cash_and_increases_holdings(self):
        cash = self.acct.buy_shares("AAPL", 5)
        self.assertEqual(cash, 10_000 - 5 * 150.0)
        self.assertEqual(self.acct.get_cash_balance(), 10_000 - 5 * 150.0)
        self.assertEqual(self.acct.get_holdings(), {"AAPL": 5})

    def test_buy_logs_transaction(self):
        self.acct.buy_shares("AAPL", 3)
        t = self.acct.get_transaction_history()[-1]
        self.assertEqual(t.kind, "BUY")
        self.assertEqual(t.symbol, "AAPL")
        self.assertEqual(t.quantity, 3)
        self.assertEqual(t.price, 150.0)
        self.assertEqual(t.cash_after, 10_000 - 3 * 150.0)

    def test_buy_case_insensitive(self):
        self.acct.buy_shares("aapl", 2)
        # Holdings are stored upper-case.
        self.assertEqual(self.acct.get_holdings(), {"AAPL": 2})

    def test_multiple_buys_accumulate(self):
        self.acct.buy_shares("AAPL", 5)
        self.acct.buy_shares("AAPL", 2)
        self.assertEqual(self.acct.get_holdings(), {"AAPL": 7})

    def test_buy_rejects_insufficient_cash(self):
        # 100 * 700 = 70000, way more than 10000 cash.
        with self.assertRaises(InsufficientFundsError):
            self.acct.buy_shares("TSLA", 100)

    def test_buy_rejects_unknown_symbol(self):
        with self.assertRaises(UnknownSymbolError):
            self.acct.buy_shares("XYZ", 1)

    def test_buy_rejects_zero_quantity(self):
        with self.assertRaises(ValueError):
            self.acct.buy_shares("AAPL", 0)

    def test_buy_rejects_negative_quantity(self):
        with self.assertRaises(ValueError):
            self.acct.buy_shares("AAPL", -1)

    def test_buy_rejects_empty_symbol(self):
        with self.assertRaises(ValueError):
            self.acct.buy_shares("", 1)

    def test_buy_rejects_whitespace_symbol(self):
        with self.assertRaises(ValueError):
            self.acct.buy_shares("   ", 1)

    def test_buy_rejects_non_string_symbol(self):
        with self.assertRaises(ValueError):
            self.acct.buy_shares(None, 1)  # type: ignore[arg-type]

    def test_buy_rejects_non_int_quantity(self):
        with self.assertRaises(ValueError):
            self.acct.buy_shares("AAPL", 1.5)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            self.acct.buy_shares("AAPL", "5")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            self.acct.buy_shares("AAPL", True)  # bool is a subclass of int

    def test_buy_state_unchanged_after_error(self):
        cash_before = self.acct.get_cash_balance()
        holdings_before = dict(self.acct.get_holdings())
        hist_len_before = len(self.acct.get_transaction_history())
        with self.assertRaises(InsufficientFundsError):
            self.acct.buy_shares("TSLA", 100)
        self.assertEqual(self.acct.get_cash_balance(), cash_before)
        self.assertEqual(self.acct.get_holdings(), holdings_before)
        self.assertEqual(len(self.acct.get_transaction_history()), hist_len_before)


# ---------------------------------------------------------------------------
# Selling shares
# ---------------------------------------------------------------------------


class TestSellShares(unittest.TestCase):
    """Tests for ``Account.sell_shares``."""

    def setUp(self):
        _patch_prices(self, {"AAPL": 150.0, "TSLA": 700.0, "GOOGL": 2800.0})
        self.acct = Account(10_000)
        self.acct.buy_shares("AAPL", 5)

    def test_sell_increases_cash_and_decreases_holdings(self):
        cash = self.acct.sell_shares("AAPL", 2)
        # After buying 5, cash = 10000 - 5*150 = 9250.
        # Selling 2 adds 300 -> 9550.
        self.assertEqual(cash, 9550.0)
        self.assertEqual(self.acct.get_holdings(), {"AAPL": 3})

    def test_sell_logs_transaction(self):
        self.acct.sell_shares("AAPL", 1)
        t = self.acct.get_transaction_history()[-1]
        self.assertEqual(t.kind, "SELL")
        self.assertEqual(t.symbol, "AAPL")
        self.assertEqual(t.quantity, 1)
        self.assertEqual(t.price, 150.0)
        self.assertEqual(t.cash_after, 10000 - 5 * 150.0 + 150.0)

    def test_sell_case_insensitive(self):
        self.acct.sell_shares("aapl", 1)
        self.assertEqual(self.acct.get_holdings(), {"AAPL": 4})

    def test_sell_all_removes_holding(self):
        # After selling all 5 AAPL shares, the symbol should no longer appear.
        self.acct.sell_shares("AAPL", 5)
        self.assertEqual(self.acct.get_holdings(), {})

    def test_sell_rejects_insufficient_shares(self):
        with self.assertRaises(InsufficientSharesError):
            self.acct.sell_shares("AAPL", 6)

    def test_sell_rejects_unknown_symbol(self):
        with self.assertRaises(UnknownSymbolError):
            self.acct.sell_shares("XYZ", 1)

    def test_sell_rejects_zero_quantity(self):
        with self.assertRaises(ValueError):
            self.acct.sell_shares("AAPL", 0)

    def test_sell_rejects_negative_quantity(self):
        with self.assertRaises(ValueError):
            self.acct.sell_shares("AAPL", -1)

    def test_sell_rejects_empty_symbol(self):
        with self.assertRaises(ValueError):
            self.acct.sell_shares("", 1)

    def test_sell_rejects_non_int_quantity(self):
        with self.assertRaises(ValueError):
            self.acct.sell_shares("AAPL", 1.5)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            self.acct.sell_shares("AAPL", True)

    def test_sell_state_unchanged_after_error(self):
        cash_before = self.acct.get_cash_balance()
        holdings_before = dict(self.acct.get_holdings())
        hist_len_before = len(self.acct.get_transaction_history())
        with self.assertRaises(InsufficientSharesError):
            self.acct.sell_shares("AAPL", 6)
        self.assertEqual(self.acct.get_cash_balance(), cash_before)
        self.assertEqual(self.acct.get_holdings(), holdings_before)
        self.assertEqual(len(self.acct.get_transaction_history()), hist_len_before)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


class TestReporting(unittest.TestCase):
    """Tests for ``get_holdings``, ``calculate_portfolio_value`` and
    ``calculate_profit_or_loss``."""

    def setUp(self):
        _patch_prices(self, {"AAPL": 100.0, "TSLA": 200.0, "GOOGL": 1000.0})
        self.acct = Account(5000)

    def test_get_holdings_empty_initially(self):
        a = Account()
        self.assertEqual(a.get_holdings(), {})

    def test_get_holdings_returns_copy(self):
        self.acct.buy_shares("AAPL", 3)
        holdings = self.acct.get_holdings()
        # Mutating the returned dict must not affect internal state.
        holdings["AAPL"] = 999
        self.assertEqual(self.acct.get_holdings(), {"AAPL": 3})

    def test_get_holdings_omits_zero_quantities(self):
        self.acct.buy_shares("AAPL", 3)
        self.acct.sell_shares("AAPL", 3)
        # No holdings left; the empty dict (not {"AAPL": 0}) is returned.
        self.assertEqual(self.acct.get_holdings(), {})

    def test_calculate_portfolio_value_cash_only(self):
        # With no holdings, the portfolio value is just the cash balance.
        self.assertEqual(self.acct.calculate_portfolio_value(), 5000.0)

    def test_calculate_portfolio_value_includes_holdings(self):
        self.acct.buy_shares("AAPL", 10)  # 10 * 100 = 1000
        self.acct.buy_shares("TSLA", 5)   # 5 * 200 = 1000
        # Cash = 5000 - 2000 = 3000, market value = 2000, total = 5000.
        self.assertEqual(self.acct.calculate_portfolio_value(), 5000.0)

    def test_calculate_portfolio_value_uses_current_prices(self):
        self.acct.buy_shares("AAPL", 10)
        # Now reprice AAPL: 10 * 250 = 2500, cash unchanged at 4000.
        _patch_prices(self, {"AAPL": 250.0, "TSLA": 200.0, "GOOGL": 1000.0})
        self.assertEqual(self.acct.calculate_portfolio_value(), 6500.0)

    def test_calculate_profit_or_loss_breaks_even(self):
        # Buy at the same price used to evaluate -> P/L is 0.
        self.acct.buy_shares("AAPL", 10)
        self.assertEqual(self.acct.calculate_profit_or_loss(), 0.0)

    def test_calculate_profit_or_loss_positive(self):
        # Deposit 1000 extra so total deposited is 6000, then buy AAPL and
        # reprice up to 200/share -> 10 * 200 = 2000 market value, P/L =
        # (2000 + 4000 cash) - 6000 = 0... not what we want.
        #
        # Better: deposit 0 initially, then deposit 1000 (total 1000),
        # then buy AAPL at 100 (10 shares -> cost 1000, cash 0),
        # then reprice AAPL to 200 -> market value 2000, cash 0,
        # total portfolio 2000, P/L = 2000 - 1000 = 1000.
        a = Account(0)
        a.deposit_funds(1000)
        a.buy_shares("AAPL", 10)
        # Sanity: cash = 0, holdings = 10 AAPL, P/L = 0 so far.
        self.assertEqual(a.calculate_profit_or_loss(), 0.0)
        _patch_prices(self, {"AAPL": 200.0, "TSLA": 200.0, "GOOGL": 1000.0})
        # Market value 2000, cash 0, portfolio 2000, total deposited 1000
        # -> P/L = 1000.
        self.assertEqual(a.calculate_profit_or_loss(), 1000.0)

    def test_calculate_profit_or_loss_negative(self):
        # Symmetric to the positive case but reprice AAPL down to 50.
        a = Account(0)
        a.deposit_funds(1000)
        a.buy_shares("AAPL", 10)
        _patch_prices(self, {"AAPL": 50.0, "TSLA": 200.0, "GOOGL": 1000.0})
        # Market value 500, cash 0, portfolio 500, total deposited 1000
        # -> P/L = -500.
        self.assertEqual(a.calculate_profit_or_loss(), -500.0)

    def test_calculate_profit_or_loss_includes_withdrawals(self):
        # Withdrawals do not change total_deposited, so they reduce P/L.
        self.acct.buy_shares("AAPL", 10)
        # Cash 4000, market value 1000, portfolio 5000, P/L 0.
        self.acct.withdraw_funds(500)
        # Cash 3500, market value 1000, portfolio 4500, P/L -500.
        self.assertEqual(self.acct.calculate_profit_or_loss(), -500.0)


# ---------------------------------------------------------------------------
# Transaction history
# ---------------------------------------------------------------------------


class TestTransactionHistory(unittest.TestCase):
    """Tests for ``get_transaction_history`` and the row helpers."""

    def setUp(self):
        _patch_prices(self, {"AAPL": 150.0, "TSLA": 700.0, "GOOGL": 2800.0})

    def test_history_returns_copy(self):
        a = Account(1000)
        hist = a.get_transaction_history()
        hist.clear()
        # The internal log should still have the opening deposit.
        self.assertEqual(len(a.get_transaction_history()), 1)

    def test_history_is_chronological(self):
        a = Account(1000)
        a.deposit_funds(500)
        a.buy_shares("AAPL", 2)
        a.sell_shares("AAPL", 1)
        a.withdraw_funds(100)
        hist = a.get_transaction_history()
        kinds = [t.kind for t in hist]
        self.assertEqual(
            kinds,
            ["DEPOSIT", "DEPOSIT", "BUY", "SELL", "WITHDRAW"],
        )

    def test_history_is_complete(self):
        a = Account(1000)
        a.deposit_funds(500)
        a.buy_shares("AAPL", 2)
        a.sell_shares("AAPL", 1)
        a.withdraw_funds(100)
        self.assertEqual(len(a.get_transaction_history()), 5)

    def test_history_records_correct_cash_after(self):
        a = Account(1000)
        a.deposit_funds(500)  # 1500
        a.buy_shares("AAPL", 2)  # 1500 - 300 = 1200
        a.sell_shares("AAPL", 1)  # 1200 + 150 = 1350
        a.withdraw_funds(100)  # 1250
        cash_after = [t.cash_after for t in a.get_transaction_history()]
        self.assertEqual(cash_after, [1000.0, 1500.0, 1200.0, 1350.0, 1250.0])

    def test_history_timestamps_are_unique_strings(self):
        a = Account(1000)
        a.deposit_funds(100)
        a.deposit_funds(200)
        ts = [t.timestamp for t in a.get_transaction_history()]
        for t in ts:
            self.assertIsInstance(t, str)
            self.assertTrue(t)


# ---------------------------------------------------------------------------
# Transaction.to_row and the *rows helpers
# ---------------------------------------------------------------------------


class TestTransactionToRow(unittest.TestCase):
    def test_buy_row_contains_symbol(self):
        t = Transaction("2024-01-01T00:00:00", "BUY", "AAPL", 5, 150.0, 250.0)
        self.assertEqual(
            t.to_row(),
            ["2024-01-01T00:00:00", "BUY", "AAPL", 5, 150.0, 250.0],
        )

    def test_deposit_row_has_empty_symbol(self):
        t = Transaction("2024-01-01T00:00:00", "DEPOSIT", None, 100, 100, 100)
        row = t.to_row()
        self.assertEqual(row[2], "")  # symbol column blank
        self.assertEqual(row[0], "2024-01-01T00:00:00")
        self.assertEqual(row[1], "DEPOSIT")

    def test_withdraw_row_has_empty_symbol(self):
        t = Transaction("2024-01-01T00:00:00", "WITHDRAW", None, 50, 50, 50)
        row = t.to_row()
        self.assertEqual(row[2], "")
        self.assertEqual(row[1], "WITHDRAW")

    def test_sell_row_contains_symbol(self):
        t = Transaction("2024-01-01T00:00:00", "SELL", "TSLA", 2, 700.0, 1400.0)
        row = t.to_row()
        self.assertEqual(row[1], "SELL")
        self.assertEqual(row[2], "TSLA")
        self.assertEqual(row[3], 2)


class TestRowHelpers(unittest.TestCase):
    """Tests for ``to_holdings_rows`` and ``to_transaction_rows``."""

    def setUp(self):
        _patch_prices(self, {"AAPL": 150.0, "TSLA": 700.0, "GOOGL": 2800.0})

    def test_to_holdings_rows_empty(self):
        a = Account()
        self.assertEqual(a.to_holdings_rows(), [])

    def test_to_holdings_rows_contents(self):
        a = Account(10_000)
        a.buy_shares("AAPL", 3)
        a.buy_shares("TSLA", 1)
        rows = a.to_holdings_rows()
        # Each row: [symbol, quantity, current_price, market_value].
        by_sym = {row[0]: row for row in rows}
        self.assertIn("AAPL", by_sym)
        self.assertIn("TSLA", by_sym)
        self.assertEqual(by_sym["AAPL"][1], 3)
        self.assertEqual(by_sym["AAPL"][2], 150.0)
        self.assertEqual(by_sym["AAPL"][3], 3 * 150.0)
        self.assertEqual(by_sym["TSLA"][1], 1)
        self.assertEqual(by_sym["TSLA"][2], 700.0)
        self.assertEqual(by_sym["TSLA"][3], 1 * 700.0)

    def test_to_holdings_rows_after_full_sell(self):
        a = Account(10_000)
        a.buy_shares("AAPL", 3)
        a.sell_shares("AAPL", 3)
        self.assertEqual(a.to_holdings_rows(), [])

    def test_to_transaction_rows_empty(self):
        a = Account()
        self.assertEqual(a.to_transaction_rows(), [])

    def test_to_transaction_rows_matches_history(self):
        a = Account(1000)
        a.deposit_funds(500)
        a.buy_shares("AAPL", 2)
        a.sell_shares("AAPL", 1)
        a.withdraw_funds(50)
        rows = a.to_transaction_rows()
        hist = a.get_transaction_history()
        self.assertEqual(len(rows), len(hist))
        for row, txn in zip(rows, hist):
            self.assertEqual(row, txn.to_row())


# ---------------------------------------------------------------------------
# Full-lifecycle integration
# ---------------------------------------------------------------------------


class TestFullLifecycle(unittest.TestCase):
    """End-to-end happy path that exercises every public method."""

    def setUp(self):
        _patch_prices(self, {"AAPL": 150.0, "TSLA": 700.0, "GOOGL": 2800.0})

    def test_deposit_buy_sell_withdraw(self):
        a = Account(5000)
        a.deposit_funds(5000)
        a.buy_shares("AAPL", 10)
        a.buy_shares("GOOGL", 1)
        a.sell_shares("AAPL", 4)
        a.withdraw_funds(100)

        # Cash: 5000 + 5000 - 10*150 - 1*2800 + 4*150 - 100
        expected_cash = 5000 + 5000 - 1500 - 2800 + 600 - 100
        self.assertEqual(a.get_cash_balance(), expected_cash)

        holdings = a.get_holdings()
        self.assertEqual(holdings.get("AAPL"), 6)
        self.assertEqual(holdings.get("GOOGL"), 1)

        # Market value: 6 * 150 + 1 * 2800 = 900 + 2800 = 3700.
        # Portfolio value: cash + market = expected_cash + 3700.
        self.assertEqual(
            a.calculate_portfolio_value(), expected_cash + 3700.0
        )
        # P/L: portfolio - total_deposited = (expected_cash + 3700) - 10000
        self.assertEqual(
            a.calculate_profit_or_loss(),
            (expected_cash + 3700.0) - 10_000.0,
        )

        # History has 6 entries: 2 deposits + 2 buys + 1 sell + 1 withdraw.
        hist = a.get_transaction_history()
        self.assertEqual(len(hist), 6)
        self.assertEqual(
            [t.kind for t in hist],
            ["DEPOSIT", "DEPOSIT", "BUY", "BUY", "SELL", "WITHDRAW"],
        )

    def test_account_error_is_base_class(self):
        # Custom errors raised by ``Account`` should always be catchable
        # via ``AccountError``.
        a = Account(100)
        with self.assertRaises(AccountError):
            a.withdraw_funds(200)
        with self.assertRaises(AccountError):
            a.buy_shares("XYZ", 1)
        with self.assertRaises(AccountError):
            a.sell_shares("XYZ", 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
