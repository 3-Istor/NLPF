"""API de prix simulée.

Ce n'est pas notre produit : c'est le service que le produit interroge, et que
nous avons écrit pour pouvoir **le faire tomber à la demande**. La panne se
déclenche par un en-tête, jamais au hasard : une démonstration doit être
reproductible.

    python price-api/mock_price_api.py --port 8099 --year-minutes 40

    GET /prices?refs=FIX-M6-16,ELE-ECU-MAIN&currency=EUR
    X-Mock-Failure: none | timeout | outlier | missing | garbage

    GET /history?ref=VALH-BOM-0006&currency=EUR

Il sert les catalogues des quatre nomenclatures (le Multipla et les trois
Valhalla) et fait varier leurs prix sur une année simulée (`simulation.py`).
`/history` rend cette année jour par jour, pour le graphe d'une pièce.

Bibliothèque standard seule : un simulateur ne mérite pas une dépendance, et
celui-ci doit pouvoir démarrer sur n'importe quelle machine de l'équipe.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlparse

# Le module se charge aussi par chemin de fichier (tests du client HTTP) : son
# voisin `simulation` doit se trouver sans paquet.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from simulation import Market  # noqa: E402

SLOW_RESPONSE_SECONDS = 30.0
HERE = Path(__file__).resolve().parent
INDICES = HERE / "data" / "price_indices.json"


def default_catalogs(seeds: Path) -> list[Path]:
    """Le Multipla, puis chaque Valhalla."""
    return [seeds / "price_catalog.json", *sorted(seeds.glob("valhalla/*/price_catalog.json"))]


class PriceCatalog:
    def __init__(self, paths: Path | Iterable[Path], market: Market | None = None) -> None:
        paths = [paths] if isinstance(paths, Path) else list(paths)
        self.prices: dict[str, dict] = {}
        for path in paths:
            document = json.loads(path.read_text(encoding="utf-8"))
            overlap = self.prices.keys() & document["prices"].keys()
            if overlap:
                # Deux catalogues qui cotent la même référence : l'un des deux
                # mentirait, et rien ne dit lequel.
                raise ValueError(f"{path} : références déjà cotées {sorted(overlap)[:5]}")
            self.prices.update(document["prices"])
        self.market = market or Market(INDICES)

    def quote(self, ref: str, currency: str, position) -> dict | None:
        """La cotation à `position` : un appel = un instant, choisi par
        l'appelant, sinon un lot de 600 pièces s'étalerait sur des heures de
        marché simulé."""
        entry = self.prices.get(ref)
        if entry is None or currency not in entry["prices"]:
            return None
        return {
            "ref": ref,
            "currency": currency,
            "price": str(self.market.price(entry, currency, position, ref)),
            "per": entry["price_per"],
            "unit": entry["unit"],
        }

    def history(self, ref: str, currency: str) -> dict | None:
        entry = self.prices.get(ref)
        if entry is None or currency not in entry["prices"]:
            return None
        return {
            "ref": ref,
            "currency": currency,
            "per": entry["price_per"],
            "unit": entry["unit"],
            "profile": entry.get("profile"),
            "drivers": entry.get("drivers") or {},
            "origin_currency": entry.get("origin_currency"),
            "reference": entry["prices"][currency]["reference"],
            **self.market.history(entry, currency, ref),
        }


class Handler(BaseHTTPRequestHandler):
    catalog: PriceCatalog
    slow_seconds: float = SLOW_RESPONSE_SECONDS

    def do_GET(self) -> None:  # noqa: N802 - imposé par BaseHTTPRequestHandler
        route = urlparse(self.path)
        if route.path == "/history":
            self._history(parse_qs(route.query))
            return
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

        position = self.catalog.market.position()
        quotes = [
            q for q in (self.catalog.quote(ref, currency, position) for ref in refs) if q
        ]
        quotes = self._derail(quotes, failure)
        self._send(
            200,
            {
                # La date simulée de la cotation, pas l'heure réelle.
                "as_of": self.catalog.market.moment(position).isoformat(),
                "currency": currency,
                "is_synthetic": True,
                "prices": quotes,
            },
        )

    def _history(self, query: dict) -> None:
        ref = query.get("ref", [""])[0]
        currency = query.get("currency", ["EUR"])[0]
        history = self.catalog.history(ref, currency)
        if history is None:
            self._send(
                404,
                {"error": {"code": "UNKNOWN_REF", "message": f"{ref} non coté en {currency}"}},
            )
            return
        self._send(200, {"is_synthetic": True, **history})

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
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # Panne « timeout » : le client a abandonné pendant le sommeil, et ce
            # thread daemon répond des secondes plus tard à une connexion qui
            # n'existe plus. Non rattrapée, l'exception s'imprime sur stderr
            # depuis un thread qui peut encore tourner à la fermeture de
            # l'interpréteur (fin de suite de tests) et fait planter le process.
            pass

    def log_message(self, *args) -> None:  # noqa: D102 - silence en test
        pass


def make_server(
    catalog_path: Path | Iterable[Path], port: int = 0, slow_seconds: float | None = None,
    host: str = "127.0.0.1", market: Market | None = None,
):
    handler = type(
        "BoundHandler",
        (Handler,),
        {
            "catalog": PriceCatalog(catalog_path, market),
            "slow_seconds": SLOW_RESPONSE_SECONDS if slow_seconds is None else slow_seconds,
        },
    )
    return ThreadingHTTPServer((host, port), handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--catalog", type=Path, action="append",
        help="catalogue à servir (répétable) ; par défaut tous ceux de --seeds",
    )
    parser.add_argument("--seeds", type=Path, default=Path("seeds"))
    parser.add_argument(
        "--year-minutes", type=float, default=40.0,
        help="durée réelle d'une année simulée ; 0 fige les prix à leur référence",
    )
    arguments = parser.parse_args()

    catalogs = arguments.catalog or default_catalogs(arguments.seeds)
    market = Market(INDICES, year_minutes=arguments.year_minutes or None)
    server = make_server(catalogs, arguments.port, host=arguments.host, market=market)
    host, port = server.server_address[:2]
    print(
        f"API de prix simulée sur http://{host}:{port}/prices — {len(catalogs)} "
        f"catalogue(s), une année en {arguments.year_minutes:g} min (données synthétiques)"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
