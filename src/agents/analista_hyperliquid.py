"""
Moon Dev - Analista Hyperliquid

Ejecuta el snapshot de la Moon Dev Data Layer API (los mismos endpoints de
repositorios/Hyperliquid-Data-Layer-API/examples), pide a un LLM que lo interprete y guarda un
informe en español con oportunidades, explicaciones y estrategia sugerida en
src/data/analisis_hyperliquid_data/<fecha>.md

Uso:
    python src/agents/analista_hyperliquid.py              # toma snapshot nuevo
    python src/agents/analista_hyperliquid.py --reuse      # usa el último snapshot guardado
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
REPORT_DIR = PROJECT_ROOT / "src" / "data" / "analisis_hyperliquid_data"

# Configuración del modelo LLM (usa GROK_API_KEY del archivo .env a través de model_factory)
MODEL_CONFIG = {"type": "xai", "name": "grok-4-fast-reasoning"}
MAX_SNAPSHOT_CHARS = 120_000
MAX_TOKENS = 6000

SYSTEM_PROMPT = """Eres un analista de mercado de Hyperliquid que redacta un INFORME EJECUTIVO para alguien que está aprendiendo a operar.
Recibes un snapshot JSON REAL (liquidaciones HL/Binance/Bybit/OKX, posiciones cerca de liquidación, whales, orderflow/CVD,
smart money, HLP, funding/OI, HIP-3, precios, orderbook de BTC). Cada sección indica el script de origen (campo "script").

TU TRABAJO PRINCIPAL ES TRADUCIR: explicar qué está pasando en el mercado como si hablaras con un estudiante, sin asumir
conocimientos previos. Para cada tema: primero qué es en una frase simple (con una analogía cotidiana si ayuda), luego qué
dicen los datos de hoy, y por último qué significa para el precio.

REGLAS:
- Escribe TODO en español, tono claro y cercano, párrafos cortos.
- Los términos técnicos (liquidación, funding, CVD, OI, smart money, whales, HLP, long/short, orderbook...) NO se explican
  en el texto: la explicación va solo en el Glosario. En el texto, cada término del glosario lleva un número entre corchetes
  pegado a la palabra, la primera vez que aparece en el informe (ej. "las liquidaciones[1] subieron"). Ese mismo número
  identifica el término en el Glosario. Cada término tiene un único número y no se repite el marcador después de la primera vez.
- Usa solo datos del snapshot, con sus números reales. Si una sección está vacía o falló, dilo; no inventes nada.
- Cita entre paréntesis la sección de donde sale cada dato clave (ej. "(liquidations_hl_1h)").
- Extensión: UNA sola página, unas 500 palabras como máximo. Elige solo los 3-4 temas más relevantes de hoy; nada de relleno ni repeticiones.
- Contexto del usuario: cuenta pequeña, solo posiciones LONG, apalancamiento 1x, stop loss y take profit del 5%.
  Prioriza oportunidades que encajen con eso y di claramente cuándo lo mejor es no operar.
- Es análisis, no consejo financiero: no prometas resultados y menciona la incertidumbre.

FORMATO EXACTO (markdown):
# Informe ejecutivo Hyperliquid - {fecha}
## Conclusión ejecutiva
Un párrafo corto: ¿cómo está el mercado hoy (alcista, bajista, indeciso) y qué conviene hacer? Con la menor jerga posible.
## Qué está pasando en el mercado (explicado paso a paso)
Una subsección ### por cada uno de los 3-4 temas más relevantes de hoy (liquidaciones, ballenas y smart money, orderflow,
funding y open interest, HLP). Cada una en 2-3 frases: qué vemos hoy (con números) y qué significa, usando los marcadores [n].
## Oportunidades
Tabla: Activo | Dirección (Long/Evitar) | Por qué | Confianza (Alta/Media/Baja)
Máximo 3 filas.
## Riesgos
Máximo 3 viñetas cortas: qué podría salir mal y qué NO hacer.
## Estrategia sugerida
Entrada, salida y stop en términos concretos y relativos al precio actual, aplicables a la cuenta del usuario.
Si no hay ventaja clara, di "esperar" y qué tendría que pasar para entrar.
## Glosario
Lista numerada con el mismo número de los marcadores del texto, en orden de aparición. Formato por línea:
`[1] **Término**: definición en una frase simple, con analogía cotidiana si ayuda.`
Incluye todos los términos marcados (5-10) y ninguno que no aparezca en el texto.
## Datos que no estuvieron disponibles
Secciones con error o vacías (o "ninguna")."""


def latest_snapshot():
    files = sorted(SNAPSHOT_DIR.glob("snapshot_*.json"))
    if not files:
        raise SystemExit("No hay snapshots guardados; ejecuta sin --reuse.")
    return files[-1]


def report_path():
    """<fecha>.md; si ya existe uno de hoy, añade la hora para no sobrescribirlo."""
    now = datetime.now()
    path = REPORT_DIR / f"{now.strftime('%Y-%m-%d')}.md"
    if path.exists():
        path = REPORT_DIR / f"{now.strftime('%Y-%m-%d_%H%M')}.md"
    return path


def main():
    path = latest_snapshot() if "--reuse" in sys.argv else hyperliquid_snapshot.main()
    snapshot = json.loads(Path(path).read_text())
    if snapshot["errors"]:
        cprint(f"⚠️ Secciones con error: {', '.join(snapshot['errors'])}", "yellow")
    if not snapshot["sections"]:
        raise SystemExit("Snapshot sin datos; no se genera informe.")

    payload = json.dumps(snapshot, default=str)[:MAX_SNAPSHOT_CHARS]
    model_type = "xai" if MODEL_CONFIG["type"].lower() == "grok" else MODEL_CONFIG["type"]
    model = model_factory.get_model(model_type, MODEL_CONFIG["name"])
    if not model:
        raise SystemExit(f"No se pudo iniciar el modelo {MODEL_CONFIG}")

    cprint("🧠 Analizando snapshot de Hyperliquid...", "cyan")
    system_prompt = SYSTEM_PROMPT.replace("{fecha}", datetime.now().strftime("%Y-%m-%d"))
    response = model.generate_response(system_prompt=system_prompt, user_content=payload, temperature=0.4, max_tokens=MAX_TOKENS)
    text = response if isinstance(response, str) else getattr(response, "content", str(response))
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = report_path()
    out.write_text(text + f"\n\n---\nSnapshot: `{Path(path).name}` ({len(snapshot['sections'])} secciones, {len(snapshot['errors'])} con error)\n")
    cprint(f"✅ Informe guardado en {out}", "green")
    return out


if __name__ == "__main__":
    main()
