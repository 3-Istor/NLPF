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

# Les couches intérieures, et ce qu'elles n'ont pas le droit de connaître.
INNER_LAYERS = {
    DOMAIN: ("carcost.application", "carcost.infrastructure"),
    APPLICATION: ("carcost.infrastructure",),
}


def module_name(module: Path, src: Path = SRC) -> str:
    parts = module.relative_to(src.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def imported_modules(module: Path, src: Path = SRC) -> set[str]:
    """Les modules importés, nommés en absolu.

    Un import relatif est résolu : `from ..infrastructure import x` doit
    tomber sous la même règle que `from carcost.infrastructure import x`,
    sinon le contournement tient en deux points.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    package = module_name(module, src).split(".")
    if module.name != "__init__.py":
        package = package[:-1]

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                anchor = package[: len(package) - (node.level - 1)]
                base = ".".join(anchor + ([node.module] if node.module else []))
            names.add(base)
            # `from .. import infrastructure` importe un module, pas un nom.
            names.update(f"{base}.{alias.name}" for alias in node.names)
    return names


def imported_roots(module: Path, src: Path = SRC) -> set[str]:
    return {name.split(".")[0] for name in imported_modules(module, src)}


def dynamic_imports(module: Path) -> list[str]:
    """Un import par chaîne échappe à toute lecture statique : on l'interdit."""
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if "importlib" in imported_roots_of(node):
                found.append(f"ligne {node.lineno} : importlib")
        elif isinstance(node, ast.Name) and node.id == "__import__":
            found.append(f"ligne {node.lineno} : __import__")
    return found


def imported_roots_of(node: ast.Import | ast.ImportFrom) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name.split(".")[0] for alias in node.names}
    return {node.module.split(".")[0]} if node.level == 0 and node.module else set()


def outer_layer_imports(module: Path, forbidden: tuple[str, ...], src: Path = SRC) -> set[str]:
    return {
        name
        for name in imported_modules(module, src)
        if any(name == layer or name.startswith(layer + ".") for layer in forbidden)
    }


INNER_MODULES = sorted(
    (module, forbidden)
    for layer, forbidden in INNER_LAYERS.items()
    for module in layer.rglob("*.py")
)


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


@pytest.mark.parametrize(
    ("module", "forbidden"),
    INNER_MODULES,
    ids=lambda value: value.name if isinstance(value, Path) else "",
)
def test_dependencies_only_point_inwards(module: Path, forbidden: tuple[str, ...]) -> None:
    """La flèche de dépendance ne va que vers l'intérieur, en relatif comme en absolu."""
    offenders = outer_layer_imports(module, forbidden)

    assert not offenders, (
        f"{module_name(module)} importe {sorted(offenders)} : une couche "
        f"intérieure ne connaît pas celles qui l'entourent"
    )


@pytest.mark.parametrize(
    ("module", "forbidden"),
    INNER_MODULES,
    ids=lambda value: value.name if isinstance(value, Path) else "",
)
def test_inner_layers_import_nothing_dynamically(module: Path, forbidden: tuple[str, ...]) -> None:
    assert not dynamic_imports(module), (
        f"{module_name(module)} : {dynamic_imports(module)}"
    )


# Les garde-fous du garde-fou : un test qui ne peut pas échouer ne vérifie rien.


@pytest.fixture
def fake_src(tmp_path: Path) -> Path:
    src = tmp_path / "carcost"
    for layer in ("domain", "application", "infrastructure"):
        (src / layer).mkdir(parents=True)
        (src / layer / "__init__.py").write_text("", encoding="utf-8")
    return src


def test_the_guard_itself_is_not_vacuous(tmp_path: Path) -> None:
    culprit = tmp_path / "leaky.py"
    culprit.write_text("import sqlalchemy\n", encoding="utf-8")

    assert imported_roots(culprit, tmp_path) & FORBIDDEN == {"sqlalchemy"}


@pytest.mark.parametrize(
    "line",
    [
        "from ..infrastructure.postgres import bom\n",
        "from .. import infrastructure\n",
        "from carcost.infrastructure import startup\n",
        "import carcost.infrastructure.api\n",
    ],
)
def test_the_guard_sees_an_application_reaching_outwards(fake_src: Path, line: str) -> None:
    culprit = fake_src / "application" / "leaky.py"
    culprit.write_text(line, encoding="utf-8")

    assert outer_layer_imports(culprit, ("carcost.infrastructure",), fake_src)


@pytest.mark.parametrize(
    "line",
    [
        "from ..application.ports import BomRepository\n",
        "from carcost.application import run_calculation\n",
        "import carcost.infrastructure\n",
    ],
)
def test_the_guard_sees_a_domain_reaching_outwards(fake_src: Path, line: str) -> None:
    culprit = fake_src / "domain" / "leaky.py"
    culprit.write_text(line, encoding="utf-8")

    assert outer_layer_imports(
        culprit, ("carcost.application", "carcost.infrastructure"), fake_src
    )


def test_the_guard_lets_a_sibling_import_through(fake_src: Path) -> None:
    """Sans ce cas, une règle qui refuse tout passerait pour une règle juste."""
    module = fake_src / "domain" / "engine.py"
    module.write_text("from .bom import Bom\nfrom . import prices\n", encoding="utf-8")

    assert not outer_layer_imports(
        module, ("carcost.application", "carcost.infrastructure"), fake_src
    )


@pytest.mark.parametrize(
    "line",
    [
        "import importlib\n",
        "from importlib import import_module\n",
        "x = __import__('carcost.infrastructure')\n",
    ],
)
def test_the_guard_sees_a_dynamic_import(tmp_path: Path, line: str) -> None:
    culprit = tmp_path / "leaky.py"
    culprit.write_text(line, encoding="utf-8")

    assert dynamic_imports(culprit)
