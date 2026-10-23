"""SQLite seed script for the freshness demo.

Resolves the database path (explicit argument, then ``DEMO30_DB_PATH``, then
``config.yml``) and (re)generates the four demo pipelines and their five
executions relative to the current time.
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "config.yml"
ENV_VAR = "DEMO30_DB_PATH"
REQUIRED_KEY = "db_path"
KNOWN_KEYS = {REQUIRED_KEY}
_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

SCHEMA = """
CREATE TABLE IF NOT EXISTS pipeline (
    code_pipeline TEXT PRIMARY KEY,
    nom TEXT NOT NULL,
    frequence_minutes INTEGER NOT NULL,
    seuil_degrade_minutes INTEGER NOT NULL,
    seuil_critique_minutes INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS execution_ingestion (
    id_execution TEXT PRIMARY KEY,
    code_pipeline TEXT NOT NULL REFERENCES pipeline (code_pipeline),
    date_debut TEXT NOT NULL,
    date_validation TEXT,
    statut TEXT NOT NULL
);
"""

# (code, name, frequency, degraded threshold, critical threshold)
PIPELINES = [
    ("PL-101", "Billing — nominal", 60, 30, 60),
    ("PL-102", "Billing — retard léger", 60, 30, 60),
    ("PL-103", "Billing — erreurs ignorées", 60, 30, 60),
    ("PL-104", "Billing — zéro validation", 60, 30, 60),
]

# (id, code, status, minutes ago the run started, minutes ago it was validated)
EXECUTIONS = [
    ("EX-001", "PL-101", "VALIDE", 35, 30),
    ("EX-002", "PL-102", "VALIDE", 110, 105),
    ("EX-003", "PL-103", "VALIDE", 145, 140),
    ("EX-004", "PL-103", "EN_ERREUR", 10, None),
    ("EX-005", "PL-104", "EN_ERREUR", 20, None),
]


class ConfigError(Exception):
    """Readable error about ``config.yml``; names the file and the line."""


def read_config(path: Path) -> dict[str, str]:
    """Read the minimal flat ``key: value`` config format (no YAML library)."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"{path} : fichier de configuration introuvable") from None
    except OSError as exc:
        raise ConfigError(f"{path} : lecture impossible ({exc.strerror})") from None

    values: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        where = f"{path}, ligne {number}"
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, raw = line.partition(":")
        if not sep or not _KEY_RE.fullmatch(key):
            raise ConfigError(f"{where} : ligne mal formée {line!r} (attendu : clé: valeur)")
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not value:
            raise ConfigError(f"{where} : valeur vide pour la clé {key!r}")
        if key not in KNOWN_KEYS:
            raise ConfigError(f"{where} : clé inconnue {key!r}")
        if key in values:
            raise ConfigError(f"{where} : clé en double {key!r}")
        values[key] = value

    if REQUIRED_KEY not in values:
        raise ConfigError(f"{path} : clé requise absente {REQUIRED_KEY!r}")
    return values


def resolve_db_path(db_path: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the database path: argument, then environment, then config.yml."""
    if db_path is not None:
        chosen = Path(db_path)
    elif os.environ.get(ENV_VAR):
        chosen = Path(os.environ[ENV_VAR])
    else:
        chosen = Path(read_config(CONFIG_PATH)[REQUIRED_KEY])
    return chosen if chosen.is_absolute() else PROJECT_DIR / chosen


def seed(
    db_path: str | os.PathLike[str] | None = None,
    now: datetime | None = None,
) -> Path:
    """Replace the content of ``pipeline`` and ``execution_ingestion``.

    Other tables of the database are left untouched. Returns the path used.
    """
    path = resolve_db_path(db_path)
    now = datetime.now() if now is None else now

    def iso(minutes_ago: int | None) -> str | None:
        if minutes_ago is None:
            return None
        return (now - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")

    conn = sqlite3.connect(path)
    try:
        with conn:
            conn.executescript(SCHEMA)
            conn.execute("DELETE FROM execution_ingestion")
            conn.execute("DELETE FROM pipeline")
            conn.executemany("INSERT INTO pipeline VALUES (?, ?, ?, ?, ?)", PIPELINES)
            conn.executemany(
                "INSERT INTO execution_ingestion VALUES (?, ?, ?, ?, ?)",
                [(i, code, iso(start), iso(valid), status) for i, code, status, start, valid in EXECUTIONS],
            )
    finally:
        conn.close()
    return path


def main() -> int:
    try:
        path = seed()
    except ConfigError as exc:
        print(f"Erreur de configuration : {exc}", file=sys.stderr)
        return 1
    print(f"Base amorcée : {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
