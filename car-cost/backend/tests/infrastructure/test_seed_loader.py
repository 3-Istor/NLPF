"""Le chargeur du jeu de données.

Il ne parle pas à Postgres : il **émet** le flux SQL que psql exécutera. Cela le
rend testable sans base, et fait du contrôle d'intégrité une condition à
l'émission — un jeu de données invalide ne produit aucun SQL du tout.
"""

from __future__ import annotations

import pytest

from carcost.infrastructure.seed_loader import SeedRejected, build_load_script


def rows(**overrides):
    """Un jeu minimal et valide : racine, ensemble, vis partagée."""
    parts = [
        _part("ROOT", "manufactured", labour="10", cumulative="1"),
        _part("SUBASM", "manufactured", labour="5", cumulative="2"),
        _part("SCREW", "purchased", price="0.500000", cumulative="14"),
    ]
    edges = [
        _edge("ROOT", "SUBASM", "2"),
        _edge("ROOT", "SCREW", "4"),
        _edge("SUBASM", "SCREW", "5"),
    ]
    return {"parts": overrides.get("parts", parts), "edges": overrides.get("edges", edges)}


def _part(ref, mode, *, labour="", price="", cumulative="1", label=None):
    return {
        "bom_version_id": "bom-test",
        "part_ref": ref,
        "label": label if label is not None else f"Pièce {ref}",
        "category": "engine" if mode == "manufactured" else "fastener",
        "system": "GMP",
        "unit": "pce",
        "valuation_mode": mode,
        "labour_minutes": labour,
        "base_price_eur": price,
        "price_per": "1",
        "material_ref": "",
        "mass_kg": "0.100000",
        "carbon_factor_kg_co2e_per_unit": "0.010000",
        "expected_cumulative_quantity": cumulative,
    }


def _edge(parent, child, quantity):
    return {
        "bom_version_id": "bom-test",
        "parent_ref": parent,
        "child_ref": child,
        "parent_valuation_mode": "manufactured",
        "quantity": quantity,
        "unit": "pce",
    }


METADATA = {
    "bom_version_id": "bom-test",
    "vehicle": "Fiat Multipla 1.6 16V",
    "root_part_ref": "ROOT",
    "generator_version": "1.0.0",
    "seed_checksum": "sha256:abc",
    "is_synthetic": True,
}


def script(**overrides) -> str:
    data = rows(**overrides)
    return build_load_script(
        metadata=overrides.get("metadata", METADATA),
        parts=data["parts"],
        edges=data["edges"],
        suppliers=overrides.get("suppliers", {"suppliers": [], "part_suppliers": []}),
    )


class TestEmittedScript:
    def test_is_one_transaction(self):
        sql = script()

        assert sql.startswith("BEGIN;")
        assert sql.rstrip().endswith("COMMIT;")

    def test_uses_copy_from_stdin(self):
        sql = script()

        assert "COPY part (" in sql
        assert "FROM STDIN" in sql
        assert sql.count("\n\\.\n") >= 2  # une marque de fin par bloc COPY

    def test_carries_the_synthetic_flag(self):
        """Une donnée inventée le dit jusque dans la base."""
        insert = script().split("\n")[2]

        assert insert.startswith("INSERT INTO bom_version")
        assert ", true, " in insert

    def test_validated_at_is_set_last_and_only_once(self):
        sql = script()

        assert sql.count("validated_at") == 1
        assert sql.index("validated_at") > sql.index("COPY bom_edge")

    def test_escapes_what_copy_would_misread(self):
        parts = rows()["parts"]
        parts[0] = _part("ROOT", "manufactured", labour="10", label="Vis\tM6\\16")

        sql = script(parts=parts)

        assert "Vis\\tM6\\\\16" in sql

    def test_empty_fields_become_sql_null(self):
        """Une pièce fabriquée n'a pas de prix : la colonne doit valoir NULL,
        pas la chaîne vide, sinon la contrainte de valorisation ne joue pas."""
        sql = script()

        assert "\\N" in sql


class TestRefusals:
    def test_a_cycle_produces_no_sql(self):
        edges = [_edge("ROOT", "SUBASM", "1"), _edge("SUBASM", "ROOT", "1")]

        with pytest.raises(SeedRejected, match="cycle"):
            script(edges=edges)

    def test_an_orphan_part_is_refused(self):
        parts = rows()["parts"] + [_part("LOST", "purchased", price="1.000000")]

        with pytest.raises(SeedRejected, match="orphelin"):
            script(parts=parts)

    def test_a_wrong_control_value_is_refused(self):
        """4 + 2×5 = 14. Si le fichier annonce autre chose, il a tort."""
        parts = rows()["parts"]
        parts[2] = _part("SCREW", "purchased", price="0.500000", cumulative="13")

        with pytest.raises(SeedRejected, match="quantité cumulée"):
            script(parts=parts)

    def test_a_purchased_part_with_children_is_refused(self):
        """Une vis qui contiendrait quelque chose : son coût serait compté deux
        fois. Le sous-ensemble ajouté est une feuille, pour que le refus vienne
        bien de la valorisation et pas d'un cycle."""
        parts = rows()["parts"] + [
            _part("TIP", "purchased", price="0.100000", cumulative="14")
        ]
        edges = rows()["edges"] + [_edge("SCREW", "TIP", "1")]

        with pytest.raises(SeedRejected, match="achetée"):
            script(parts=parts, edges=edges)

    def test_a_manufactured_part_with_a_price_is_refused(self):
        parts = rows()["parts"]
        parts[1] = _part("SUBASM", "manufactured", labour="5", price="9.000000",
                         cumulative="2")

        with pytest.raises(SeedRejected, match="prix"):
            script(parts=parts)

    def test_an_unknown_root_is_refused(self):
        with pytest.raises(SeedRejected, match="racine"):
            script(metadata={**METADATA, "root_part_ref": "NOWHERE"})
