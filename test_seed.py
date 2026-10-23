"""Tests for the SQLite seed module (contract: SPECS.md section 4, seed.py)."""
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import seed
from freshness import Execution, evaluate_pipeline

NOW = datetime(2026, 10, 23, 12, 0, 0)
PROJECT_DIR = Path(seed.__file__).resolve().parent


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """No test may inherit a database path from the real environment."""
    monkeypatch.delenv("DEMO30_DB_PATH", raising=False)


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yml"
    path.write_text(text, encoding="utf-8")
    return path


def rows(db: Path, query: str) -> list[tuple]:
    with sqlite3.connect(db) as conn:
        return conn.execute(query).fetchall()


# --- Path resolution priority -----------------------------------------------

def test_explicit_db_path_wins_over_env_and_config(tmp_path, monkeypatch):
    monkeypatch.setattr(seed, "CONFIG_PATH", write_config(tmp_path, "db_path: from_config.db\n"))
    monkeypatch.setenv("DEMO30_DB_PATH", str(tmp_path / "from_env.db"))
    explicit = tmp_path / "explicit.db"
    assert seed.resolve_db_path(explicit) == explicit


def test_env_wins_over_config(tmp_path, monkeypatch):
    monkeypatch.setattr(seed, "CONFIG_PATH", write_config(tmp_path, "db_path: from_config.db\n"))
    env_path = tmp_path / "from_env.db"
    monkeypatch.setenv("DEMO30_DB_PATH", str(env_path))
    assert seed.resolve_db_path() == env_path


def test_empty_env_falls_back_to_config(tmp_path, monkeypatch):
    monkeypatch.setattr(seed, "CONFIG_PATH", write_config(tmp_path, "db_path: from_config.db\n"))
    monkeypatch.setenv("DEMO30_DB_PATH", "")
    assert seed.resolve_db_path() == PROJECT_DIR / "from_config.db"


def test_config_is_used_without_explicit_path_or_env(tmp_path, monkeypatch):
    monkeypatch.setattr(seed, "CONFIG_PATH", write_config(tmp_path, "db_path: /abs/other.db\n"))
    assert seed.resolve_db_path() == Path("/abs/other.db")


def test_shipped_config_defaults_to_data_db():
    assert seed.read_config(PROJECT_DIR / "config.yml") == {"db_path": "data.db"}
    assert seed.resolve_db_path() == PROJECT_DIR / "data.db"


@pytest.mark.parametrize("source", ["explicit", "env", "config"])
def test_relative_path_resolves_from_project_dir(source, tmp_path, monkeypatch):
    monkeypatch.setattr(seed, "CONFIG_PATH", write_config(tmp_path, "db_path: rel/c.db\n"))
    if source == "explicit":
        assert seed.resolve_db_path("rel/a.db") == PROJECT_DIR / "rel/a.db"
    elif source == "env":
        monkeypatch.setenv("DEMO30_DB_PATH", "rel/b.db")
        assert seed.resolve_db_path() == PROJECT_DIR / "rel/b.db"
    else:
        assert seed.resolve_db_path() == PROJECT_DIR / "rel/c.db"


def test_relative_resolution_ignores_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert seed.resolve_db_path("x.db") == PROJECT_DIR / "x.db"


def test_explicit_path_does_not_read_config(tmp_path, monkeypatch):
    monkeypatch.setattr(seed, "CONFIG_PATH", tmp_path / "missing.yml")
    assert seed.resolve_db_path(tmp_path / "x.db") == tmp_path / "x.db"
    seed.seed(tmp_path / "x.db", now=NOW)  # must not raise ConfigError


def test_dotenv_is_never_read(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(f"DEMO30_DB_PATH={tmp_path / 'dotenv.db'}\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(seed, "CONFIG_PATH", write_config(tmp_path, "db_path: from_config.db\n"))
    assert seed.resolve_db_path() == PROJECT_DIR / "from_config.db"


# --- Minimal config.yml reader ----------------------------------------------

def test_reader_ignores_blank_and_comment_lines(tmp_path):
    path = write_config(tmp_path, "# comment\n\n   \ndb_path: a.db\n# other\n")
    assert seed.read_config(path) == {"db_path": "a.db"}


@pytest.mark.parametrize("raw", ['"a b.db"', "'a b.db'", "a b.db"])
def test_reader_strips_matching_quotes(tmp_path, raw):
    assert seed.read_config(write_config(tmp_path, f"db_path: {raw}\n")) == {"db_path": "a b.db"}


def test_reader_keeps_colons_in_value(tmp_path):
    path = write_config(tmp_path, "db_path: C:/data/x.db\n")
    assert seed.read_config(path) == {"db_path": "C:/data/x.db"}


def test_reader_does_not_handle_trailing_comments(tmp_path):
    path = write_config(tmp_path, "db_path: a.db # note\n")
    assert seed.read_config(path) == {"db_path": "a.db # note"}


@pytest.mark.parametrize(
    "text, line",
    [
        ("db_path: a.db\nother: 1\n", 2),  # unknown key
        ("db_path: a.db\ndb_path: b.db\n", 2),  # duplicate
        ("# c\ndb_path a.db\n", 2),  # malformed: no colon
        ("db_path:\n", 1),  # empty value
        ('db_path: ""\n', 1),  # empty after quote stripping
        (": a.db\n", 1),  # empty key
        ("db_path: a.db\n  nested: 1\n", 2),  # nesting / indentation
        ("db_path: a.db\n- item\n", 2),  # list
    ],
)
def test_reader_errors_name_file_and_line(tmp_path, text, line):
    path = write_config(tmp_path, text)
    with pytest.raises(seed.ConfigError) as err:
        seed.read_config(path)
    assert str(path) in str(err.value)
    assert f"ligne {line}" in str(err.value)


def test_reader_rejects_missing_required_key(tmp_path):
    path = write_config(tmp_path, "# nothing here\n")
    with pytest.raises(seed.ConfigError) as err:
        seed.read_config(path)
    assert str(path) in str(err.value)
    assert "db_path" in str(err.value)


def test_reader_rejects_missing_file(tmp_path):
    path = tmp_path / "absent.yml"
    with pytest.raises(seed.ConfigError) as err:
        seed.read_config(path)
    assert str(path) in str(err.value)


def test_resolve_raises_config_error_when_config_needed_and_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(seed, "CONFIG_PATH", write_config(tmp_path, "oops\n"))
    with pytest.raises(seed.ConfigError):
        seed.resolve_db_path()


def test_cli_prints_config_error_and_exits_1(tmp_path, monkeypatch, capsys):
    path = write_config(tmp_path, "db_path: a.db\nbad line\n")
    monkeypatch.setattr(seed, "CONFIG_PATH", path)
    assert seed.main() == 1
    captured = capsys.readouterr()
    assert str(path) in captured.err + captured.out
    assert "Traceback" not in captured.err + captured.out


def test_cli_real_run_uses_env_db_and_exits_0(tmp_path):
    db = tmp_path / "cli.db"
    env = {"PATH": "/usr/bin:/bin", "DEMO30_DB_PATH": str(db)}
    done = subprocess.run(
        [sys.executable, "-I", str(PROJECT_DIR / "seed.py")],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr
    assert len(rows(db, "SELECT * FROM pipeline")) == 4


# --- Seeded data ------------------------------------------------------------

@pytest.fixture
def db(tmp_path) -> Path:
    path = tmp_path / "seed.db"
    seed.seed(path, now=NOW)
    return path


def test_creates_four_pipelines(db):
    assert rows(db, "SELECT code_pipeline, nom, frequence_minutes, "
                    "seuil_degrade_minutes, seuil_critique_minutes "
                    "FROM pipeline ORDER BY code_pipeline") == [
        ("PL-101", "Billing — nominal", 60, 30, 60),
        ("PL-102", "Billing — retard léger", 60, 30, 60),
        ("PL-103", "Billing — erreurs ignorées", 60, 30, 60),
        ("PL-104", "Billing — zéro validation", 60, 30, 60),
    ]


def test_creates_five_executions(db):
    result = rows(db, "SELECT id_execution, code_pipeline, statut "
                      "FROM execution_ingestion ORDER BY id_execution")
    assert [r[0] for r in result] == [f"EX-00{i}" for i in range(1, 6)]
    assert [(r[1], r[2]) for r in result] == [
        ("PL-101", "VALIDE"),
        ("PL-102", "VALIDE"),
        ("PL-103", "VALIDE"),
        ("PL-103", "EN_ERREUR"),
        ("PL-104", "EN_ERREUR"),
    ]


def test_dates_are_iso_8601_and_errors_have_no_validation(db):
    for _, debut, validation, statut in rows(
        db, "SELECT id_execution, date_debut, date_validation, statut FROM execution_ingestion"
    ):
        datetime.fromisoformat(debut)
        if statut == "EN_ERREUR":
            assert validation is None
        else:
            assert datetime.fromisoformat(validation) >= datetime.fromisoformat(debut)


def read_executions(db: Path, code: str) -> list[Execution]:
    return [
        Execution(
            statut,
            datetime.fromisoformat(debut),
            datetime.fromisoformat(validation) if validation else None,
        )
        for statut, debut, validation in rows(
            db, "SELECT statut, date_debut, date_validation FROM execution_ingestion "
                f"WHERE code_pipeline = '{code}'"
        )
    ]


@pytest.mark.parametrize(
    "code, delay, status",
    [("PL-101", 0, "NORMAL"), ("PL-102", 45, "DEGRADE"), ("PL-103", 80, "CRITIQUE"), ("PL-104", None, "CRITIQUE")],
)
def test_seed_reproduces_acceptance_scenarios(db, code, delay, status):
    result = evaluate_pipeline(code, 60, 30, 60, read_executions(db, code), NOW)
    assert (result.retard_minutes, result.statut_calcule) == (delay, status)


def test_seed_is_relative_to_now(tmp_path):
    later = NOW + timedelta(hours=5)
    first, second = tmp_path / "a.db", tmp_path / "b.db"
    seed.seed(first, now=NOW)
    seed.seed(second, now=later)
    q = "SELECT date_debut FROM execution_ingestion WHERE id_execution = 'EX-001'"
    shift = datetime.fromisoformat(rows(second, q)[0][0]) - datetime.fromisoformat(rows(first, q)[0][0])
    assert shift == timedelta(hours=5)


def test_seed_without_now_uses_current_time(tmp_path):
    path = tmp_path / "now.db"
    before = datetime.now()
    seed.seed(path)
    (debut,) = rows(path, "SELECT date_debut FROM execution_ingestion WHERE id_execution = 'EX-001'")[0]
    assert before - timedelta(hours=1) < datetime.fromisoformat(debut) < datetime.now()


def test_reseed_replaces_data_without_duplicates(db):
    seed.seed(db, now=NOW + timedelta(hours=1))
    assert len(rows(db, "SELECT * FROM pipeline")) == 4
    assert len(rows(db, "SELECT * FROM execution_ingestion")) == 5


def test_reseed_removes_foreign_rows_of_its_two_tables(db):
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO pipeline VALUES ('PL-999', 'x', 1, 1, 1)")
        conn.execute("INSERT INTO execution_ingestion VALUES ('EX-999', 'PL-999', '2026-01-01T00:00:00', NULL, 'EN_ERREUR')")
    seed.seed(db, now=NOW)
    assert "PL-999" not in [r[0] for r in rows(db, "SELECT code_pipeline FROM pipeline")]
    assert len(rows(db, "SELECT * FROM execution_ingestion")) == 5


def test_other_tables_are_left_untouched(tmp_path):
    path = tmp_path / "shared.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE other (v TEXT)")
        conn.execute("INSERT INTO other VALUES ('keep')")
    seed.seed(path, now=NOW)
    assert rows(path, "SELECT v FROM other") == [("keep",)]


def test_schema_accepts_unknown_status_for_rule_5(db):
    """Rule 5 needs the dashboard to be testable with an invalid status."""
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO execution_ingestion VALUES ('EX-X', 'PL-101', '2026-01-01T00:00:00', NULL, 'BIZARRE')")


# --- No write to another database -------------------------------------------

def test_seed_writes_only_the_resolved_database(tmp_path, monkeypatch):
    other = tmp_path / "other.db"
    monkeypatch.setenv("DEMO30_DB_PATH", str(other))
    monkeypatch.setattr(seed, "CONFIG_PATH", write_config(tmp_path, f"db_path: {tmp_path / 'cfg.db'}\n"))
    project_db = PROJECT_DIR / "data.db"
    before = project_db.stat().st_mtime_ns if project_db.exists() else None

    target = tmp_path / "target.db"
    seed.seed(target, now=NOW)

    assert target.exists()
    assert not other.exists()
    assert not (tmp_path / "cfg.db").exists()
    after = project_db.stat().st_mtime_ns if project_db.exists() else None
    assert before == after


def test_seed_uses_env_database_when_no_explicit_path(tmp_path, monkeypatch):
    env_db = tmp_path / "env.db"
    monkeypatch.setenv("DEMO30_DB_PATH", str(env_db))
    monkeypatch.setattr(seed, "CONFIG_PATH", write_config(tmp_path, f"db_path: {tmp_path / 'cfg.db'}\n"))
    seed.seed(now=NOW)
    assert env_db.exists()
    assert not (tmp_path / "cfg.db").exists()
