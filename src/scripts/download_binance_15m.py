"""
Moon Dev - Descarga de velas de 15 minutos desde Binance (spot, API pública, sin clave)

Descarga BTC, ETH y SOL (contra USDT) desde START_DATE hasta hoy y guarda un CSV por activo en
src/data/rbi/binance_15m/<SIMBOLO>-USDT-15m.csv con el mismo formato que BTC-USD-15m.csv
(columnas 'datetime, open, high, low, close, volume,' con espacios y coma final), que es lo que
esperan los backtests de rbi_agent_v3.

Uso: python src/scripts/download_binance_15m.py
"""

from datetime import datetime, timezone
from pathlib import Path
import time

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "src" / "data" / "rbi" / "binance_15m"
URL = "https://data-api.binance.vision/api/v3/klines"
SYMBOLS = ["BTC", "ETH", "SOL"]
START_DATE = datetime(2023, 1, 1, tzinfo=timezone.utc)
INTERVAL_MS = 15 * 60 * 1000
LIMIT = 1000


def download(symbol):
    start_ms = int(START_DATE.timestamp() * 1000)
    end_ms = int(time.time() * 1000)
    rows = []
    while start_ms < end_ms:
        r = requests.get(URL, params={"symbol": f"{symbol}USDT", "interval": "15m", "startTime": start_ms, "limit": LIMIT}, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows.extend(batch)
        start_ms = batch[-1][0] + INTERVAL_MS
        time.sleep(0.1)
    # Descarta la vela en curso (aún sin cerrar)
    return [k for k in rows if k[6] < end_ms]


def save(symbol, klines):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{symbol}-USDT-15m.csv"
    with open(path, "w") as f:
        f.write("datetime, open, high, low, close, volume,\n")
        for k in klines:
            ts = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{ts}, {float(k[1])}, {float(k[2])}, {float(k[3])}, {float(k[4])}, {float(k[5])},\n")
    return path


def main():
    for symbol in SYMBOLS:
        klines = download(symbol)
        path = save(symbol, klines)
        first = datetime.fromtimestamp(klines[0][0] / 1000, tz=timezone.utc)
        last = datetime.fromtimestamp(klines[-1][0] / 1000, tz=timezone.utc)
        print(f"{symbol}: {len(klines)} velas  {first:%Y-%m-%d %H:%M} -> {last:%Y-%m-%d %H:%M} UTC  {path}")


if __name__ == "__main__":
    main()
