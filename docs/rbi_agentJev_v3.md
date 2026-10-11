# RBI Agent Jev v3 (`src/agents/rbi_agentJev_v3.py`)

Copia independiente de `rbi_agent_v3.py` con un filtro previo. Cada idea pasa primero por **Jev** (`typesafe/jev-1.13`, vía la Decisions API de OpenRouter). Si Jev la aprueba, sigue al ciclo RBI normal de este mismo agente, con Grok. Si no, se descarta y no se gasta ningún token de backtest en ella.

El ciclo RBI (research, backtest, debug, optimización) es el mismo que describe [rbi_agent_v3.md](rbi_agent_v3.md). Esta página solo documenta lo que cambia.

## Uso

```bash
cd /Users/germandavidvertelnarvaez/Developer/moondev-ai-trading-agents
conda activate tflow
python -m src.agents.rbi_agentJev_v3
```

Antes hay que generar las ideas con `research_agent_jev.py`, que escribe en la misma carpeta:

```bash
python src/agents/research_agent_jev.py
```

## Entradas

- **Ideas:** `src/data/rbi_jev_v3/ideas.txt`. Lo escribe `research_agent_jev.py`. Mismo formato que `rbi_v3/ideas.txt`: una idea por línea, `#` para comentarios.
- **Claves:** `OPENROUTER_API_KEY` (filtro Jev) y `GROK_API_KEY` (ciclo RBI), ambas en `.env`.
- **Datos:** `src/data/rbi/binance_15m/BTC-USDT-15m.csv`, igual que `rbi_agent_v3`.

## El filtro Jev

Jev no devuelve texto. Responde tres preguntas de tipo sí/no, cada una con una probabilidad entre 0 y 1:

| Pregunta | Qué evalúa |
|---|---|
| `backtesteable_con_ohlcv` | Si la señal se puede calcular con precio y volumen, directa o con un proxy razonable |
| `reglas_claras` | Si hay reglas concretas de entrada, salida o stop |
| `ventaja_plausible` | Si la lógica tiene una razón de mercado plausible y no depende de niveles de precio fijos |

Se le pasa como contexto que solo hay OHLCV de 15 minutos de BTC, ETH y SOL, y que no hay liquidaciones, funding, open interest, order book ni datos on-chain.

**Regla:** la idea pasa si las **tres** probabilidades son al menos `JEV_MIN_PROB = 0.6`. Si alguna queda por debajo, se descarta. El motivo queda en el log como el nombre de la pregunta que no llegó al umbral.

Cada llamada cuesta unos $0,00003.

## Decisiones

Se guardan en `src/data/rbi_jev_v3/jev_decisions.csv`:

```
timestamp,hash,decision,backtesteable_con_ohlcv,reglas_claras,ventaja_plausible,cost_usd,idea_snippet
```

Decisiones posibles: `APROBADA` o `DESCARTADA`.

Una idea descartada se registra en `processed_ideas.log` como `DESCARTADA_JEV`, así que no se vuelve a evaluar. Para reevaluarla, borra su línea de ese log.

## Qué pasa si falla la API

Si la llamada a Jev falla (clave inválida, saldo, límite de tasa), el agente se detiene con el error. No aprueba ni descarta la idea, para no tomar decisiones a ciegas.

## Salidas

Carpeta: `src/data/rbi_jev_v3/<MM_DD_YYYY>/`, con las mismas subcarpetas que `rbi_v3`. Además:

- `jev_decisions.csv`: decisiones del filtro.
- `processed_ideas.log`: ideas procesadas y descartadas.
- `ideas.txt`: entrada, la escribe `research_agent_jev.py`.

Al final del run, el agente imprime un resumen: cuántas ideas pasaron el filtro y cuántas se descartaron.

## Ajustes

- **Umbral:** `JEV_MIN_PROB` en `rbi_agentJev_v3.py`. Con 0,6 el filtro es estricto. Si descarta demasiado, bájalo.
- **Preguntas:** `JEV_QUESTIONS`. Cada pregunta tiene `instructions` y `criteria` con las descripciones de `true` y `false`.
- **Contexto:** `JEV_CONTEXT`, que describe qué datos existen. Si cambian los datos disponibles, hay que actualizarlo aquí, o Jev evaluará ideas con datos que no tenemos.

## Limitaciones conocidas

- **Heredadas de `rbi_agent_v3`:** la comisión solo se exige por prompt (sin comprobación en código), no hay validación fuera de muestra y a veces el modelo llama a `bt.plot()`. Ver [rbi_agent_v3.md](rbi_agent_v3.md).
- **Jev no predice si la estrategia opera:** en la corrida del 11/10/2026 aprobó 5 ideas y 4 no abrieron ni una operación en las 10 depuraciones; la única que operó dio +1,38 % frente a ~398 % de buy & hold. El filtro evalúa la descripción, no si las condiciones se cumplen en los datos.
- **Jev no entiende los datos:** evalúa la descripción de la idea, no los resultados del backtest. Una idea puede pasar el filtro y aun así no ser rentable.
- **Preguntas binarias:** un umbral de 0,6 en cada pregunta deja pasar ideas que están apenas por encima del corte. No es una medida de calidad.

## Problemas corregidos

- **Bloque `multi_data_tester` y bucle de 0 trades:** igual que en `rbi_agent_v3` (se quitó el import inexistente y se descarta la idea tras 3 ejecuciones sin operaciones). Ver [rbi_agent_v3.md](rbi_agent_v3.md).

- **Ruta del CSV:** igual que en `rbi_agent_v3`, el prompt de backtest recibía `{PROJECT_ROOT}` sin sustituir. Ahora se corrige en `create_backtest` y en el prompt de debug (`BTC_CSV_PATH`).
- **Carpeta de ideas:** antes leía `src/data/rbi_pp_multi/ideas.txt`. Ahora lee `src/data/rbi_jev_v3/ideas.txt`, para no mezclar ideas con las de `research_agent.py`.
