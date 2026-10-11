"""
Moon Dev - Snapshot de mercado de Hyperliquid (solo lectura)

Llama una vez a los mismos endpoints que usan los scripts de
repositorios/Hyperliquid-Data-Layer-API/examples (01-38) y guarda un JSON compacto en
src/data/research_hyperliquid/snapshot_<timestamp>.json para que el subagente
research_hyperliquid lo interprete y genere ideas para rbi_v3/ideas.txt.

Uso: python src/scripts/hyperliquid_snapshot.py
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
API_REPO = ROOT / "repositorios" / "Hyperliquid-Data-Layer-API"
OUT_DIR = ROOT / "src" / "data" / "research_hyperliquid"
MAX_LIST = 15   # items por lista
MAX_KEYS = 40   # claves por dict

load_dotenv(API_REPO / ".env", override=True)  # clave de la Data Layer API
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(API_REPO))
from api import MoonDevAPI  # noqa: E402


def compact(obj, depth=0):
    """Recorta listas/dicts largos para no inflar el contexto del LLM."""
    if depth > 6:
        return "..."
    if isinstance(obj, list):
        out = [compact(x, depth + 1) for x in obj[:MAX_LIST]]
        if len(obj) > MAX_LIST:
            out.append({"_total_items": len(obj)})
        return out
    if isinstance(obj, dict):
        keys = list(obj)[:MAX_KEYS]
        out = {k: compact(obj[k], depth + 1) for k in keys}
        if len(obj) > MAX_KEYS:
            out["_total_keys"] = len(obj)
        return out
    return obj


def find_address(obj):
    """Primera dirección 0x de 42 chars dentro de cualquier estructura."""
    if isinstance(obj, str):
        return obj if obj.startswith("0x") and len(obj) == 42 else None
    items = obj.values() if isinstance(obj, dict) else obj if isinstance(obj, list) else []
    for x in items:
        found = find_address(x)
        if found:
            return found
    return None


def public_funding_oi():
    """Script 33: funding y OI de BTC en Hyperliquid y Binance (APIs públicas, sin key)."""
    hl = requests.post("https://api.hyperliquid.xyz/info", json={"type": "metaAndAssetCtxs"}, timeout=30).json()
    names = [a["name"] for a in hl[0]["universe"]]
    btc = hl[1][names.index("BTC")]
    prem = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex", params={"symbol": "BTCUSDT"}, timeout=30).json()
    oi = requests.get("https://fapi.binance.com/fapi/v1/openInterest", params={"symbol": "BTCUSDT"}, timeout=30).json()
    return {"hyperliquid_BTC": btc, "binance_premiumIndex": prem, "binance_openInterest": oi}


def main():
    api = MoonDevAPI()
    if not api.api_key:
        raise SystemExit("Falta MOONDEV_API_KEY en .env")

    # (sección, script de origen, función sin argumentos)
    tasks = [
        ("liquidations_hl_1h", "01", lambda: api.get_liquidations("1h")),
        ("liquidations_hl_24h", "01", lambda: api.get_liquidations("24h")),
        ("liquidation_stats_hl", "01", api.get_liquidation_stats),
        ("positions_near_liq", "02", api.get_positions),
        ("positions_all", "02", api.get_all_positions),
        ("whales", "03", api.get_whales),
        ("events", "04", api.get_events),
        ("contracts", "05", api.get_contracts),
        ("tick_stats", "06", api.get_tick_stats),
        ("tick_latest", "06", api.get_tick_latest),
        ("orderflow", "07", api.get_orderflow),
        ("orderflow_stats", "07", api.get_orderflow_stats),
        ("trades", "08", api.get_trades),
        ("large_trades", "08", api.get_large_trades),
        ("smart_money_rankings", "09", api.get_smart_money_rankings),
        ("smart_money_signals_10m", "09", lambda: api.get_smart_money_signals("10m")),
        ("smart_money_signals_1h", "09", lambda: api.get_smart_money_signals("1h")),
        ("smart_money_signals_24h", "09", lambda: api.get_smart_money_signals("24h")),
        ("hlp_positions", "12", api.get_hlp_positions),
        ("hlp_deltas", "12", api.get_hlp_deltas),
        ("binance_liquidations_1h", "13", lambda: api.get_binance_liquidations("1h")),
        ("binance_liquidation_stats", "13", api.get_binance_liquidation_stats),
        ("all_liquidations_1h", "14", lambda: api.get_all_liquidations("1h")),
        ("all_liquidation_stats", "14", api.get_all_liquidation_stats),
        ("buyers", "15", api.get_buyers),
        ("depositors", "16", api.get_depositors),
        ("hlp_sentiment", "17", api.get_hlp_sentiment),
        ("hlp_flips", "17", api.get_hlp_flips),
        ("hlp_flip_stats", "17", api.get_hlp_flip_stats),
        ("hlp_liquidator_status", "18", api.get_hlp_liquidator_status),
        ("hlp_market_maker", "18", api.get_hlp_market_maker),
        ("hlp_timing", "18", api.get_hlp_timing),
        ("hlp_correlation", "18", api.get_hlp_correlation),
        ("prices", "19", api.get_prices),
        ("orderbook_BTC", "19", lambda: api.get_orderbook("BTC")),
        ("hip3_liquidations_1h", "20", lambda: api.get_hip3_liquidations("1h")),
        ("hip3_liquidation_stats", "20", api.get_hip3_liquidation_stats),
        ("hip3_tick_stats", "21", api.get_hip3_tick_stats),
        ("position_snapshot_stats", "24", api.get_position_snapshot_stats),
        ("position_snapshots_BTC", "24", lambda: api.get_position_snapshots("BTC", hours=24, max_distance_pct=5)),
        ("bybit_liquidations_1h", "29", lambda: api.get_bybit_liquidations("1h")),
        ("okx_liquidations_1h", "29", lambda: api.get_okx_liquidations("1h")),
        ("imbalance_1h", "28", lambda: api.get_imbalance("1h")),
        ("btc_ticks_1h", "35", lambda: api.get_ticks("BTC", duration="1h", limit=200)),
        ("bars_BTC_1h", "35", lambda: api.get_bars_symbol("BTC", interval="1h", limit=24)),
        ("polymarket_traders", "34", api.get_poly_profitable_traders),
        ("liquidation_totals", "37", api.get_all_liquidation_totals),
        ("funding_oi_btc", "33", public_funding_oi),
    ]

    snapshot = {"timestamp": datetime.now().isoformat(timespec="seconds"), "sections": {}, "errors": {}}
    raw = {}
    for name, script, fn in tasks:
        try:
            raw[name] = fn()
            snapshot["sections"][name] = {"script": script, "data": compact(raw[name])}
            print(f"OK    {script} {name}")
        except Exception as e:
            snapshot["errors"][name] = f"{type(e).__name__}: {e}"
            print(f"FALLO {script} {name}: {e}")
            if "401" in str(e):
                raise SystemExit("401: MOONDEV_API_KEY rechazada por la API (inválida o vencida). Abortando para no saturar el rate limit.")
        time.sleep(1)  # evita 429

    # Scripts por wallet (10, 11, 36, 38): dirección tomada de los propios datos de whales/smart money
    wallet = find_address(raw.get("smart_money_rankings")) or find_address(raw.get("whales"))
    if wallet:
        snapshot["wallet_analizada"] = wallet
        for name, script, fn in [
            ("user_positions", "10", lambda: api.get_user_positions(wallet)),
            ("user_fills_60m", "11", lambda: api.get_user_fills(wallet, limit=50, minutes=60)),
            ("hl_clearinghouse", "36", lambda: api.get_hl_clearinghouse(wallet)),
            ("hl_open_orders", "36", lambda: api.get_hl_open_orders(wallet)),
        ]:
            try:
                snapshot["sections"][name] = {"script": script, "data": compact(fn())}
                print(f"OK    {script} {name}")
            except Exception as e:
                snapshot["errors"][name] = f"{type(e).__name__}: {e}"
                print(f"FALLO {script} {name}: {e}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(snapshot, indent=1, default=str))
    print(f"\nSnapshot: {out}  ({len(snapshot['sections'])} secciones, {len(snapshot['errors'])} errores)")
    return out


if __name__ == "__main__":
    main()
