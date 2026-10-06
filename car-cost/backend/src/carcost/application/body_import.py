"""Règles d'import d'une variante de carrosserie (ADR-0017 §3, §6 et §11).

Pur : un `BodyModel` et la nomenclature parente donnent un plan de variante,
« aucun changement » (`None`), ou toutes les fautes à la fois. Rien n'est écrit,
rien n'est chiffré.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from fractions import Fraction

from carcost.application.body_model import BodyModel, ModelObject
from carcost.domain.bom import Bom, Edge, Part, ValuationMode
from carcost.domain.bom_validation import validate_bom

BODY_ASSEMBLY_REF = "CAR-ASSY"
_REF = re.compile(r"[A-Z0-9-]+")


@dataclass(frozen=True)
class ImportFault:
    code: str
    message: str
    object_name: str | None
    part_ref: str | None


class BodyImportRejected(Exception):
    def __init__(self, faults: list[ImportFault]) -> None:
        self.faults = tuple(sorted(faults, key=lambda f: (f.object_name or "", f.code)))
        super().__init__("; ".join(f.message for f in self.faults))


@dataclass(frozen=True)
class PartChange:
    part_ref: str
    label: str
    kind: str  # "MODIFIED" | "NEW"
    material_before: str | None
    material_after: str
    mass_before_kg: Decimal | None  # quantité de l'arête vers la matière (R1)
    mass_after_kg: Decimal

    @property
    def mass_delta_kg(self) -> Decimal:
        return self.mass_after_kg - (self.mass_before_kg or 0)


@dataclass(frozen=True)
class NewPart:
    ref: str
    label: str
    system: str
    category: str
    unit: str
    material_ref: str
    mass_kg: Decimal
    labour_minutes: Decimal
    carbon_factor: Decimal


@dataclass(frozen=True)
class VariantPlan:
    bom: Bom
    changes: tuple[PartChange, ...]
    new_parts: tuple[NewPart, ...]
    updated_parts: Mapping[str, tuple[str, Decimal]]
    cumulative: Mapping[str, Decimal]


def measured_mass(volume_m3: Fraction, density_kg_m3: Decimal) -> Decimal:
    """`arrondi₁₀⁻⁶(volume × densité)` en ROUND_HALF_UP, calculé exactement."""
    scaled = volume_m3 * Fraction(density_kg_m3) * 10**6
    rounded = math.floor(abs(scaled) + Fraction(1, 2))
    return Decimal(rounded if scaled >= 0 else -rounded).scaleb(-6)


def plan_variant(parent: Bom, model: BodyModel) -> VariantPlan | None:
    pieces = [obj for obj in model.objects if obj.spec is not None]
    if not pieces:
        raise BodyImportRejected(
            [ImportFault("INVALID_MODEL_FILE", "aucun objet carcost dans le modèle", None, None)]
        )

    faults = [fault for obj in pieces for fault in _object_faults(parent, obj)]
    groups: dict[str, list[ModelObject]] = {}
    for obj in pieces:
        if isinstance(obj.spec, Mapping) and isinstance(obj.spec.get("ref"), str):
            groups.setdefault(obj.spec["ref"], []).append(obj)
    for ref, objects in groups.items():
        first = objects[0]
        for other in objects[1:]:
            if other.mesh_index != first.mesh_index or (
                ref not in parent.parts and other.spec.get("parts") != first.spec.get("parts")
            ):
                faults.append(_fault("OCCURRENCES_DIFFER", other, "maillage ou fixations différents des autres emplacements"))
                break
    if faults:
        raise BodyImportRejected(faults)

    parts = dict(parent.parts)
    edges = list(parent.edges)
    new_parts: list[NewPart] = []
    updated: dict[str, tuple[str, Decimal]] = {}
    for ref, objects in sorted(groups.items()):
        first = objects[0]
        material = first.materials[0]
        mass = measured_mass(first.volume_m3, parent.parts[material].density_kg_m3)
        if ref in parent.parts:
            part = parent.parts[ref]
            old = dict(parent.children_of(ref))[part.material_ref]
            if material == part.material_ref and mass == old:
                continue
            parts[ref] = replace(part, material_ref=material, mass_kg=part.mass_kg - old + mass)
            edges = [
                replace(e, child_ref=material, quantity=mass)
                if (e.parent_ref, e.child_ref) == (ref, part.material_ref) else e
                for e in edges
            ]
            updated[ref] = (material, parts[ref].mass_kg)
        else:
            new = NewPart(ref, first.name or ref, "CAR", "body", "pce", material, mass, Decimal(0), Decimal(0))
            new_parts.append(new)
            parts[ref] = Part(
                ref, new.label, new.system, new.unit, ValuationMode.MANUFACTURED,
                carbon_factor=new.carbon_factor, labour_minutes=new.labour_minutes,
                mass_kg=mass, material_ref=material,
            )
            edges.append(Edge(BODY_ASSEMBLY_REF, ref, Decimal(len(objects))))
            edges.append(Edge(ref, material, mass))
            edges += [Edge(ref, fix, Decimal(str(q))) for fix, q in (first.spec.get("parts") or {}).items()]

    if not new_parts and not updated:
        return None
    bom = Bom(parent.root_ref, parts, tuple(edges))
    violations = validate_bom(bom)
    if violations:
        raise BodyImportRejected([ImportFault(v.code, v.message, None, v.part_ref) for v in violations])

    cumulative = {ref: Decimal(0) for ref in bom.parts}
    cumulative[bom.root_ref] = Decimal(1)
    for ref in bom.topological_order():
        for child, quantity in bom.children_of(ref):
            cumulative[child] += cumulative[ref] * quantity
    return VariantPlan(bom, diff_versions(parent, bom), tuple(new_parts), updated, cumulative)


def diff_versions(parent: Bom, variant: Bom) -> tuple[PartChange, ...]:
    """Les pièces à matière de `variant` nouvelles ou dont la matière ou sa
    quantité diffèrent de `parent`, triées par référence."""
    changes = []
    for ref, part in sorted(variant.parts.items()):
        if part.material_ref is None or part.is_purchased:
            continue
        after = dict(variant.children_of(ref))[part.material_ref]
        before_part = parent.parts.get(ref)
        if before_part is None:
            changes.append(PartChange(ref, part.label, "NEW", None, part.material_ref, None, after))
            continue
        before = dict(parent.children_of(ref))[before_part.material_ref]
        if (before_part.material_ref, before) != (part.material_ref, after):
            changes.append(
                PartChange(ref, part.label, "MODIFIED", before_part.material_ref, part.material_ref, before, after)
            )
    return tuple(changes)


def _fault(code: str, obj: ModelObject, message: str) -> ImportFault:
    ref = obj.spec.get("ref") if isinstance(obj.spec, Mapping) else None
    return ImportFault(code, f"{obj.name or ref} : {message}", obj.name, ref or None)


def _object_faults(parent: Bom, obj: ModelObject) -> list[ImportFault]:
    spec = obj.spec
    if not isinstance(spec, Mapping):
        return [_fault("INVALID_SPEC", obj, "extras.carcost n'est pas un objet")]
    ref = spec.get("ref")
    if not ref or not obj.materials:
        return [_fault("MISSING_SPEC", obj, "référence ou matériau manquant")]

    invalid = []
    if not isinstance(ref, str) or not _REF.fullmatch(ref):
        invalid.append(f"référence {ref!r} hors [A-Z0-9-]")
    fixations = spec.get("parts") or {}
    if not isinstance(fixations, Mapping):
        invalid.append("parts n'est pas un objet")
    else:
        for fix, quantity in fixations.items():
            try:
                valid = Decimal(str(quantity)).is_finite() and Decimal(str(quantity)) > 0
            except InvalidOperation:
                valid = False
            if not valid:
                invalid.append(f"quantité {quantity!r} de {fix} non décimale ou ≤ 0")
    if len(obj.materials) > 1:
        invalid.append(f"plusieurs matériaux {list(obj.materials)}")
    if invalid:
        return [_fault("INVALID_SPEC", obj, "; ".join(invalid))]

    faults = []
    if not obj.is_closed:
        faults.append(_fault("MESH_NOT_CLOSED", obj, "maillage non fermé"))
    elif obj.volume_m3 <= 0:
        faults.append(_fault("NON_POSITIVE_VOLUME", obj, "volume nul ou négatif (normales inversées ?)"))

    material = obj.materials[0]
    if material not in parent.parts:
        faults.append(_fault("UNKNOWN_MATERIAL", obj, f"matière {material} inconnue"))
    elif parent.parts[material].density_kg_m3 is None:
        faults.append(_fault("MATERIAL_WITHOUT_DENSITY", obj, f"matière {material} sans densité"))

    part = parent.parts.get(ref)
    if part is not None:
        if part.is_purchased:
            faults.append(_fault("REF_IS_PURCHASED", obj, f"{ref} est une pièce achetée"))
        elif part.material_ref is None:
            faults.append(_fault("NOT_A_MATERIAL_PIECE", obj, f"{ref} n'a pas de matière"))
        return faults
    for fix in fixations:
        if fix not in parent.parts:
            faults.append(_fault("UNKNOWN_PART", obj, f"fixation {fix} inconnue"))
        elif not parent.parts[fix].is_purchased:
            faults.append(_fault("NOT_PURCHASED", obj, f"fixation {fix} fabriquée"))
    return faults
