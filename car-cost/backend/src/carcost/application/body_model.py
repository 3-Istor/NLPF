"""Ce que le lecteur de modèle 3D extrait d'un fichier (ADR-0017 §2 et §3).

Types purs : aucune règle d'import ici, seulement ce que le fichier contient.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class ModelObject:
    node_index: int
    name: str  # node.name, "" si absent
    mesh_index: int
    materials: tuple[str, ...]  # noms distincts des matériaux des primitives, triés
    spec: Mapping | None  # node["extras"]["carcost"] tel quel ; None => décor
    volume_m3: Fraction  # Σ p1·(p2×p3)/6 dans le repère monde, exact
    is_closed: bool  # chaque arête est partagée par exactement deux triangles


@dataclass(frozen=True)
class BodyModel:
    objects: tuple[ModelObject, ...]  # ordre des nœuds du fichier


class ModelFileRejected(Exception):
    """Fichier illisible : "INVALID_MODEL_FILE" ou "UNSUPPORTED_EXTENSION"."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
