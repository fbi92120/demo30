"""Integration tests: SQLite -> read -> pure engine -> dashboard (SPECS.md section 5)."""
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import app
import seed

NOW = datetime(2026, 10, 23, 12, 0, 0)
APP_FILE = str(Path(app.__file__).resolve())


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Every test works on a temporary database, never on the project one."""
    monkeypatch.setenv("DEMO30_DB_PATH", str(tmp_path / "it.db"))


@pytest.fixture
def db(tmp_path) -> Path:
    path = tmp_path / "it.db"
    seed.seed(path, now=NOW)
    return path


@pytest.fixture
def live_db(tmp_path) -> Path:
    """Seeded at the real current time, as the dashboard evaluates with datetime.now()."""
    path = tmp_path / "it.db"
    seed.seed(path)
    return path


def by_code(views):
    return {v.code_pipeline: v for v in views}


# --- SQLite -> read -> engine ------------------------------------------------

def test_all_pipelines_are_evaluated_from_the_database(db):
    views = by_code(app.load_views(db, NOW))
    assert list(views) == ["PL-101", "PL-102", "PL-103", "PL-104"]
    expected = {
        "PL-101": (0, "NORMAL"),
        "PL-102": (45, "DEGRADE"),
        "PL-103": (80, "CRITIQUE"),
        "PL-104": (None, "CRITIQUE"),
    }
    for code, (delay, status) in expected.items():
        assert views[code].error is None
        assert (views[code].result.retard_minutes, views[code].result.statut_calcule) == (delay, status)


def test_pipelines_come_from_the_database_not_from_the_code(db):
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO pipeline VALUES ('PL-555', 'Extra', 60, 30, 60)")
    views = by_code(app.load_views(db, NOW))
    assert "PL-555" in views
    assert views["PL-555"].result.statut_calcule == "CRITIQUE"  # no execution at all


def test_loading_never_modifies_the_database(db):
    before = (db.read_bytes(), db.stat().st_mtime_ns)
    app.load_views(db, NOW)
    assert (db.read_bytes(), db.stat().st_mtime_ns) == before


def test_missing_database_is_reported_not_created(tmp_path):
    missing = tmp_path / "absent.db"
    with pytest.raises(app.DatabaseUnavailable):
        app.load_views(missing, NOW)
    assert not missing.exists()


def test_unreadable_database_is_reported(tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_text("this is not a sqlite file")
    with pytest.raises(app.DatabaseUnavailable):
        app.load_views(bad, NOW)


def test_database_without_expected_tables_is_reported(tmp_path):
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    with pytest.raises(app.DatabaseUnavailable):
        app.load_views(empty, NOW)


# --- Rule 5: an unknown status stays local to its pipeline -------------------

def test_unknown_status_breaks_only_its_pipeline(db):
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO execution_ingestion VALUES ('EX-X', 'PL-102', "
            "'2026-10-23T11:00:00', NULL, 'BIZARRE')"
        )
    views = by_code(app.load_views(db, NOW))
    assert views["PL-102"].result is None
    assert "PL-102" in views["PL-102"].error and "BIZARRE" in views["PL-102"].error
    assert views["PL-102"].executions  # still examinable
    for code in ("PL-101", "PL-103", "PL-104"):
        assert views[code].error is None and views[code].result is not None


def test_unknown_status_does_not_write(db):
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO execution_ingestion VALUES ('EX-X', 'PL-101', "
            "'2026-10-23T11:00:00', NULL, 'BIZARRE')"
        )
    before = db.read_bytes()
    app.load_views(db, NOW)
    assert db.read_bytes() == before


# --- Rule 6: an unreadable validation date stays local to its pipeline -----

def test_unreadable_validation_date_breaks_only_its_pipeline(db):
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE execution_ingestion SET date_validation = 'pas-une-date' WHERE id_execution = 'EX-002'")
    views = by_code(app.load_views(db, NOW))
    assert views["PL-102"].result is None
    assert views["PL-102"].error
    assert views["PL-102"].executions  # still examinable
    for code in ("PL-101", "PL-103", "PL-104"):
        assert views[code].error is None and views[code].result is not None


@pytest.mark.parametrize(
    "column, execution, code",
    [
        ("date_debut", "EX-001", "PL-101"),  # start date, never used by the engine
        ("date_validation", "EX-004", "PL-103"),  # validation date of an EN_ERREUR run
    ],
)
def test_any_unreadable_execution_date_breaks_only_its_pipeline(db, column, execution, code):
    with sqlite3.connect(db) as conn:
        conn.execute(f"UPDATE execution_ingestion SET {column} = 'pas-une-date' WHERE id_execution = ?", (execution,))
    views = by_code(app.load_views(db, NOW))
    assert views[code].result is None
    assert code in views[code].error and "ISO 8601" in views[code].error
    for other in set(views) - {code}:
        assert views[other].error is None and views[other].result is not None


def test_missing_validation_date_on_error_run_is_normal(db):
    views = by_code(app.load_views(db, NOW))
    assert views["PL-103"].error is None  # EX-004 is EN_ERREUR with NULL validation
    assert views["PL-104"].error is None


def test_unreadable_validation_date_is_shown_without_stopping_the_dashboard(live_db):
    with sqlite3.connect(live_db) as conn:
        conn.execute("UPDATE execution_ingestion SET date_validation = 'pas-une-date' WHERE id_execution = 'EX-002'")
    before = live_db.read_bytes()
    at = run_app()
    assert not at.exception
    assert any("PL-102" in e.value for e in at.error)
    text = " ".join(m.value for m in at.markdown)
    for icon, code in [("🟢", "PL-101"), ("🔴", "PL-103"), ("🔴", "PL-104")]:
        assert f"{icon} {code}" in text
    assert live_db.read_bytes() == before


# --- Dashboard (Streamlit AppTest) ------------------------------------------

def run_app() -> AppTest:
    return AppTest.from_file(APP_FILE, default_timeout=20).run()


def test_dashboard_without_database_invites_to_refresh(tmp_path):
    at = run_app()
    assert not at.exception
    assert any("Actualiser les scénarios" in w.value for w in at.warning)
    assert not (tmp_path / "it.db").exists()  # reading never creates the database


def test_refresh_button_creates_the_data():
    at = run_app()
    at.button[0].click().run()
    assert not at.exception
    assert len(at.selectbox[0].options) == 4


def test_dashboard_shows_all_states(live_db):
    at = run_app()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    for icon, code in [("🟢", "PL-101"), ("🟠", "PL-102"), ("🔴", "PL-103"), ("🔴", "PL-104")]:
        assert f"{icon} {code}" in text


def test_selector_shows_no_validation_label(live_db):
    at = run_app()
    at.selectbox[0].select("PL-104").run()
    assert any("aucune validation" in m.value for m in at.markdown)


def test_dashboard_keeps_displaying_others_when_one_pipeline_is_in_error(live_db):
    with sqlite3.connect(live_db) as conn:
        conn.execute(
            "INSERT INTO execution_ingestion VALUES ('EX-X', 'PL-102', "
            "'2026-10-23T11:00:00', NULL, 'BIZARRE')"
        )
    before = live_db.read_bytes()
    at = run_app()
    assert not at.exception
    assert any("PL-102" in e.value and "BIZARRE" in e.value for e in at.error)
    text = " ".join(m.value for m in at.markdown)
    for icon, code in [("🟢", "PL-101"), ("🔴", "PL-103"), ("🔴", "PL-104")]:
        assert f"{icon} {code}" in text
    assert live_db.read_bytes() == before  # the error triggers no write


def test_invalid_config_is_shown_without_traceback(monkeypatch, tmp_path):
    monkeypatch.delenv("DEMO30_DB_PATH")
    bad = tmp_path / "config.yml"
    bad.write_text("not valid\n")
    monkeypatch.setattr(seed, "CONFIG_PATH", bad)
    at = run_app()
    assert not at.exception
    assert any(str(bad) in e.value for e in at.error)
