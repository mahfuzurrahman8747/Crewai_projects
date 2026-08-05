"""Smoke test for the backend implementation.

Verifies the Account class meets the design requirements end-to-end
without taking a dependency on pytest.
"""

import prices
import account
from account import (
    Account,
    InsufficientFundsError,
    InsufficientSharesError,
    UnknownSymbolError,
    Transaction,
)


def assert_eq(actual, expected, label):
    assert actual == expected, f"{label}: expected {expected!r}, got {actual!r}"


def assert_raises(fn, exc, label):
    try:
        fn()
    except exc:
        return
    except Exception as e:
        raise AssertionError(f"{label}: expected {exc.__name__}, got {type(e).__name__}: {e}")
    raise AssertionError(f"{label}: expected {exc.__name__}, but no exception was raised")


def test_prices():
    assert_eq(prices.get_share_price("AAPL"), 150.0, "AAPL price")
    assert_eq(prices.get_share_price("aapl"), 150.0, "AAPL case-insensitive")
    assert_eq(prices.get_share_price("TSLA"), 700.0, "TSLA price")
    assert_eq(prices.get_share_price("GOOGL"), 2800.0, "GOOGL price")
    assert_raises(lambda: prices.get_share_price("XYZ"), ValueError, "unknown symbol")


def test_account_basic():
    a = Account(1000)
    assert_eq(a.get_cash_balance(), 1000.0, "initial balance")

    # deposit
    bal = a.deposit_funds(500)
    assert_eq(bal, 1500.0, "after deposit")
    assert_eq(a.get_cash_balance(), 1500.0, "get_cash_balance after deposit")

    # withdraw
    bal = a.withdraw_funds(200)
    assert_eq(bal, 1300.0, "after withdraw")

    assert_raises(lambda: a.withdraw_funds(99999), InsufficientFundsError, "over-withdraw")
    assert_raises(lambda: a.deposit_funds(-1), ValueError, "negative deposit")
    assert_raises(lambda: a.withdraw_funds(0), ValueError, "zero withdraw")
    assert_raises(lambda: Account(-1), ValueError, "negative initial deposit")


def test_buy_sell():
    a = Account(10_000)

    # buy AAPL
    cash = a.buy_shares("AAPL", 5)
    assert_eq(cash, 10_000 - 5 * 150.0, "cash after buy AAPL")
    assert_eq(a.get_holdings(), {"AAPL": 5}, "holdings after buy")

    # buy more TSLA
    cash = a.buy_shares("TSLA", 2)
    assert_eq(cash, 10_000 - 5 * 150.0 - 2 * 700.0, "cash after buy TSLA")
    assert_eq(a.get_holdings(), {"AAPL": 5, "TSLA": 2}, "holdings after second buy")

    # sell
    cash = a.sell_shares("AAPL", 2)
    assert_eq(cash, 10_000 - 5 * 150.0 - 2 * 700.0 + 2 * 150.0, "cash after sell AAPL")
    assert_eq(a.get_holdings(), {"AAPL": 3, "TSLA": 2}, "holdings after sell")

    # sell all AAPL -> entry should be removed
    a.sell_shares("AAPL", 3)
    assert_eq(a.get_holdings(), {"TSLA": 2}, "holdings zero-out")

    # errors
    assert_raises(lambda: a.sell_shares("AAPL", 1), InsufficientSharesError, "sell no shares")
    assert_raises(lambda: a.buy_shares("AAPL", 999_999), InsufficientFundsError, "buy broke")
    assert_raises(lambda: a.buy_shares("XYZ", 1), UnknownSymbolError, "unknown symbol buy")
    assert_raises(lambda: a.sell_shares("XYZ", 1), UnknownSymbolError, "unknown symbol sell")
    assert_raises(lambda: a.buy_shares("AAPL", 0), ValueError, "zero qty buy")
    assert_raises(lambda: a.buy_shares("AAPL", -1), ValueError, "negative qty buy")
    assert_raises(lambda: a.buy_shares("", 1), ValueError, "empty symbol")


def test_portfolio_and_pnl():
    a = Account(10_000)
    a.buy_shares("AAPL", 5)
    a.buy_shares("TSLA", 1)
    expected_market = 5 * 150.0 + 1 * 700.0
    expected_cash = 10_000 - expected_market
    expected_value = expected_cash + expected_market
    assert_eq(a.calculate_portfolio_value(), expected_value, "portfolio value")
    assert_eq(a.calculate_profit_or_loss(), expected_value - 10_000, "profit/loss")


def test_history_ordering():
    a = Account(1000)
    a.deposit_funds(500)
    a.buy_shares("AAPL", 2)
    a.sell_shares("AAPL", 1)
    a.withdraw_funds(100)
    hist = a.get_transaction_history()
    # initial deposit created on construction is a DEPOSIT, then 4 ops => 5 total
    assert_eq(len(hist), 5, "history length")
    assert_eq(hist[0].kind, "DEPOSIT", "hist[0] kind (initial)")
    assert_eq(hist[1].kind, "DEPOSIT", "hist[1] kind")
    assert_eq(hist[2].kind, "BUY", "hist[2] kind")
    assert_eq(hist[3].kind, "SELL", "hist[3] kind")
    assert_eq(hist[4].kind, "WITHDRAW", "hist[4] kind")


def test_holdings_zero_filter():
    a = Account(10_000)
    a.buy_shares("AAPL", 3)
    a.sell_shares("AAPL", 3)
    assert_eq(a.get_holdings(), {}, "holdings after selling all")


def test_transaction_to_row():
    t = Transaction("2024-01-01T00:00:00", "BUY", "AAPL", 5, 150.0, 250.0)
    assert_eq(
        t.to_row(),
        ["2024-01-01T00:00:00", "BUY", "AAPL", 5, 150.0, 250.0],
        "transaction row",
    )

    t2 = Transaction("2024-01-01T00:00:00", "DEPOSIT", None, 100, 100, 100)
    assert_eq(t2.to_row()[2], "", "transaction symbol empty")


def test_to_holdings_and_history_rows():
    a = Account(10_000)
    a.buy_shares("AAPL", 3)
    a.buy_shares("TSLA", 1)
    rows = a.to_holdings_rows()
    by_sym = {r[0]: r for r in rows}
    assert "AAPL" in by_sym and "TSLA" in by_sym, "holdings rows contain both"
    assert_eq(by_sym["AAPL"][1], 3, "AAPL qty in row")
    assert_eq(by_sym["AAPL"][2], 150.0, "AAPL price in row")
    assert_eq(by_sym["AAPL"][3], 3 * 150.0, "AAPL market value")
    assert_eq(by_sym["TSLA"][3], 1 * 700.0, "TSLA market value")
    hist_rows = a.to_transaction_rows()
    assert_eq(len(hist_rows), 3, "hist rows length")  # initial + 2 buys


def test_full_lifecycle():
    a = Account(5000)
    a.deposit_funds(5000)
    a.buy_shares("AAPL", 10)
    a.buy_shares("GOOGL", 1)
    a.sell_shares("AAPL", 4)
    a.withdraw_funds(100)

    expected_cash = (
        5000
        + 5000
        - 10 * 150.0
        - 1 * 2800.0
        + 4 * 150.0
        - 100
    )
    assert_eq(a.get_cash_balance(), expected_cash, "lifecycle cash")
    holdings = a.get_holdings()
    assert_eq(holdings.get("AAPL"), 6, "lifecycle AAPL qty")
    assert_eq(holdings.get("GOOGL"), 1, "lifecycle GOOGL qty")
    hist = a.get_transaction_history()
    assert_eq(len(hist), 6, "lifecycle history length")  # 2 deposits + 2 buys + 1 sell + 1 withdraw
    kinds = [t.kind for t in hist]
    assert_eq(kinds, ["DEPOSIT", "DEPOSIT", "BUY", "BUY", "SELL", "WITHDRAW"], "lifecycle ordering")


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passed")
    exit(0 if failed == 0 else 1)
