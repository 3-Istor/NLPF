"""Le domaine ne connaît ni écran, ni réseau, ni base (ADR-0004).

Cette règle est vérifiée ici, mécaniquement, parce qu'une règle qui repose sur
la discipline finit par tomber un soir de veille de soutenance.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "carcost"
DOMAIN = SRC / "domain"
APPLICATION = SRC / "application"

FORBIDDEN = {
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
    "psycopg",
    "psycopg2",
    "httpx",
    "requests",
    "aiohttp",
    "pydantic",
    "redis",
    # Le réseau non plus : « ni écran, ni réseau, ni fournisseur de prix ».
    "urllib",
    "socket",
    "http",
    "sqlite3",
}


def imported_roots(module: Path) -> set[str]:
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize(
    "module", sorted(DOMAIN.rglob("*.py")), ids=lambda p: p.name
)
def test_domain_imports_no_infrastructure(module: Path) -> None:
    offenders = imported_roots(module) & FORBIDDEN

    assert not offenders, (
        f"{module.name} importe {sorted(offenders)} : le moteur doit rester "
        f"testable sans base ni réseau"
    )


@pytest.mark.parametrize(
    "module", sorted(APPLICATION.rglob("*.py")), ids=lambda p: p.name
)
def test_application_imports_no_infrastructure(module: Path) -> None:
    """Les cas d'usage déclarent des ports ; ils n'en connaissent aucun client."""
    offenders = imported_roots(module) & FORBIDDEN

    assert not offenders, (
        f"{module.name} importe {sorted(offenders)} : un cas d'usage nomme ce "
        f"dont il a besoin, pas qui le lui fournit"
    )


def test_the_domain_never_imports_the_application_or_the_infrastructure() -> None:
    """La flèche de dépendance ne va que vers l'intérieur."""
    for module in DOMAIN.rglob("*.py"):
        text = module.read_text(encoding="utf-8")

        assert "from ..application" not in text, module.name
        assert "from ..infrastructure" not in text, module.name


def test_the_guard_itself_is_not_vacuous(tmp_path: Path) -> None:
    """Un test qui ne peut pas échouer ne vérifie rien."""
    culprit = tmp_path / "leaky.py"
    culprit.write_text("import sqlalchemy\n", encoding="utf-8")

    assert imported_roots(culprit) & FORBIDDEN == {"sqlalchemy"}
