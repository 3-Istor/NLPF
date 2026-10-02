"""Le démarrage préserve les données et refuse une préparation incomplète."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from carcost.infrastructure import startup
from carcost.infrastructure.seed_loader import SeedRejected


@pytest.fixture
def prepared(monkeypatch):
    connection = MagicMock()
    monkeypatch.setattr(startup.psycopg, "connect", Mock(return_value=connection))
    queries = connection.__enter__.return_value.execute.return_value.fetchone
    seeds = {"metadata": {"bom_version_id": "test-version"}}
    monkeypatch.setattr(startup, "read_seeds", Mock(return_value=seeds))
    monkeypatch.setattr(startup, "seed_directories", Mock(return_value=[Path("seeds")]))
    script = Mock(return_value="BEGIN; COMMIT;")
    monkeypatch.setattr(startup, "build_load_script", script)
    load = Mock()
    monkeypatch.setattr(startup.subprocess, "run", load)
    snapshot = Mock(return_value=0)
    monkeypatch.setattr(startup, "take_first_snapshot", snapshot)
    monkeypatch.setattr(startup, "apply_pending_migrations", Mock())
    return queries, script, load, snapshot


def test_startup_applies_missing_migrations_before_anything_else(prepared):
    queries, *_ = prepared
    queries.side_effect = [(datetime.now(timezone.utc),), ("existing-snapshot",)]
    startup.initialize("test-dsn")
    startup.apply_pending_migrations.assert_called_once_with("test-dsn")


class TestPendingMigrations:
    """Docker n'exécute les migrations qu'à la création du volume. Sans ce
    rattrapage, une base existante ignorerait toute migration ultérieure et
    l'API tomberait sur la première table manquante."""

    @pytest.fixture
    def applied(self, monkeypatch):
        connection = MagicMock()
        monkeypatch.setattr(startup.psycopg, "connect", Mock(return_value=connection))
        rows = connection.__enter__.return_value.execute.return_value.fetchall
        load = Mock()
        monkeypatch.setattr(startup.subprocess, "run", load)
        return rows, load

    @pytest.fixture
    def migrations(self, tmp_path):
        for name in ("0001_initial.sql", "0002_suite.sql", "0003_encore.sql", "README.md"):
            (tmp_path / name).write_text("SELECT 1;")
        return tmp_path

    def test_only_unrecorded_versions_are_applied_in_order(self, applied, migrations):
        rows, load = applied
        rows.return_value = [("0001",), ("0002",)]

        startup.apply_pending_migrations("test-dsn", migrations)

        load.assert_called_once_with(
            ["psql", "--dbname", "test-dsn", "-v", "ON_ERROR_STOP=1", "-q",
             "-f", str(migrations / "0003_encore.sql")],
            check=True,
        )

    def test_an_up_to_date_base_is_left_alone(self, applied, migrations):
        rows, load = applied
        rows.return_value = [("0001",), ("0002",), ("0003",)]

        startup.apply_pending_migrations("test-dsn", migrations)

        load.assert_not_called()


def test_first_start_loads_validated_seeds_and_prices(prepared):
    queries, script, load, snapshot = prepared
    queries.side_effect = [None, None]
    startup.initialize("test-dsn")
    script.assert_called_once()
    load.assert_called_once_with(
        ["psql", "--dbname", "test-dsn", "-v", "ON_ERROR_STOP=1", "-q"],
        input="BEGIN; COMMIT;", text=True, check=True,
    )
    snapshot.assert_called_once_with(["--dsn", "test-dsn", "--bom-version", "test-version"])


def test_restart_does_not_reload_or_create_snapshot(prepared):
    queries, script, load, snapshot = prepared
    queries.side_effect = [(datetime.now(timezone.utc),), ("existing-snapshot",)]
    startup.initialize("test-dsn")
    script.assert_not_called()
    load.assert_not_called()
    snapshot.assert_not_called()


def test_existing_bom_without_snapshot_takes_first_prices(prepared):
    queries, _, load, snapshot = prepared
    queries.side_effect = [(datetime.now(timezone.utc),), None]
    startup.initialize("test-dsn")
    load.assert_not_called()
    snapshot.assert_called_once()


def test_unvalidated_existing_bom_is_not_replaced(prepared):
    queries, script, load, snapshot = prepared
    queries.return_value = (None,)
    with pytest.raises(RuntimeError, match="n'est pas validée"):
        startup.initialize("test-dsn")
    script.assert_not_called()
    load.assert_not_called()
    snapshot.assert_not_called()


def test_rejected_seeds_never_reach_database(prepared):
    queries, script, load, snapshot = prepared
    queries.return_value = None
    script.side_effect = SeedRejected("jeu invalide")
    with pytest.raises(SeedRejected, match="jeu invalide"):
        startup.initialize("test-dsn")
    load.assert_not_called()
    snapshot.assert_not_called()


def test_failed_sql_load_does_not_take_snapshot(prepared):
    queries, _, load, snapshot = prepared
    queries.return_value = None
    load.side_effect = startup.subprocess.CalledProcessError(1, ["psql"])
    with pytest.raises(startup.subprocess.CalledProcessError):
        startup.initialize("test-dsn")
    snapshot.assert_not_called()


def test_failed_first_snapshot_refuses_startup(prepared):
    queries, _, _, snapshot = prepared
    queries.side_effect = [(datetime.now(timezone.utc),), None]
    snapshot.return_value = 1
    with pytest.raises(RuntimeError, match="premier snapshot"):
        startup.initialize("test-dsn")


def test_failed_initialization_does_not_launch_server(monkeypatch, capsys):
    def refuse(*args):
        raise RuntimeError("prix indisponibles")
    monkeypatch.setattr(startup, "initialize", refuse)
    launch = Mock()
    monkeypatch.setattr(startup.os, "execvp", launch)
    assert startup.main() == 1
    launch.assert_not_called()
    assert "initialisation refusée : prix indisponibles" in capsys.readouterr().err


def test_every_bom_is_loaded_and_gets_its_own_first_snapshot(prepared, monkeypatch):
    """Un snapshot du Multipla ne donne aucun prix à une Valhalla : chacune
    doit recevoir le sien, même si un snapshot existe déjà ailleurs."""
    queries, script, load, snapshot = prepared
    versions = iter(["bom-a", "bom-b"])
    monkeypatch.setattr(
        startup, "read_seeds",
        Mock(side_effect=lambda _: {"metadata": {"bom_version_id": next(versions)}}),
    )
    monkeypatch.setattr(
        startup, "seed_directories", Mock(return_value=[Path("a"), Path("b")])
    )
    queries.side_effect = [None, None, None, None]
    startup.initialize("test-dsn")
    assert script.call_count == 2
    assert [call.args[0][-1] for call in snapshot.call_args_list] == ["bom-a", "bom-b"]
