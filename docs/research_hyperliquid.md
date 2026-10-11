# Research Hyperliquid (subagente)

Subagente de Claude Code (`.claude/agents/research_hyperliquid.md`) que convierte datos reales de la Moon Dev Data Layer API en ideas para `rbi_v3`.

## Componentes
- `src/scripts/hyperliquid_snapshot.py`: recolector solo lectura. Llama una vez a los endpoints de los scripts `examples/01..38` (excepto 23 y 25), pausa 1 s entre llamadas, recorta listas largas y guarda `src/data/research_hyperliquid/snapshot_<fecha>.json`. Aborta si la API responde 401.
- Subagente `research_hyperliquid`: ejecuta el recolector, interpreta el snapshot y anexa 10-15 ideas (una línea cada una, con números) a `src/data/rbi_v3/ideas.txt`, sin duplicados.

## Uso
```bash
conda activate tflow
python src/scripts/hyperliquid_snapshot.py   # solo el snapshot
```
Luego pide en Claude Code: "usa el subagente research_hyperliquid".

## Requisitos y límites
- `MOONDEV_API_KEY` válida en `.env`. Los endpoints tienen rate limit (429).
- La API da estado actual y ventanas cortas; las ideas deben ser backtesteables con OHLCV, usando proxies cuando la señal original (liquidaciones, whales) no esté en el CSV.
- Solo investigación: no ejecuta órdenes. Las ideas son hipótesis, sin garantía de rentabilidad.

## Versión Python
`src/agents/research_hyperliquid_agent.py`: mismo flujo sin Claude Code. Toma el snapshot (o `--reuse` para el último guardado), lo envía a un LLM vía `model_factory` (por defecto Grok/xAI usando `GROK_API_KEY` de `.env`, configurable en `MODEL_CONFIG`) y anexa ~12 ideas deduplicadas a `src/data/rbi_v3/ideas.txt`; el registro queda en `src/data/research_hyperliquid/ideas_generadas.csv`.
```bash
python src/agents/research_hyperliquid_agent.py
```
Si la API devuelve 401/429 el agente se detiene sin escribir ideas.
