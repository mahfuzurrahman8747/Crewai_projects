"""Gradio 6 frontend for the Trading Simulation account management system.

A professional, polished single-file UI built with Gradio 6 that drives the
:class:`account.Account` backend. Layout: four tabs -- Account, Trade,
Portfolio, History. Domain exceptions are caught and surfaced as friendly
markdown messages rather than being allowed to bubble up.

Gradio 6 specifics:
    * ``theme=`` and ``css=`` kwargs go on ``demo.launch(...)``, not on
      ``gr.Blocks(...)``.
    * ``footer_links=...`` replaces ``show_api=...``.
    * ``gr.on(triggers=[...], fn=..., ...)`` binds multiple triggers to
      one handler.
    * ``gr.State`` holds the current ``Account`` across callbacks.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import gradio as gr

from account import (
    Account,
    AccountError,
    InsufficientFundsError,
    InsufficientSharesError,
    UnknownSymbolError,
)


# ---------------------------------------------------------------------------
# Colour palette (works in both light and dark mode)
# ---------------------------------------------------------------------------
# Primary  : #ecad0a  (warm amber)
# Secondary: #209dd7  (sky blue)
# Accent   : #753991  (royal purple)
# ---------------------------------------------------------------------------
_PALETTE_CSS = """
:root {
    --ts-primary:   #ecad0a;
    --ts-secondary: #209dd7;
    --ts-accent:    #753991;
}

/* Brand the primary buttons */
.gradio-container .primary {
    background: var(--ts-primary) !important;
    color: #1a1a1a !important;
    border: none !important;
}
.gradio-container .primary:hover {
    background: #d99a00 !important;
}

/* Tab strip -- use secondary blue as the selected indicator */
.tabitem.selected {
    border-top-color: var(--ts-secondary) !important;
    color: var(--ts-secondary) !important;
}

/* Side panel / accordion titles */
.section-title, label > .label-text {
    color: var(--ts-accent) !important;
    font-weight: 600 !important;
}

/* Status boxes: small accent line on the left */
.ts-status {
    border-left: 4px solid var(--ts-secondary) !important;
    padding: 8px 12px !important;
    border-radius: 4px !important;
    background: rgba(32, 157, 215, 0.06) !important;
}
.ts-status.error {
    border-left-color: #c0392b !important;
    background: rgba(192, 57, 43, 0.08) !important;
}
.ts-status.success {
    border-left-color: #27ae60 !important;
    background: rgba(39, 174, 96, 0.08) !important;
}
.ts-status.info {
    border-left-color: var(--ts-primary) !important;
    background: rgba(236, 173, 10, 0.08) !important;
}

/* Tighter spacing inside the Row containers */
.gr-row { gap: 12px !important; }

/* Bring the main heading into the palette */
#ts-header h1 {
    color: var(--ts-accent) !important;
    border-bottom: 3px solid var(--ts-primary);
    padding-bottom: 8px;
}

/* Dark mode tweaks: lift contrast a touch */
.dark .ts-status { background: rgba(32, 157, 215, 0.18) !important; }
.dark .ts-status.error { background: rgba(192, 57, 43, 0.22) !important; }
.dark .ts-status.success { background: rgba(39, 174, 96, 0.22) !important; }
.dark .ts-status.info { background: rgba(236, 173, 10, 0.22) !important; }
"""


# ---------------------------------------------------------------------------
# Callback helpers
# ---------------------------------------------------------------------------

def _fmt_money(value) -> str:
    """Format a float as a fixed-precision money string."""
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _ensure_account(state: Optional[Account]) -> Tuple[Account, bool]:
    """Return a valid ``Account`` and a ``created`` flag."""
    if state is None:
        return Account(0.0), True
    return state, False


def _format_account_status(account: Account) -> str:
    """Return a short markdown summary of the account's cash & P/L state."""
    cash = _fmt_money(account.get_cash_balance())
    portfolio = _fmt_money(account.calculate_portfolio_value())
    pl = account.calculate_profit_or_loss()
    pl_str = _fmt_money(pl)
    pl_marker = "[+]" if pl >= 0 else "[-]"
    return (
        f"**Cash balance:** {cash}  \n"
        f"**Portfolio value:** {portfolio}  \n"
        f"**Profit / Loss:** {pl_marker} {pl_str}"
    )


def _format_status_md(message: str, level: str = "info") -> str:
    """Wrap a status message in a styled markdown block.

    The CSS classes ``ts-status``, ``ts-status.error``, ``ts-status.success``
    and ``ts-status.info`` are defined in ``_PALETTE_CSS``.
    """
    if level in {"error", "success", "info"}:
        cls = f"ts-status {level}"
    else:
        cls = "ts-status"
    return f'<div class="{cls}">{message}</div>'


# ---------------------------------------------------------------------------
# Account tab callbacks
# ---------------------------------------------------------------------------

def create_account(initial_deposit, state: Optional[Account]):
    """Create / reset the ``Account`` with the given initial deposit."""
    try:
        # Re-creating always overwrites -- "reset" semantics are useful for
        # the UI and keep the demo approachable.
        new_account = Account(float(initial_deposit))
    except (TypeError, ValueError) as exc:
        placeholder, _ = _ensure_account(state)
        msg = _format_status_md(
            f"[ERROR] Could not create account: {exc}", level="error"
        )
        return placeholder, msg

    msg = _format_status_md(
        "[OK] Account created successfully. Ready to trade.",
        level="success",
    )
    msg += "\n\n" + _format_account_status(new_account)
    return new_account, msg


def do_deposit(amount, state: Optional[Account]):
    """Deposit funds into the account."""
    account, _ = _ensure_account(state)
    if amount is None:
        return account, _format_status_md(
            "[WARN] Enter a deposit amount.", level="error"
        )

    try:
        account.deposit_funds(float(amount))
    except ValueError as exc:
        return account, _format_status_md(f"[ERROR] {exc}", level="error")
    except InsufficientFundsError as exc:
        return account, _format_status_md(f"[ERROR] {exc}", level="error")
    except AccountError as exc:
        return account, _format_status_md(f"[ERROR] {exc}", level="error")

    msg = _format_status_md(
        f"[OK] Deposited {_fmt_money(amount)}.", level="success"
    )
    msg += "\n\n" + _format_account_status(account)
    return account, msg


def do_withdraw(amount, state: Optional[Account]):
    """Withdraw funds from the account."""
    account, _ = _ensure_account(state)
    if amount is None:
        return account, _format_status_md(
            "[WARN] Enter a withdrawal amount.", level="error"
        )

    try:
        account.withdraw_funds(float(amount))
    except ValueError as exc:
        return account, _format_status_md(f"[ERROR] {exc}", level="error")
    except InsufficientFundsError as exc:
        return account, _format_status_md(f"[ERROR] {exc}", level="error")
    except AccountError as exc:
        return account, _format_status_md(f"[ERROR] {exc}", level="error")

    msg = _format_status_md(
        f"[OK] Withdrew {_fmt_money(amount)}.", level="success"
    )
    msg += "\n\n" + _format_account_status(account)
    return account, msg


# ---------------------------------------------------------------------------
# Trade tab callbacks
# ---------------------------------------------------------------------------

def do_buy(symbol, quantity, state: Optional[Account]):
    """Buy ``quantity`` shares of ``symbol``."""
    account, _ = _ensure_account(state)

    if not symbol:
        return account, _format_status_md(
            "[WARN] Pick a symbol first.", level="error"
        )
    if quantity is None:
        return account, _format_status_md(
            "[WARN] Enter a quantity.", level="error"
        )
    try:
        qty = int(quantity)
    except (TypeError, ValueError):
        return account, _format_status_md(
            "[ERROR] Quantity must be a whole number.", level="error"
        )

    try:
        account.buy_shares(symbol, qty)
    except ValueError as exc:
        return account, _format_status_md(f"[ERROR] {exc}", level="error")
    except UnknownSymbolError as exc:
        return account, _format_status_md(f"[ERROR] {exc}", level="error")
    except InsufficientFundsError as exc:
        return account, _format_status_md(f"[ERROR] {exc}", level="error")
    except AccountError as exc:
        return account, _format_status_md(f"[ERROR] {exc}", level="error")

    msg = _format_status_md(
        f"[OK] Bought {qty} x **{symbol}**.", level="success"
    )
    msg += "\n\n" + _format_account_status(account)
    return account, msg


def do_sell(symbol, quantity, state: Optional[Account]):
    """Sell ``quantity`` shares of ``symbol``."""
    account, _ = _ensure_account(state)

    if not symbol:
        return account, _format_status_md(
            "[WARN] Pick a symbol first.", level="error"
        )
    if quantity is None:
        return account, _format_status_md(
            "[WARN] Enter a quantity.", level="error"
        )
    try:
        qty = int(quantity)
    except (TypeError, ValueError):
        return account, _format_status_md(
            "[ERROR] Quantity must be a whole number.", level="error"
        )

    try:
        account.sell_shares(symbol, qty)
    except ValueError as exc:
        return account, _format_status_md(f"[ERROR] {exc}", level="error")
    except UnknownSymbolError as exc:
        return account, _format_status_md(f"[ERROR] {exc}", level="error")
    except InsufficientSharesError as exc:
        return account, _format_status_md(f"[ERROR] {exc}", level="error")
    except InsufficientFundsError as exc:
        return account, _format_status_md(f"[ERROR] {exc}", level="error")
    except AccountError as exc:
        return account, _format_status_md(f"[ERROR] {exc}", level="error")

    msg = _format_status_md(
        f"[OK] Sold {qty} x **{symbol}**.", level="success"
    )
    msg += "\n\n" + _format_account_status(account)
    return account, msg


# ---------------------------------------------------------------------------
# Portfolio tab callbacks
# ---------------------------------------------------------------------------

def _price_for(symbol: str) -> float:
    """Look up a price via the shared price service."""
    from prices import get_share_price
    try:
        return get_share_price(symbol)
    except ValueError:
        return 0.0


def refresh_portfolio(state: Optional[Account]):
    """Return the markdown summary + holdings rows for the portfolio tab."""
    if state is None:
        empty_md = _format_status_md(
            "[INFO] No account yet. Create one on the **Account** tab.",
            level="error",
        )
        return empty_md, []

    cash = _fmt_money(state.get_cash_balance())
    portfolio = _fmt_money(state.calculate_portfolio_value())
    pl = state.calculate_profit_or_loss()
    pl_str = _fmt_money(pl)
    pl_marker = "[+]" if pl >= 0 else "[-]"

    holdings = state.get_holdings()
    if holdings:
        rows_md = "\n".join(
            f"- **{sym}** -- {qty} shares @ "
            f"{_fmt_money(_price_for(sym))} "
            f"(value {_fmt_money(qty * _price_for(sym))})"
            for sym, qty in holdings.items()
        )
        holdings_md = "### Holdings\n" + rows_md
    else:
        holdings_md = (
            "### Holdings\n"
            "_None yet -- buy some shares on the **Trade** tab._"
        )

    summary = (
        "### Summary\n"
        f"- **Cash balance:** {cash}\n"
        f"- **Portfolio value:** {portfolio}\n"
        f"- **Profit / Loss:** {pl_marker} {pl_str}\n\n"
        f"{holdings_md}"
    )

    return summary, state.to_holdings_rows()


# ---------------------------------------------------------------------------
# History tab callbacks
# ---------------------------------------------------------------------------

def refresh_history(state: Optional[Account]):
    """Return the transaction rows for the history tab."""
    if state is None:
        return []
    return state.to_transaction_rows()


# ---------------------------------------------------------------------------
# UI assembly
# ---------------------------------------------------------------------------

def build_demo() -> gr.Blocks:
    """Construct (but do not launch) the Gradio 6 demo."""
    with gr.Blocks(
        title="Trading Sim -- Account Manager",
    ) as demo:
        # Single shared account state across all tabs.
        account_state = gr.State(value=None)

        gr.Markdown(
            "# Trading Simulation -- Account Manager",
            elem_id="ts-header",
        )
        gr.Markdown(
            "Create an account, deposit or withdraw cash, buy and sell shares, "
            "and watch your portfolio value and profit/loss update in real "
            "time. Share prices are sourced from the test implementation of "
            "`get_share_price` (AAPL, TSLA, GOOGL)."
        )

        with gr.Tabs():
            # -------------------------------------------------- Account tab
            with gr.Tab("Account"):
                gr.Markdown("### Open an account")
                with gr.Row():
                    initial_deposit = gr.Number(
                        label="Initial deposit ($)",
                        value=10000,
                        precision=2,
                        minimum=0,
                    )
                    create_btn = gr.Button(
                        "Create / Reset Account",
                        variant="primary",
                    )
                account_status = gr.Markdown(
                    value=_format_status_md(
                        "[INFO] Click *Create / Reset Account* to get started."
                    )
                )

                gr.Markdown("### Cash operations")
                with gr.Row():
                    deposit_amt = gr.Number(
                        label="Deposit amount ($)",
                        precision=2,
                        minimum=0,
                    )
                    deposit_btn = gr.Button("Deposit", variant="primary")
                with gr.Row():
                    withdraw_amt = gr.Number(
                        label="Withdraw amount ($)",
                        precision=2,
                        minimum=0,
                    )
                    withdraw_btn = gr.Button("Withdraw", variant="primary")

                gr.on(
                    triggers=[create_btn.click],
                    fn=create_account,
                    inputs=[initial_deposit, account_state],
                    outputs=[account_state, account_status],
                )
                gr.on(
                    triggers=[deposit_btn.click],
                    fn=do_deposit,
                    inputs=[deposit_amt, account_state],
                    outputs=[account_state, account_status],
                )
                gr.on(
                    triggers=[withdraw_btn.click],
                    fn=do_withdraw,
                    inputs=[withdraw_amt, account_state],
                    outputs=[account_state, account_status],
                )

            # -------------------------------------------------- Trade tab
            with gr.Tab("Trade"):
                gr.Markdown(
                    "### Place a trade\n"
                    "Select a symbol and the number of shares to buy or sell. "
                    "Quantities must be positive whole numbers."
                )
                symbol_dd = gr.Dropdown(
                    choices=["AAPL", "TSLA", "GOOGL"],
                    label="Symbol",
                    value="AAPL",
                )

                gr.Markdown("#### Buy")
                with gr.Row():
                    qty_buy = gr.Number(
                        label="Quantity to buy",
                        precision=0,
                        minimum=0,
                    )
                    buy_btn = gr.Button("Buy", variant="primary")

                gr.Markdown("#### Sell")
                with gr.Row():
                    qty_sell = gr.Number(
                        label="Quantity to sell",
                        precision=0,
                        minimum=0,
                    )
                    sell_btn = gr.Button("Sell")

                trade_status = gr.Markdown(
                    value=_format_status_md(
                        "[INFO] Pick a symbol, enter a quantity, then choose Buy or Sell."
                    )
                )

                gr.on(
                    triggers=[buy_btn.click],
                    fn=do_buy,
                    inputs=[symbol_dd, qty_buy, account_state],
                    outputs=[account_state, trade_status],
                )
                gr.on(
                    triggers=[sell_btn.click],
                    fn=do_sell,
                    inputs=[symbol_dd, qty_sell, account_state],
                    outputs=[account_state, trade_status],
                )

            # ------------------------------------------------- Portfolio tab
            with gr.Tab("Portfolio"):
                gr.Markdown(
                    "### Current portfolio\n"
                    "Click **Refresh** to recompute using the latest share prices."
                )
                refresh_btn = gr.Button("Refresh", variant="primary")
                portfolio_summary = gr.Markdown(
                    value=_format_status_md(
                        "[INFO] Click *Refresh* to see your portfolio summary."
                    )
                )
                holdings_table = gr.Dataframe(
                    headers=["Symbol", "Quantity", "Current Price", "Market Value"],
                    datatype=["str", "number", "number", "number"],
                    row_count=(0, "dynamic"),
                    col_count=(4, "fixed"),
                    interactive=False,
                    label="Holdings",
                )

                refresh_btn.click(
                    fn=refresh_portfolio,
                    inputs=[account_state],
                    outputs=[portfolio_summary, holdings_table],
                )

            # -------------------------------------------------- History tab
            with gr.Tab("History"):
                gr.Markdown(
                    "### Transaction history\n"
                    "Every deposit, withdrawal, buy and sell, with the running "
                    "cash balance afterwards."
                )
                history_btn = gr.Button("Refresh", variant="primary")
                history_table = gr.Dataframe(
                    headers=["Timestamp", "Kind", "Symbol", "Quantity", "Price", "Cash After"],
                    datatype=["str", "str", "str", "number", "number", "number"],
                    row_count=(0, "dynamic"),
                    col_count=(6, "fixed"),
                    interactive=False,
                    label="Transactions",
                )

                history_btn.click(
                    fn=refresh_history,
                    inputs=[account_state],
                    outputs=[history_table],
                )

    return demo


# Module-level demo so ``demo.launch()`` is just one line for the end user.
demo: gr.Blocks = build_demo()


if __name__ == "__main__":
    # Gradio 6: app-level kwargs go on launch(), NOT on gr.Blocks().
    demo.launch(
        theme=gr.themes.Soft(primary_hue="amber", secondary_hue="blue"),
        css=_PALETTE_CSS,
        footer_links=("gradio",),
    )
