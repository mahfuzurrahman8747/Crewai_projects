# Design: Account Management System for Trading Simulation Platform

## Overview

A simple account management system that tracks cash, share holdings, and transactions for a simulated trading platform. The system has three layers: a `prices` helper (provided test implementation of `get_share_price`), a pure-Python `Account` class (business logic), a Gradio 6 UI, and a pytest unit-test suite. All files live flat in the project root (no subdirectories, no packages). A `uv` virtualenv is used; only `gradio` and its transitive deps are available — no extra third-party packages. `pytest` is assumed available for the test engineer via `uv pip install pytest` (a dev-only test dependency outside the app's runtime surface).

---

## File Layout

All files in the same directory:

| File | Owner | Purpose |
|---|---|---|
| `prices.py` | backend_engineer | Test implementation of `get_share_price(symbol)` |
| `account.py` | backend_engineer | Core domain logic: `Account`, `Transaction`, exceptions |
| `app.py` | frontend_engineer | Gradio 6 UI that wraps `Account` |
| `test_account.py` | test_engineer | pytest unit tests for `account.py` |

---

## Module 1 — `prices.py` (backend_engineer)

Provides the share-price lookup the rest of the system uses. The frontend and tests both import from here.

### Functions

```
def get_share_price(symbol: str) -> float
```
- **Input:** ticker symbol (case-insensitive, e.g. `"AAPL"`).
- **Output:** current per-share price as `float`.
- **Behavior:** returns fixed prices for known tickers; raises `ValueError` for unknown symbols so the system surfaces bad input.
  - `AAPL` → `150.0`
  - `TSLA` → `700.0`
  - `GOOGL` → `2800.0`
- **Note:** In a real deployment this would call an external API; the test implementation is intentionally deterministic so tests are reproducible.

---

## Module 2 — `account.py` (backend_engineer)

Pure-Python domain model. No Gradio, no I/O. Easy to unit-test.

### Exception classes

```
class AccountError(Exception): ...
class InsufficientFundsError(AccountError): ...
class InsufficientSharesError(AccountError): ...
class UnknownSymbolError(AccountError): ...
```
- `InsufficientFundsError`: raised by `withdraw_funds` and `buy_shares` when cash would go negative.
- `InsufficientSharesError`: raised by `sell_shares` when the user does not own enough of the symbol.
- `UnknownSymbolError`: raised when `prices.get_share_price` raises `ValueError` (re-raised with a friendlier message).

### `Transaction` dataclass

```
@dataclass
class Transaction:
    timestamp: str        # ISO-8601 string, generated via datetime.utcnow().isoformat()
    kind: str             # "DEPOSIT" | "WITHDRAW" | "BUY" | "SELL"
    symbol: str | None    # None for DEPOSIT / WITHDRAW
    quantity: int         # shares for BUY/SELL, units of cash for DEPOSIT/WITHDRAW
    price: float          # share price for BUY/SELL, amount for DEPOSIT/WITHDRAW
    cash_after: float     # cash balance after the transaction
```

A `to_row()` helper that returns a `list[str]` suitable for display in a `gr.Dataframe`:
```
def to_row(self) -> list[str]
```
Returns `[timestamp, kind, symbol or "", quantity, price, cash_after]`.

### `Account` class

```
class Account:
    def __init__(self, initial_deposit: float = 0.0) -> None
```
- Validates `initial_deposit >= 0`; otherwise raises `ValueError`.
- State fields (private):
  - `_cash: float` — current cash balance
  - `_holdings: dict[str, int]` — symbol → share count
  - `_transactions: list[Transaction]` — chronological log
  - `_total_deposited: float` — running total of deposits (for P/L)

#### Cash operations

```
def deposit_funds(self, amount: float) -> float
```
- Validates `amount > 0`. Appends a `Transaction(kind="DEPOSIT", quantity=amount, price=amount, ...)`. Increments `_cash` and `_total_deposited`. Returns the new cash balance.

```
def withdraw_funds(self, amount: float) -> float
```
- Validates `amount > 0`. If `_cash - amount < 0`, raises `InsufficientFundsError`. Otherwise logs a `Transaction(kind="WITHDRAW", quantity=amount, price=amount, ...)` and decrements `_cash`. Returns new cash balance.

#### Trade operations

```
def buy_shares(self, symbol: str, quantity: int) -> float
```
- Validates `quantity > 0` and `symbol` non-empty.
- Resolves price via `prices.get_share_price(symbol.upper())`. Catches `ValueError` and raises `UnknownSymbolError`.
- Computes `cost = price * quantity`. If `cost > _cash`, raises `InsufficientFundsError`.
- Appends `Transaction(kind="BUY", symbol=symbol.upper(), quantity=quantity, price=price, ...)`, decrements `_cash`, and increments `_holdings[symbol]`. Returns new cash balance.

```
def sell_shares(self, symbol: str, quantity: int) -> float
```
- Validates `quantity > 0` and `symbol` non-empty.
- Resolves price; raises `UnknownSymbolError` on bad symbol.
- If `_holdings.get(symbol.upper(), 0) < quantity`, raises `InsufficientSharesError`.
- Appends `Transaction(kind="SELL", ...)`, decrements `_holdings[symbol]`, increments `_cash` by `proceeds = price * quantity`. Returns new cash balance.

#### Reporting

```
def get_cash_balance(self) -> float
def get_holdings(self) -> dict[str, int]        # returns a copy, only symbols with quantity > 0
def calculate_portfolio_value(self) -> float    # _cash + sum(qty * get_share_price(sym) for sym in holdings)
def calculate_profit_or_loss(self) -> float     # calculate_portfolio_value() - _total_deposited
def get_transaction_history(self) -> list[Transaction]   # returns a copy
```

All reporting methods are read-only and never mutate state.

#### Convenience for the UI

```
def to_holdings_rows(self) -> list[list]
def to_transaction_rows(self) -> list[list]
```
Convert internal state to `list[list]` rows for `gr.Dataframe`. Holdings rows: `[symbol, quantity, current_price, market_value]`. Transaction rows: result of `Transaction.to_row()` for each entry.

---

## Module 3 — `app.py` (frontend_engineer)

A single-file Gradio 6 app that drives the `Account` class. Must be careful to use the **Gradio 6 API** (not the older Gradio 4/5 style).

### Gradio 6 API guidance for the frontend engineer

These are the API details that differ from earlier versions and matter for this app:

1. **App-level kwargs (theme, css, title, etc.) go on `demo.launch()`, not on `gr.Blocks(...)`.** In Gradio 6 the `Blocks` constructor no longer accepts `theme=` or `css=`. Use:
   ```
   with gr.Blocks(title="Trading Sim") as demo:
       ...
   demo.launch(theme=gr.themes.Soft(), css="...optional styles...")
   ```
   Do **not** pass `theme=` to `gr.Blocks(...)` — it will raise `TypeError` in 6.x.

2. **`show_api` on `launch()` is replaced by `footer_links`.** Use `footer_links=("api", "gradio")` (or `None` to suppress) instead of `show_api=False`.

3. **Tabs** must use a `gr.Tabs` container with `with gr.Tab("..."):` children (still supported in 6). Multiple `gr.Tab` siblings still work, but for an explicit tab strip prefer:
   ```
   with gr.Tabs():
       with gr.Tab("Account"): ...
       with gr.Tab("Trade"): ...
       with gr.Tab("Portfolio"): ...
       with gr.Tab("History"): ...
   ```

4. **`gr.on(triggers=[...], fn=..., inputs=..., outputs=...)`** is the recommended way to bind several triggers to one handler (e.g. both a button click and an `Enter` keypress on a textbox).

5. **`gr.State`** holds the current `Account` instance across callbacks. Any handler that mutates the account must list the state in `outputs=[...]` so Gradio persists the change.

6. **Component signatures (Gradio 6):**
   - `gr.Textbox(value=None, *, label=None, lines=1, interactive=None, visible=True, ...)`
   - `gr.Number(value=None, *, label=None, interactive=None, visible=True, precision=None, ...)`
   - `gr.Dropdown(choices=[...], *, label=None, value=None, interactive=None, ...)`
   - `gr.Button(value="Run", *, visible=True, interactive=True, ...)`
   - `gr.Dataframe(value=None, *, row_count=None, column_count=None, label=None, interactive=None, headers=None, ...)` — pass `headers=` to label columns; pass `value=` as `list[list]` for a static initial state.
   - `gr.Markdown(value=None, *, label=None, visible=True, ...)`
   - `gr.State(value=...)`

7. **Updates from a callback:** return a `dict` or call `gr.update(value=...)`. A returned `list[list]` for a `gr.Dataframe` updates the table.

8. **Error feedback to the user:** catch domain exceptions in each callback and return user-friendly `gr.Markdown` / `gr.Textbox` messages rather than letting them bubble.

### Layout

```
with gr.Blocks(title="Trading Sim — Account Manager") as demo:
    account_state = gr.State(value=None)        # holds the Account instance

    gr.Markdown("# Trading Simulation — Account Manager")

    with gr.Tabs():
        # ---- Account tab ----
        with gr.Tab("Account"):
            initial_deposit = gr.Number(label="Initial deposit", value=10000, precision=2)
            create_btn      = gr.Button("Create / Reset Account", variant="primary")
            deposit_amt     = gr.Number(label="Deposit amount", precision=2)
            deposit_btn     = gr.Button("Deposit")
            withdraw_amt    = gr.Number(label="Withdraw amount", precision=2)
            withdraw_btn    = gr.Button("Withdraw")
            account_status  = gr.Markdown()      # shows cash balance, errors

        # ---- Trade tab ----
        with gr.Tab("Trade"):
            symbol_dd   = gr.Dropdown(choices=["AAPL", "TSLA", "GOOGL"], label="Symbol")
            qty_buy     = gr.Number(label="Quantity to buy", precision=0)
            buy_btn     = gr.Button("Buy")
            qty_sell    = gr.Number(label="Quantity to sell", precision=0)
            sell_btn    = gr.Button("Sell")
            trade_status= gr.Markdown()

        # ---- Portfolio tab ----
        with gr.Tab("Portfolio"):
            refresh_btn = gr.Button("Refresh")
            portfolio_summary = gr.Markdown()    # total value, P/L
            holdings_table    = gr.Dataframe(
                headers=["Symbol", "Quantity", "Current Price", "Market Value"],
                row_count=(0, "dynamic"),
                interactive=False,
            )

        # ---- History tab ----
        with gr.Tab("History"):
            history_btn      = gr.Button("Refresh")
            history_table    = gr.Dataframe(
                headers=["Timestamp", "Kind", "Symbol", "Quantity", "Price", "Cash After"],
                row_count=(0, "dynamic"),
                interactive=False,
            )
```

### Callback functions (signatures only — frontend engineer writes the bodies)

```
def create_account(initial_deposit: float, state) -> tuple[Account, str]
    # if state is None or initial_deposit < 0, build a new Account(initial_deposit)
    # returns (new_state, markdown status)

def do_deposit(amount: float, state) -> tuple[Account, str]
    # calls state.deposit_funds(amount); catches AccountError

def do_withdraw(amount: float, state) -> tuple[Account, str]
    # calls state.withdraw_funds(amount); catches InsufficientFundsError

def do_buy(symbol: str, quantity: int, state) -> tuple[Account, str]
    # catches InsufficientFundsError, UnknownSymbolError

def do_sell(symbol: str, quantity: int, state) -> tuple[Account, str]
    # catches InsufficientSharesError, UnknownSymbolError

def refresh_portfolio(state) -> tuple[str, list[list]]
    # returns (markdown summary, holdings rows) via state.calculate_portfolio_value(),
    # state.calculate_profit_or_loss(), state.get_holdings(), state.to_holdings_rows()

def refresh_history(state) -> list[list]
    # returns state.to_transaction_rows()
```

### Event wiring (Gradio 6)

```
create_btn.click(create_account, inputs=[initial_deposit, account_state], outputs=[account_state, account_status])
gr.on(triggers=[deposit_btn.click], fn=do_deposit, inputs=[deposit_amt, account_state], outputs=[account_state, account_status])
gr.on(triggers=[withdraw_btn.click], fn=do_withdraw, inputs=[withdraw_amt, account_state], outputs=[account_state, account_status])
gr.on(triggers=[buy_btn.click], fn=do_buy, inputs=[symbol_dd, qty_buy, account_state], outputs=[account_state, trade_status])
gr.on(triggers=[sell_btn.click], fn=do_sell, inputs=[symbol_dd, qty_sell, account_state], outputs=[account_state, trade_status])
refresh_btn.click(refresh_portfolio, inputs=[account_state], outputs=[portfolio_summary, holdings_table])
history_btn.click(refresh_history, inputs=[account_state], outputs=[history_table])

demo.launch(theme=gr.themes.Soft(), footer_links=("gradio",))
```

> ⚠️ Do not put `theme=` inside `gr.Blocks(...)` — in Gradio 6 it belongs on `launch()`.

---

## Module 4 — `test_account.py` (test_engineer)

A pytest suite that exercises every `Account` method, every error path, and the public reporting surface. Uses `monkeypatch` to stub `prices.get_share_price` so tests are independent of the hard-coded values and can pin known prices.

### Test cases (signatures only)

```
def test_create_account_with_initial_deposit()
def test_create_account_rejects_negative_deposit()   # expect ValueError
def test_deposit_increases_cash_and_logs_transaction()
def test_deposit_rejects_non_positive_amount()       # 0, -1
def test_withdraw_decreases_cash()
def test_withdraw_rejects_amount_exceeding_balance() # expect InsufficientFundsError
def test_withdraw_rejects_non_positive_amount()
def test_buy_shares_decreases_cash_and_increases_holdings()
def test_buy_shares_rejects_insufficient_cash()      # expect InsufficientFundsError
def test_buy_shares_rejects_unknown_symbol()         # expect UnknownSymbolError
def test_buy_shares_rejects_non_positive_quantity()
def test_sell_shares_increases_cash_and_decreases_holdings()
def test_sell_shares_rejects_insufficient_shares()   # expect InsufficientSharesError
def test_sell_shares_rejects_unknown_symbol()        # expect UnknownSymbolError
def test_sell_shares_rejects_non_positive_quantity()
def test_get_holdings_omits_zero_quantities()
def test_calculate_portfolio_value_uses_current_prices(monkeypatch)
def test_calculate_profit_or_loss_positive_and_negative(monkeypatch)
def test_get_transaction_history_is_chronological_and_complete()
def test_full_lifecycle_deposit_buy_sell_withdraw(monkeypatch)
```

A `conftest.py` (optional) can provide a `make_account` fixture and a `pin_prices(monkeypatch, prices_map)` helper that replaces `prices.get_share_price` with a dict-backed stub so each test controls prices exactly. If a conftest is added, place it in the same directory (still flat).

### Suggested `pin_prices` fixture signature

```
@pytest.fixture
def pin_prices(monkeypatch):
    def _pin(mapping: dict[str, float]):
        monkeypatch.setattr(
            "prices.get_share_price",
            lambda symbol: (_ for _ in ()).throw(KeyError(symbol))
            if symbol.upper() not in mapping
            else float(mapping[symbol.upper()]),
        )
    return _pin
```

(Implementation may be written however the test engineer prefers; the above is a sketch.)

---

## Work Assignments

### backend_engineer
- Implement `prices.py` (fixed prices for AAPL/TSLA/GOOGL, raise `ValueError` for unknown).
- Implement `account.py`: exceptions, `Transaction` dataclass, full `Account` class with all methods listed above, plus `to_holdings_rows` / `to_transaction_rows` helpers.
- **Acceptance:** `from account import Account; Account(1000).deposit_funds(500).withdraw_funds(200)` works; bad inputs raise the documented exceptions; `get_transaction_history()` returns every operation in order.

### frontend_engineer
- Implement `app.py` using **Gradio 6** (verify version with `python -c "import gradio; print(gradio.__version__)"`; must be `>=6.0`).
- Use the API guidance in the design: `theme=` on `launch()`, `gr.Tabs`/`gr.Tab` containers, `gr.on` for multi-trigger handlers, `gr.State` for the current `Account`, `gr.Dataframe` with explicit `headers=`.
- Catch `AccountError` subclasses in callbacks and surface readable messages via `gr.Markdown`.
- **Acceptance:** `uv run app.py` opens the UI, an account can be created, funds deposited/withdrawn, shares bought/sold, portfolio and history tabs reflect the state.

### test_engineer
- Implement `test_account.py` covering every method and every error path listed above.
- Use `monkeypatch` (no extra packages) to stub `prices.get_share_price` so tests are deterministic and independent of the hard-coded values.
- **Acceptance:** `uv run pytest` exits 0 with full coverage of `account.py`'s public methods and the three custom exceptions.

---

## Open Questions / Assumptions

- The spec says "report the holdings … at any point in time" and "profit or loss … at any point in time." The `Account` class as designed reports the **current** state, not arbitrary historical snapshots. If historical reconstruction is required, the transaction log can replay state at any past timestamp — but the current scope (per the requirements list) only requires *current* reporting, so we deliver that and keep the transaction log rich enough to support a future point-in-time view.
- `get_share_price` is called with case-insensitive symbols; `Account` normalises to upper case internally.
- `precision=0` is used for share quantities to enforce integer inputs in the UI; the backend itself accepts any `int` and rejects `<= 0`.