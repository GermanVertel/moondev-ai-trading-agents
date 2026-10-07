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

## Registro de cambios: correcciones de seguridad (2026-10-07)

Revisión de `src/agents/trading_agent.py` y de la ruta de entrada de Solana en `src/nice_funcs.py`.

### `src/agents/trading_agent.py`
| Corrección | Antes | Después |
|------------|-------|---------|
| Señales viejas | `recommendations_df` se acumulaba entre ciclos y se reejecutaban filas BUY/SELL antiguas | Se reinicia al comienzo de cada `run_trading_cycle` |
| Acciones desconocidas | Todo lo que no fuera SELL/NOTHING caía en la rama BUY | La salida del modo single se normaliza a BUY/SELL/NOTHING (desconocido = NOTHING); `handle_exits` también trata las desconocidas como NOTHING |
| Empates del swarm | `max()` devolvía la primera clave en un empate, así que ganaba BUY | Un empate entre acciones = NOTHING |
| Parseo de votos del swarm | `"BUY" in texto` (subcadena: "Don't Buy" contaba como BUY) | La respuesta debe empezar por BUY/SELL; si no, es Do Nothing |
| Balance en 0 | Si `get_account_balance()` devolvía 0 se hacían entradas de tamaño 0 | Se omite la entrada o el short cuando el balance es <= 0 |
| `CASH_PERCENTAGE` | No estaba definido (`NameError` en `allocate_portfolio`) | Definido en el bloque de configuración (20) |
| Señales de estrategia | Se escribían como columna del DataFrame y el swarm nunca las leía | Se pasan como argumento a `analyze_market_data` y se incluyen en el prompt |
| Parseo de confianza | Concatenaba todos los dígitos de la línea ("75% (3 indicators)" daba 753) | Regex para `NN%`, con respaldo al primer número y tope de 100 |
| Fallo del monitor | Un `monitor_position_pnl` fallido imprimía "Position closed" y relanzaba el swarm al instante | Espera `SLEEP_BETWEEN_RUNS_MINUTES` y reintenta |

### `src/nice_funcs.py` (`ai_entry`, Solana)
- Ahora devuelve `True` cuando la posición alcanza el objetivo (o ya estaba en él) y `False` ante un error crítico o cuando se rinde. Antes devolvía siempre `None`, así que quien la llamaba veía todas las entradas como fallidas. Los otros llamadores (`copybot_agent`, `strategy_agent`, `exchange_manager`) siguen siendo compatibles.
- Se añadió un tope de seguridad de 15 vueltas de compra (`max_entry_loops`), para que una actualización de posición que falle o se retrase ya no pueda provocar compras sin fin.

### Stop loss y take profit en Solana
- `monitor_position_pnl` aplica ahora `STOP_LOSS_PERCENTAGE` y `TAKE_PROFIT_PERCENTAGE` en Solana. P&L = valor actual en USD de la posición / valor en USD al entrar - 1 (usa `get_token_balance_usd`, sin llamadas extra a APIs).
- El valor de entrada se guarda en `ENTRY_VALUE_USD` justo después de una entrada confirmada. Si el agente se reinicia con una posición ya abierta, la referencia es el valor al empezar el monitoreo, así que el P&L cuenta desde ese momento.
- Al cumplirse un umbral llama a `chunk_kill` y verifica que el balance desapareció (si quedan más de $0.10 devuelve `False`, y `main()` espera y reintenta).
- Limitación: el P&L se basa en el valor en USD que devuelve la consulta de la billetera. Si esa llamada falla y devuelve 0, el monitor considera la posición cerrada (comportamiento previo de `get_token_balance_usd`).
- Los mensajes de `ai_entry` ya no mencionan un tope de "max 30% of usd_size" que nunca existió.

### Compatibilidad con HyperLiquid
`nice_funcs_hyperliquid.py` tiene una API distinta a la de Aster (`get_position` necesita un `account` y devuelve una tupla; no existen `chunk_kill`, `limit_sell` ni `limit_buy`). En lugar de cambiar ese módulo, `trading_agent.py` incorporó una pequeña capa de adaptadores (junto a `ENTRY_VALUE_USD`):
- `get_futures_position(token)`: diccionario de posición unificado para Aster y HyperLiquid (`position_amount`, `entry_price`, `mark_price`, `pnl`, `pnl_percentage`, `is_long`).
- `get_position_usd(token)`: valor en USD de la posición en cualquier exchange.
- `close_position_full(token)`: `chunk_kill` en Solana y Aster, `kill_switch` (orden IOC reduce-only) en HyperLiquid.
- `close_futures_position(token, position, size)`: la usan el stop loss y el take profit (`kill_switch` en HyperLiquid, órdenes límite en Aster).
- Los shorts en HyperLiquid ahora fallan de forma visible si `open_short` no devuelve orden.
- `pnl_percentage` en HyperLiquid es `returnOnEquity` (rendimiento sobre el margen, por lo que incluye el apalancamiento). Un stop loss o take profit del 5% se activa entonces con un movimiento de precio de aproximadamente 5% / apalancamiento.
- HyperLiquid exige un mínimo de $10 por orden (`market_buy` sube las menores a $11).
- Probado con órdenes reales en la testnet de HyperLiquid (ver más abajo). En mainnet solo se probaron lecturas, sin órdenes.

### Salidas long/short
`handle_exits` ahora lee la dirección de la posición abierta (`get_futures_position`, Aster y HyperLiquid) en lugar de tratar toda posición como un long:

| Posición | BUY | SELL | NOTHING |
|----------|-----|------|---------|
| LONG | mantener | cerrar | mantener |
| SHORT | cerrar | mantener | mantener |

Después de cerrar un short por una señal BUY, un nuevo long solo se abre en el ciclo siguiente si la señal sigue siendo BUY. Con `LONG_ONLY = True` (y en Solana) no cambia nada.

### Cuenta unificada de HyperLiquid y testnet
- En una Cuenta Unificada el colateral es el saldo de USDC en spot. El `accountValue` de perpetuos queda en 0 sin posiciones y, con una abierta, solo muestra el margen en uso (una parte del mismo dinero, no dinero adicional). `get_account_balance` ahora detecta `unifiedAccount` y `portfolioMargin` (`userAbstraction`) y usa el **total de USDC spot**, que es el patrimonio completo.
- `nice_funcs_hyperliquid.py` acepta `HL_TESTNET=true` (variable de entorno) para usar la testnet de HyperLiquid con fondos de prueba. Mainnet sigue siendo el valor por defecto. Ejemplo: `HL_TESTNET=true python src/agents/trading_agent.py`. La cuenta de testnet se fondea con el faucet de la app de testnet.
- Verificado en testnet con órdenes reales: BUY abre un long, el monitor lo cierra por take profit, SELL cierra un long, SELL sin posición abre un short (`LONG_ONLY = False`), SELL mantiene un short y BUY lo cierra. El balance leído con una posición abierta coincide con el patrimonio completo.
- También se ejecutó un ciclo completo con el swarm real (6 modelos, datos de mercado y decisión). Resultado: NOTHING con 83%, sin operar.

Nota: HyperLiquid exige un mínimo de $10 por orden y `market_buy` sube las menores a $11. En cuentas pequeñas esto pasa por encima de `MAX_POSITION_PERCENTAGE` (por ejemplo, 30% de $12.41 = $3.72, pero la orden enviada es de $11).

### Resultado de las órdenes de HyperLiquid
HyperLiquid responde `status: "ok"` incluso cuando la orden se rechaza; el resultado real está en `response.data.statuses` (`filled`, `resting` o `{"error": ...}`). `ai_entry` devolvía `result is not None` y `open_short` devolvía la respuesta cruda, así que una orden rechazada se reportaba como abierta.
- La nueva `_check_order()` en `nice_funcs_hyperliquid.py` lanza `RuntimeError` con el mensaje del exchange cuando la orden no es aceptada.
- La usan `ai_entry`, `open_short` y `kill_switch` (un cierre rechazado ahora se hace visible, así que el monitor reintenta en lugar de suponer que la posición se cerró).
- Verificado en testnet: una orden rechazada ahora lanza `Insufficient margin to place order`; las entradas y cierres normales de long y short siguen funcionando.
- Nota: una orden mayor que el margen disponible no siempre se rechaza; HyperLiquid puede llenarla **parcialmente** hasta donde alcance el margen (una orden de prueba de $5 millones se llenó por unos $950 en testnet).

### Reanálisis mientras hay una posición abierta
`monitor_position_pnl` bloqueaba el ciclo principal hasta que el stop loss o el take profit cerraran la posición, así que mientras tanto no había análisis nuevo ni señales SELL. Ahora `main()` le pasa `run_cycle=agent.run_trading_cycle` y `cycle_interval=SLEEP_BETWEEN_RUNS_MINUTES * 60`:
- El stop loss y el take profit se siguen revisando cada `PNL_CHECK_INTERVAL` segundos.
- Cada `SLEEP_BETWEEN_RUNS_MINUTES` el monitor corre un ciclo completo (swarm incluido). Con la posición abierta, una señal BUY la mantiene y una SELL la cierra (un short se cierra con BUY). El monitor nota el cierre en su siguiente revisión y termina.
- El intervalo se cuenta desde el final de cada ciclo, así que el período real es el intervalo más la duración del ciclo (cerca de un minuto con el swarm).
- Costo: un swarm cada `SLEEP_BETWEEN_RUNS_MINUTES`, igual que cuando no hay posición.
- Verificado en testnet con un ciclo simulado: BUY, BUY, SELL; el SELL cerró el long y el monitor devolvió `True`.

### Problemas conocidos sin corregir
- `ai_entry` (Solana) toma `max_usd_order_size`, `slippage`, `orders_per_open` y `tx_sleep` de `src/config.py`, no del encabezado de `trading_agent.py`. El `max_usd_order_size` y el `slippage` propios del agente solo afectan a `chunk_kill`.
- `ai_entry` no tiene tope propio: el tamaño lo decide quien la llama (`calculate_position_size`, hasta `MAX_POSITION_PERCENTAGE` del balance en USDC, comprado en chunks de $3).
- Ajeno a este agente, en `nice_funcs.py`: `pnl_close` usa `stop_loss_percentage` (la configuración define `stop_loss_perctentage`, con un typo) y `close_all_positions` usa `dont_trade_list`, que no está definido.
- `SOL_ADDRESS` termina en `...1111`; el mint real de SOL envuelto termina en `...2`.
- Los comentarios y las referencias de línea del docstring al inicio de `trading_agent.py` están desactualizados, y las etiquetas ACTIVE/DISABLED de FART y housecoin en `MONITORED_TOKENS` están intercambiadas.
