# Trading Agent

Pure LLM-based trader that uses Claude/GPT/Grok to analyze markets and execute trades.

## What It Does
- Analyzes token data using AI
- Makes buy/sell decisions
- Manages portfolio allocation
- No hardcoded rules, pure AI reasoning

## Usage
```bash
python src/agents/trading_agent.py
```

## Configuration
Edit top of `trading_agent.py`:
```python
AI_MODEL_TYPE = 'claude'  # or 'openai', 'xai', 'groq'
AI_MODEL_NAME = None      # or specific model
```

## Key Functions
- `analyze_market_data()` - AI analyzes token and decides action
- `allocate_portfolio()` - AI allocates USD across opportunities
- `execute_trades()` - Executes the AI decisions

## Output
Saves decisions to `src/data/trading_agent/[date]/`
## Changelog: Safety Fixes (2026-10-07)

Review of `src/agents/trading_agent.py` and the Solana entry path in `src/nice_funcs.py`.

### `src/agents/trading_agent.py`
| Fix | Before | After |
|-----|--------|-------|
| Stale signals | `recommendations_df` accumulated across cycles, so old BUY/SELL rows were re-executed | Reset at the start of every `run_trading_cycle` |
| Unknown actions | Anything that wasn't SELL/NOTHING fell into the BUY branch | Single-model output is normalized to BUY/SELL/NOTHING (unknown = NOTHING); `handle_exits` also treats unknown actions as NOTHING |
| Swarm ties | `max()` picked the first key on a tie, so BUY won | A tie between actions = NOTHING |
| Swarm vote parsing | `"BUY" in text` (substring, "Don't Buy" counted as BUY) | Answer must start with BUY/SELL, otherwise Do Nothing |
| Zero balance | `get_account_balance()` returning 0 led to entries of size 0 | Entry/short is skipped when balance <= 0 |
| `CASH_PERCENTAGE` | Undefined (`NameError` in `allocate_portfolio`) | Defined in the config block (20) |
| Strategy signals | Written as a DataFrame column and never read by the swarm | Passed as an argument to `analyze_market_data` and included in the prompt |
| Confidence parsing | All digits in the line concatenated ("75% (3 indicators)" -> 753) | Regex for `NN%`, fallback to first number, capped at 100 |
| Monitor failure | A failed `monitor_position_pnl` printed "Position closed" and instantly re-ran the swarm | Waits `SLEEP_BETWEEN_RUNS_MINUTES` and retries |

### `src/nice_funcs.py` (`ai_entry`, Solana)
- Now returns `True` when the position reaches the target (or is already there) and `False` on critical error or when it gives up. Previously it always returned `None`, so callers saw every entry as failed. Other callers (`copybot_agent`, `strategy_agent`, `exchange_manager`) are compatible.
- Added a safety cap of 15 buy loops (`max_entry_loops`) so a failing or lagging position update can no longer cause endless purchases.

### Solana stop loss / take profit (follow-up)
- `monitor_position_pnl` now applies `STOP_LOSS_PERCENTAGE` / `TAKE_PROFIT_PERCENTAGE` on Solana. P&L = current USD value of the position / USD value at entry - 1 (uses `get_token_balance_usd`, no extra API calls).
- The entry value is stored in `ENTRY_VALUE_USD` right after a confirmed entry. If the agent restarts with a position already open, the baseline is the value when monitoring starts, so P&L counts from that moment.
- On a hit it calls `chunk_kill` and verifies the balance is gone (> $0.10 left = returns `False`, and `main()` waits and retries).
- Limitation: the P&L is based on the USD value reported by the wallet fetch. If that call fails and returns 0, the monitor treats the position as closed (pre-existing behavior of `get_token_balance_usd`).
- `ai_entry` messages no longer claim a "max 30% of usd_size" cap that never existed.

### HyperLiquid compatibility (follow-up)
`nice_funcs_hyperliquid.py` has a different API from Aster (`get_position` needs an `account` and returns a tuple; no `chunk_kill`, `limit_sell` or `limit_buy`). Instead of changing that module, `trading_agent.py` got a small adapter layer (next to `ENTRY_VALUE_USD`):
- `get_futures_position(token)`: unified position dict for Aster/HyperLiquid (`position_amount`, `entry_price`, `mark_price`, `pnl`, `pnl_percentage`, `is_long`).
- `get_position_usd(token)`: USD value of the position on any exchange.
- `close_position_full(token)`: `chunk_kill` on Solana/Aster, `kill_switch` (reduce-only IOC) on HyperLiquid.
- `close_futures_position(token, position, size)`: used by stop loss / take profit (`kill_switch` on HyperLiquid, limit orders on Aster).
- Shorts on HyperLiquid now fail loudly if `open_short` returns no order (it swallows its own errors and returns `None`).
- `pnl_percentage` on HyperLiquid is `returnOnEquity` (return on margin, so it includes leverage). Stop loss / take profit at 5% therefore triggers at about a 5%/leverage price move.
- Not tested against the real HyperLiquid API. Run first with a very small `MAX_POSITION_PERCENTAGE`; HyperLiquid also enforces a $10 minimum order (`market_buy` bumps smaller orders to $11).

### Long/short exits (follow-up)
`handle_exits` now reads the direction of the open position (`get_futures_position`, Aster/HyperLiquid) instead of treating every position as a long:

| Position | BUY | SELL | NOTHING |
|----------|-----|------|---------|
| LONG | keep | close | keep |
| SHORT | close | keep | keep |

After a short is closed by a BUY signal, a new long is only opened in the next cycle if the signal is still BUY. With `LONG_ONLY = True` (and on Solana) nothing changes.

### HyperLiquid Unified Account (follow-up)
On a Unified Account the collateral is the spot USDC balance and the perps `accountValue` / `withdrawable` stay at 0, so the agent read a balance of 0. `get_account_balance` now falls back to the spot USDC total when the perps value is 0. Limitation: with an open perps position and a unified account, the spot USDC total includes the margin on hold.

Note: HyperLiquid enforces a $10 minimum order and `market_buy` raises smaller orders to $11. On small accounts this overrides `MAX_POSITION_PERCENTAGE` (e.g. 30% of $12.41 = $3.72, but the order sent is $11).

### Known issues NOT fixed
- Solana: while a position is open, `monitor_position_pnl` blocks the loop, so no new AI analysis (and no SELL signals) happen until the position closes by stop loss / take profit.
- HyperLiquid: `ai_entry` and `open_short` in `nice_funcs_hyperliquid.py` treat any non-`None` order response as success, even if the exchange rejected the order. The agent verifies the position afterwards on BUY entries, but not on shorts.
- `ai_entry` (Solana) takes `max_usd_order_size`, `slippage`, `orders_per_open` and `tx_sleep` from `src/config.py`, not from the top of `trading_agent.py`. The agent's own `max_usd_order_size` and `slippage` only affect `chunk_kill`.
- `ai_entry` has no cap of its own: the size is decided by the caller (`calculate_position_size`, up to `MAX_POSITION_PERCENTAGE` of the USDC balance, bought in $3 chunks).
- Unrelated to this agent, in `nice_funcs.py`: `pnl_close` uses `stop_loss_percentage` (config defines `stop_loss_perctentage`, typo) and `close_all_positions` uses an undefined `dont_trade_list`.
- `SOL_ADDRESS` ends in `...1111`; the real wrapped SOL mint ends in `...2`.
- Comments / docstring line references at the top of `trading_agent.py` are outdated, and the FART/housecoin ACTIVE/DISABLED labels in `MONITORED_TOKENS` are swapped.
