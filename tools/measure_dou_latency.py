"""Mede a latência real da API de busca do DOU (40 consultas com termos da rotina de teste).

Uso:
    uv run python tools/measure_dou_latency.py
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.local.rotina_teste import test_terms

URL = "https://www.in.gov.br/consulta/-/buscar/dou"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
}


def main() -> int:
    roots = [f"{c[:2]}.{c[2:5]}.{c[5:8]}" for c in test_terms()]
    queries = (roots * 3)[:40]
    latencies: list[float] = []
    errors = 0

    for idx, q in enumerate(queries, start=1):
        payload = {
            "q": q,
            "exactDate": "personalizado",
            "publishFrom": "03-11-2026",
            "publishTo": "23-11-2026",
            "sortType": "0",
            "s": ["do1", "do2", "do3", "doe"],
        }
        t0 = time.perf_counter()
        try:
            resp = requests.get(URL, params=payload, headers=HEADERS, timeout=35)
            elapsed = time.perf_counter() - t0
            latencies.append(elapsed)
            print(f"[{idx:02d}/40] q={q} status={resp.status_code} elapsed={elapsed:.3f}s")
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            errors += 1
            latencies.append(elapsed)
            print(f"[{idx:02d}/40] q={q} ERROR={exc} elapsed={elapsed:.3f}s")

    sorted_lat = sorted(latencies)
    p50 = statistics.median(sorted_lat)
    p95_idx = min(len(sorted_lat) - 1, int(0.95 * (len(sorted_lat) - 1) + 0.5))
    p95 = sorted_lat[p95_idx]
    mx = sorted_lat[-1]
    print(f"\nResumo (40 consultas, {errors} erro(s)): p50={p50:.3f}s | p95={p95:.3f}s | max={mx:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
