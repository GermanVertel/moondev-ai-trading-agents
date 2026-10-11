# RBI Agent v3 (`src/agents/rbi_agent_v3.py`)

Agente que toma ideas de trading en texto, las convierte en estrategias de `backtesting.py`, las ejecuta y las optimiza hasta alcanzar un retorno objetivo. Es la versión con Grok (xAI) de todo el ciclo. Para la versión que pasa cada idea por un filtro de Jev, ver [rbi_agentJev_v3.md](rbi_agentJev_v3.md).

## Uso

```bash
cd /Users/germandavidvertelnarvaez/Developer/moondev-ai-trading-agents
conda activate tflow
python -m src.agents.rbi_agent_v3
```

Hay que ejecutarlo desde la raíz del proyecto. Con `python src/agents/rbi_agent_v3.py` falla la importación de `src`.

## Entradas

- **Ideas:** `src/data/rbi_v3/ideas.txt`. Una idea por línea. Se ignoran las líneas vacías y las que empiezan con `#`. Si el archivo no existe, el agente crea una plantilla y termina.
- **Datos:** `src/data/rbi/binance_15m/BTC-USDT-15m.csv`. Velas de 15 minutos de Binance spot, desde 2023-01-01. Se actualizan con `python src/scripts/download_binance_15m.py`. ETH y SOL están en la misma carpeta, pero el agente solo usa BTC.
- **Claves:** `GROK_API_KEY` en `.env`. Todas las etapas usan `grok-4-fast-reasoning`.

## Parámetros principales

Están al inicio de `rbi_agent_v3.py`.

| Parámetro | Valor | Qué controla |
|---|---|---|
| `TARGET_RETURN` | 50 | Retorno objetivo en % (`Return [%]`) |
| `MAX_DEBUG_ITERATIONS` | 10 | Intentos de corregir errores de ejecución |
| `MAX_OPTIMIZATION_ITERATIONS` | 10 | Rondas de optimización por idea |
| `EXECUTION_TIMEOUT` | 300 | Segundos máximos por backtest |
| `CONDA_ENV` | `tflow` | Entorno con que se ejecutan los backtests |

## Flujo por idea

1. **Research:** el modelo da un nombre de estrategia de dos palabras y describe reglas de entrada, salida y riesgo.
2. **Backtest:** escribe el código de `backtesting.py` con `self.I()` y talib o pandas_ta. Usa `cash=1.000.000` y posiciones enteras o fracciones.
3. **Package check:** revisa que los paquetes usados estén disponibles.
4. **Ejecución y debug:** corre el archivo con `conda run -n tflow python`. Extrae `Return [%]`. Si falla, el modelo corrige el código hasta `MAX_DEBUG_ITERATIONS` veces.
5. **Optimización:** mientras `Return [%]` esté por debajo del objetivo, el modelo mejora la estrategia hasta `MAX_OPTIMIZATION_ITERATIONS` veces.
6. **Registro:** la idea queda en `processed_ideas.log` (md5 de la línea, fecha, nombre y primeros 50 caracteres). No se vuelve a procesar.

El objetivo de 50 % se cumple cuando `Return [%]` lo alcanza. Si el objetivo se alcanza, el archivo final se guarda como `_TARGET_HIT_<ret>pct.py`. Si no, queda como `_BEST_<ret>pct.py`.

## Salidas

Carpeta: `src/data/rbi_v3/<MM_DD_YYYY>/`

- `research/`: texto de la estrategia (`<Nombre>_strategy.txt`).
- `backtests/`: primer código de backtest (`<Nombre>_BT.py`).
- `backtests_package/`: código revisado (`<Nombre>_PKG.py`).
- `backtests_final/`: versiones de depuración (`_BTFinal_v<i>.py`) y la que funcionó (`_BTFinal_WORKING_<ret>pct.py`).
- `backtests_optimized/`: versiones optimizadas (`_OPT_v<i>.py`) y la final (`_TARGET_HIT_` o `_BEST_`).
- `execution_results/`: JSON con `stdout`, `stderr`, código de salida y tiempo de cada ejecución.

## Limitaciones conocidas

- **Sin comisión en el prompt:** el prompt de backtest no fija comisión, así que el modelo a menudo usa `commission=0`. Los retornos salen inflados. Para validar, usar `commission=0.0004` (0,04 % por lado). El subagente `rbi_agent_v3_claude` sí lo exige.
- **Sin validación fuera de muestra:** el agente optimiza y reporta sobre el mismo periodo.
- **Gráficos:** el modelo a veces llama a `bt.plot()` a pesar del prompt. Eso abre una pestaña del navegador y deja un HTML en la carpeta desde donde se ejecutó (la raíz del proyecto). No afecta a los resultados.
- **Señales que no están en OHLCV:** si la idea depende de liquidaciones, whales o funding, el modelo usa un proxy de precio y volumen. El backtest no valida la señal original.
- **Tiempo:** con unas 132.000 velas, un backtest puede acercarse al límite de 300 s.

## Problemas corregidos

- **Ruta del CSV:** el prompt de backtest recibía `{PROJECT_ROOT}` sin sustituir. El modelo escribía `/src/data/...` y todos los backtests fallaban al leer el CSV. Ahora `create_backtest` sustituye la variable por la raíz del proyecto, y el prompt de debug recibe la ruta absoluta correcta (`BTC_CSV_PATH`).
