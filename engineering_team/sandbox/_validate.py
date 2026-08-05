"""Validation script: import ``app`` and confirm ``gr.Blocks`` constructs.

Per the task requirements this script must NOT call ``.launch()`` -- it only
imports the module and inspects / instantiates the demo object so we can be
sure the UI builds without error.
"""

from __future__ import annotations

import importlib
import sys
import traceback

import app as _app_module
import gradio as gr


def main() -> int:
    # --- 1. The module imported cleanly and exposes the demo ------------
    demo = getattr(_app_module, "demo", None)
    assert demo is not None, "app.demo is missing"
    assert isinstance(demo, gr.Blocks), (
        f"app.demo should be a gr.Blocks, got {type(demo).__name__}"
    )

    # --- 2. Re-run the factory directly to double-check -----------------
    demo2 = _app_module.build_demo()
    assert isinstance(demo2, gr.Blocks), "build_demo() did not return gr.Blocks"

    # --- 3. The backend can be driven end-to-end ------------------------
    from account import (
        Account,
        InsufficientFundsError,
        InsufficientSharesError,
        UnknownSymbolError,
    )

    acct = Account(5000)
    acct.deposit_funds(1500)
    acct.buy_shares("AAPL", 10)
    acct.sell_shares("AAPL", 3)
    assert acct.get_cash_balance() > 0
    assert acct.get_holdings() == {"AAPL": 7}
    assert len(acct.get_transaction_history()) == 4
    assert isinstance(acct.calculate_portfolio_value(), float)
    assert isinstance(acct.calculate_profit_or_loss(), float)

    # Domain rules
    try:
        acct.withdraw_funds(10_000_000)
    except InsufficientFundsError:
        pass
    else:
        raise AssertionError("expected InsufficientFundsError")

    try:
        acct.sell_shares("AAPL", 999)
    except InsufficientSharesError:
        pass
    else:
        raise AssertionError("expected InsufficientSharesError")

    try:
        acct.buy_shares("MSFT", 1)
    except UnknownSymbolError:
        pass
    else:
        raise AssertionError("expected UnknownSymbolError")

    # Tabular helpers
    assert acct.to_holdings_rows(), "to_holdings_rows should not be empty"
    assert len(acct.to_transaction_rows()) == 4

    print("[OK] app.py imported successfully")
    print("[OK] demo is a gr.Blocks:", type(demo).__name__)
    print("[OK] build_demo() returns gr.Blocks")
    print("[OK] end-to-end backend exercise passed")
    print("[OK] All domain exception paths raised as expected")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
