"""L'adaptateur Postgres, contre une vraie base chargée.

Ces tests sont ignorés si Postgres n'est pas joignable : la suite doit rester
verte hors ligne. Quand ils tournent, ils vérifient que le graphe relu en base
est bien celui du jeu de données — pas un graphe plausible.

    docker compose up -d
    PYTHONPATH=backend/src python3 -m carcost.infrastructure seeds \\
      | docker compose exec -T db psql -U 3istor -d 3istor -q
    backend/.venv/Scripts/python -m pytest backend/tests/integration
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from carcost.application.browse_bom import children_of_path, where_used
from carcost.application.ports import BomVersionNotFound
from carcost.domain.engine import compute
from carcost.domain.scenario import CalculationInput

DSN = os.environ.get(
    "CARCOST_DSN", "postgresql://3istor:3istor@127.0.0.1:5432/3istor"
)
VERSION = os.environ.get("CARCOST_BOM_VERSION", "bom-multipla-2026-09-22")


@pytest.fixture(scope="module")
def repository():
    psycopg = pytest.importorskip("psycopg")
    from carcost.infrastructure.postgres_bom_repository import PostgresBomRepository

    try:
        with psycopg.connect(DSN, connect_timeout=3):
            pass
    except Exception as unreachable:  # noqa: BLE001 - on saute, on n'échoue pas
        pytest.skip(f"Postgres injoignable : {unreachable}")
    return PostgresBomRepository(DSN)


@pytest.fixture(scope="module")
def multipla(repository):
    return repository.load(VERSION)


def test_the_loaded_graph_has_the_expected_shape(multipla):
    assert len(multipla.parts) == 474
    assert len(multipla.edges) == 689
    assert multipla.root_ref == "VEH-MULTIPLA-16V"


def test_the_graph_is_acyclic_as_read_back(multipla):
    assert len(multipla.topological_order()) == len(multipla.parts)


def test_unfolding_the_root_gives_the_seven_systems(multipla):
    page = children_of_path(multipla, "VEH-MULTIPLA-16V")

    assert page.total == 7
    assert "GMP-ASSY" in {item.part_ref for item in page.items}


def test_the_wheel_shows_three_numbers_that_must_not_be_confused(multipla):
    """La roue complète est montée cinq fois, à trois endroits, sous deux
    parents. Sur un arbre ces trois nombres seraient égaux ; ici ils valent
    3, 5 et 2, et c'est exactement ce que l'écran doit savoir distinguer.

    Chemins : train avant (×2), train arrière (×2), logement de secours (×1).
    """
    page = where_used(multipla, "CHS-WHEEL-ASSY")

    assert page.total == 3, "trois chemins mènent à la roue"
    assert sum(
        (occurrence.quantity_on_path for occurrence in page.items), Decimal(0)
    ) == Decimal("5"), "mais il en faut cinq par véhicule"
    assert {occurrence.quantity_on_path for occurrence in page.items} == {
        Decimal("1"),
        Decimal("2"),
    }


def test_the_engine_agrees_with_the_control_values_read_from_the_database(multipla):
    """Le moteur, nourri par la base et non par le fichier, retrouve les mêmes
    quantités cumulées."""
    prices = {
        ref: Decimal("1")
        for ref, part in multipla.parts.items()
        if part.is_purchased
    }
    result = compute(
        CalculationInput(
            bom=multipla,
            unit_prices=prices,
            labour_rate=Decimal("42.00"),
            active_rules=frozenset({"labour"}),
        )
    )

    assert result.line("ENG-PISTON-RING").cumulative_quantity == Decimal("12")
    assert result.line("CHS-TIRE-185-65-15").cumulative_quantity == Decimal("5")
    assert result.line("INT-SEAT-ASSY").cumulative_quantity == Decimal("6")


def test_an_unknown_version_is_refused(repository):
    with pytest.raises(BomVersionNotFound):
        repository.load("bom-inexistante")
