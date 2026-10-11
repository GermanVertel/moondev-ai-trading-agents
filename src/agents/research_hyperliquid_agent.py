"""
Moon Dev - Research Hyperliquid Agent (versión Python)

Toma un snapshot real de la Moon Dev Data Layer API (liquidaciones, whales, orderflow,
smart money, HLP, funding/OI...), pide a un LLM que lo interprete y anexa ideas de
estrategia (una línea cada una, con números) a src/data/rbi_v3/ideas.txt.

Uso:
    python src/agents/research_hyperliquid_agent.py              # toma snapshot nuevo
    python src/agents/research_hyperliquid_agent.py --reuse      # usa el último snapshot guardado
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from termcolor import cprint

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "scripts"))

from src.models import model_factory
import hyperliquid_snapshot

SNAPSHOT_DIR = PROJECT_ROOT / "src" / "data" / "research_hyperliquid"
IDEAS_TXT = PROJECT_ROOT / "src" / "data" / "rbi_v3" / "ideas.txt"
IDEAS_LOG = SNAPSHOT_DIR / "ideas_generadas.csv"

# Configuración del modelo LLM (usa GROK_API_KEY del archivo .env a través de model_factory)
MODEL_CONFIG = {"type": "xai", "name": "grok-4-fast-reasoning"}
NUM_IDEAS = 12
MAX_SNAPSHOT_CHARS = 120_000

SYSTEM_PROMPT = f"""Eres un analista cuantitativo de Hyperliquid. Recibes un snapshot JSON REAL del mercado
(liquidaciones HL/Binance/Bybit/OKX, posiciones cerca de liquidación, whales, events, contracts, ticks,
orderflow/CVD, trades, smart_money, user_positions/fills, HLP, buyers, depositors, HIP-3, funding/OI).

Usa el snapshot para entender qué condiciones del mercado son anómalas o extremas hoy, y conviértelas en
CONDICIONES RECURRENTES: situaciones que se repiten en cualquier día y activo y que se pueden buscar en el
histórico (ej. 'ratio de liquidaciones short/long en 1h por encima de 5:1', 'funding en el percentil 5 de sus
últimos 30 días', 'CVD a más de 2 desviaciones estándar'). Propón {NUM_IDEAS} ideas de estrategia distintas.

REGLAS DE CONDICIONES RECURRENTES (estrictas):
- Cada idea se define por un umbral genérico (percentil, z-score, ratio, múltiplo del promedio) y no por un hecho
  puntual de hoy. Debe seguir teniendo sentido mañana, con otro símbolo y con otros montos.
- NUNCA nombres un símbolo concreto como condición de entrada (nada de 'si STRK liquida...'); di en qué tipo de
  activos aplica (ej. 'altcoins líquidas', 'BTC y ETH') y cita el símbolo del snapshot solo como ejemplo de dónde
  se observó la condición.
- Usa los números del snapshot para calibrar el umbral (qué tan extrema es la condición frente a lo normal) y
  menciónalos como ejemplo observado, nunca como parte de la regla.
- Cada idea debe poder responder: ¿cuántas veces ocurrió esta condición en el histórico y qué hizo el precio después?

REGLAS DE FORMATO (estrictas):
- Escribe TODO en español.
- PROHIBIDO usar precios absolutos o niveles fijos de precio (ej. 'si BTC rompe 82000'). Usa solo umbrales relativos: % de movimiento, múltiplos del volumen promedio, ATR, VWAP, máximos/mínimos de N velas, medias móviles, z-scores, ratios long/short, % de distancia a liquidación.
- Los montos en USD del snapshot solo sirven como contexto de la condición, no como parte de la regla de entrada.
- Una idea por línea, texto plano. Sin numeración, viñetas, markdown, ni líneas vacías.
- Cada idea indica la condición recurrente con su umbral, un ejemplo observado en el snapshot (con sus números) y una regla de entrada, salida y stop.
- Debe ser backtesteable con OHLCV (backtesting.py + pandas_ta/talib). Si la señal original no está en OHLCV
  (liquidaciones, whales), usa un proxy de precio/volumen y menciona la señal como contexto.
- Cubre áreas distintas (liquidaciones, orderflow/CVD, smart money, HLP, funding/OI, whales, HIP-3, polymarket); como máximo 2 ideas por símbolo.
- Prefiere señales cuantitativas con umbrales (z-scores, ratios long/short, % de distancia a liquidación, funding) y usa timeframes y activos con OHLCV (BTC, ETH, SOL, HYPE...).
- NO uses volatilidad implícita, opciones, ni datos que no puedan reconstruirse con OHLCV; evita activos ilíquidos con liquidaciones de unos pocos miles de USD.
- Máximo 2-3 frases por idea. No inventes datos que no estén en el snapshot.
- Responde SOLO con las líneas de ideas."""


def latest_snapshot():
    files = sorted(SNAPSHOT_DIR.glob("snapshot_*.json"))
    if not files:
        raise SystemExit("No hay snapshots guardados; ejecuta sin --reuse.")
    return files[-1]


def clean_line(line):
    line = re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", line.strip())
    line = line.replace("**", "").strip().strip('"')
    return line.lstrip("#").strip()


def parse_ideas(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    ideas = []
    for line in text.splitlines():
        cleaned = clean_line(line)
        if len(cleaned) <= 40:
            continue
        if "disclaimer" in cleaned.lower():
            continue
        ideas.append(cleaned)
    return ideas


def existing_ideas():
    if not IDEAS_TXT.exists():
        return set()
    return {l.strip().lower() for l in IDEAS_TXT.read_text().splitlines() if l.strip() and not l.startswith("#")}


def save_ideas(ideas):
    IDEAS_TXT.parent.mkdir(parents=True, exist_ok=True)
    seen = existing_ideas()
    new = [i for i in ideas if i.lower() not in seen]
    if not new:
        return 0
    prefix = "\n" if IDEAS_TXT.exists() and IDEAS_TXT.stat().st_size and not IDEAS_TXT.read_text().endswith("\n") else ""
    with open(IDEAS_TXT, "a") as f:
        f.write(prefix + "\n".join(new) + "\n")
    with open(IDEAS_LOG, "a") as f:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for i in new:
            f.write(f'{stamp},{MODEL_CONFIG["name"]},"{i.replace(chr(34), chr(39))}"\n')
    return len(new)


def main():
    path = latest_snapshot() if "--reuse" in sys.argv else hyperliquid_snapshot.main()
    snapshot = json.loads(Path(path).read_text())
    if snapshot["errors"]:
        cprint(f"⚠️ Secciones con error: {', '.join(snapshot['errors'])}", "yellow")
    if not snapshot["sections"]:
        raise SystemExit("Snapshot sin datos; no se generan ideas.")

    payload = json.dumps(snapshot, default=str)[:MAX_SNAPSHOT_CHARS]
    model_type = "xai" if MODEL_CONFIG["type"].lower() == "grok" else MODEL_CONFIG["type"]
    model = model_factory.get_model(model_type, MODEL_CONFIG["name"])
    if not model:
        raise SystemExit(f"No se pudo iniciar el modelo {MODEL_CONFIG}")

    cprint("🧠 Analizando snapshot de Hyperliquid...", "cyan")
    response = model.generate_response(system_prompt=SYSTEM_PROMPT, user_content=payload, temperature=0.7, max_tokens=4000)
    text = response if isinstance(response, str) else getattr(response, "content", str(response))

    ideas = parse_ideas(text)
    added = save_ideas(ideas)
    for i in ideas:
        cprint(f"💡 {i}", "yellow")
    cprint(f"✅ {added} ideas nuevas añadidas a {IDEAS_TXT} ({len(ideas) - added} duplicadas)", "green")


if __name__ == "__main__":
    main()
