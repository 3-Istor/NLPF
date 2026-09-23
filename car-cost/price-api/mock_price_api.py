"""API de prix simulée.

Ce n'est pas notre produit : c'est le service que le produit interroge, et que
nous avons écrit pour pouvoir **le faire tomber à la demande**. La panne se
déclenche par un en-tête, jamais au hasard : une démonstration doit être
reproductible.

    python price-api/mock_price_api.py --port 8099 --catalog seeds/price_catalog.json

    GET /prices?refs=FIX-M6-16,ELE-ECU-MAIN&currency=EUR
    X-Mock-Failure: none | timeout | outlier | missing | garbage

Bibliothèque standard seule : un simulateur ne mérite pas une dépendance, et
celui-ci doit pouvoir démarrer sur n'importe quelle machine de l'équipe.
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SLOW_RESPONSE_SECONDS = 30.0


class PriceCatalog:
    def __init__(self, path: Path) -> None:
        document = json.loads(path.read_text(encoding="utf-8"))
        self.as_of = document["metadata"]["dataset_date"]
        self.prices = document["prices"]

    def quote(self, ref: str, currency: str) -> dict | None:
        entry = self.prices.get(ref)
        if entry is None or currency not in entry["prices"]:
            return None
        return {
            "ref": ref,
            "currency": currency,
            "price": entry["prices"][currency]["reference"],
            "per": entry["price_per"],
            "unit": entry["unit"],
        }


class Handler(BaseHTTPRequestHandler):
    catalog: PriceCatalog
    slow_seconds: float = SLOW_RESPONSE_SECONDS

    def do_GET(self) -> None:  # noqa: N802 - imposé par BaseHTTPRequestHandler
        route = urlparse(self.path)
        if route.path != "/prices":
            self._send(404, {"error": {"code": "NOT_FOUND", "message": route.path}})
            return

        failure = self.headers.get("X-Mock-Failure", "none").lower()
        if failure == "timeout":
            # On ne ferme pas la connexion : on ne répond simplement pas. C'est
            # la panne que le client doit distinguer d'un refus net.
            time.sleep(self.slow_seconds)

        query = parse_qs(route.query)
        refs = [r for r in query.get("refs", [""])[0].split(",") if r]
        currency = query.get("currency", ["EUR"])[0]

        quotes = [q for q in (self.catalog.quote(ref, currency) for ref in refs) if q]
        quotes = self._derail(quotes, failure)
        self._send(
            200,
            {
                "as_of": self.catalog.as_of,
                "currency": currency,
                "is_synthetic": True,
                "prices": quotes,
            },
        )

    @staticmethod
    def _derail(quotes: list[dict], failure: str) -> list[dict]:
        """Les pannes que le produit doit savoir encaisser.

        Elles portent sur la PREMIÈRE pièce demandée : une panne qui frappe
        tout le lot se remarque trop facilement, alors que le cas difficile est
        celui d'une seule ligne fausse au milieu de trois cents justes.
        """
        if not quotes or failure in ("none", "timeout"):
            return quotes
        if failure == "outlier":
            quotes[0] = {**quotes[0], "price": "-42.000000"}
        elif failure == "garbage":
            quotes[0] = {**quotes[0], "price": "indisponible"}
        elif failure == "missing":
            quotes = quotes[1:]
        return quotes

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # noqa: D102 - silence en test
        pass


def make_server(catalog_path: Path, port: int = 0, slow_seconds: float | None = None):
    handler = type(
        "BoundHandler",
        (Handler,),
        {
            "catalog": PriceCatalog(catalog_path),
            "slow_seconds": SLOW_RESPONSE_SECONDS if slow_seconds is None else slow_seconds,
        },
    )
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--catalog", type=Path, default=Path("seeds/price_catalog.json"))
    arguments = parser.parse_args()

    server = make_server(arguments.catalog, arguments.port)
    host, port = server.server_address[:2]
    print(f"API de prix simulée sur http://{host}:{port}/prices (données synthétiques)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
