"""Ce qu'une ligne d'arbre affiche une fois qu'un calcul existe.

Une ligne porte deux montants, et les confondre revient à compter deux fois :

  - `rolled_up_contribution` : ce que pèse **cette occurrence**, enfants
    compris. C'est la question qu'on pose en dépliant — « ce moteur-là, il me
    coûte combien ? ». Ces valeurs ne se somment **pas** entre niveaux.
  - `own_contribution` : la contribution propre de la pièce au véhicule. C'est
    celle-là, et elle seule, dont la somme égale le total.

Le marquage des modifications se calcule ici aussi : le navigateur ne connaît
pas le graphe et ne peut pas savoir quels parents remonter (ADR-0009).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..domain.bom import Bom
from .browse_bom import PATH_SEPARATOR, PathNotFound, TreeNode
from .run_calculation import Calculation
from .scenario import Scenario


@dataclass(frozen=True)
class CostedNode:
    node: TreeNode
    #: Combien il en faut pour un véhicule *par ce chemin* : le produit des
    #: quantités d'arêtes depuis la racine.
    quantity_on_path: Decimal
    unit_cost: Decimal | None
    own_unit_cost: Decimal | None
    rolled_up_contribution: Decimal | None
    own_contribution: Decimal | None
    price_status: str
    is_modified: bool
    has_modified_descendant: bool


@dataclass(frozen=True)
class Marks:
    modified: frozenset[str]
    with_modified_descendant: frozenset[str]

    def is_modified(self, part_ref: str) -> bool:
        return part_ref in self.modified

    def has_modified_descendant(self, part_ref: str) -> bool:
        return part_ref in self.with_modified_descendant


def path_quantity(bom: Bom, path: str) -> Decimal:
    """Le produit des quantités d'arêtes le long du chemin.

    Ce n'est pas la quantité cumulée de la pièce : c'est ce que ce chemin-là
    apporte. Une vis peut être à 8 ici et à 15 ailleurs, pour 23 en tout.
    """
    refs = path.split(PATH_SEPARATOR)
    quantity = Decimal(1)
    for parent_ref, child_ref in zip(refs, refs[1:]):
        for candidate, edge_quantity in bom.children_of(parent_ref):
            if candidate == child_ref:
                quantity *= edge_quantity
                break
        else:
            raise PathNotFound(
                f"{path} : aucune arête ne va de {parent_ref} à {child_ref}"
            )
    return quantity


def marks_of(bom: Bom, scenario: Scenario) -> Marks:
    """Quelles pièces sont réglées, et lesquelles en contiennent une.

    La remontée jusqu'à la racine n'est pas un ornement : sans elle, un réglage
    posé sur une vis est introuvable dans une nomenclature de 474 pièces.
    """
    modified = {parameter.part_ref for parameter in scenario.parameters}

    touched: set[str] = set()
    for ref in reversed(bom.topological_order()):
        for child_ref, _ in bom.children_of(ref):
            if child_ref in modified or child_ref in touched:
                touched.add(ref)
                break

    return Marks(
        modified=frozenset(modified), with_modified_descendant=frozenset(touched)
    )


def with_costs(
    bom: Bom,
    nodes: tuple[TreeNode, ...],
    calculation: Calculation,
    scenario: Scenario,
) -> tuple[CostedNode, ...]:
    by_ref = {line.part_ref: line for line in calculation.lines}
    marks = marks_of(bom, scenario)

    costed = []
    for node in nodes:
        line = by_ref.get(node.part_ref)
        quantity = path_quantity(bom, node.path)
        unit_cost = line.full_unit_cost if line else None
        own_unit_cost = line.own_unit_cost if line else None

        costed.append(
            CostedNode(
                node=node,
                quantity_on_path=quantity,
                unit_cost=unit_cost,
                own_unit_cost=own_unit_cost,
                rolled_up_contribution=(
                    quantity * unit_cost if unit_cost is not None else None
                ),
                own_contribution=(
                    quantity * own_unit_cost if own_unit_cost is not None else None
                ),
                # Un prix manquant se dit ; il ne se remplace pas par zéro, qui
                # se lirait comme « cette pièce est gratuite ». Un prix de repli
                # se dit aussi : sur la ligne, pas seulement sur le total.
                price_status=calculation.price_status_of(node.part_ref).value,
                is_modified=marks.is_modified(node.part_ref),
                has_modified_descendant=marks.has_modified_descendant(node.part_ref),
            )
        )
    return tuple(costed)
