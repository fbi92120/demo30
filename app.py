"""Streamlit dashboard for the freshness of ingestion pipelines.

Reads SQLite in read-only mode, calls the pure engine ``freshness.py`` and
shows every pipeline found in the database. The only write is the
"Actualiser les scénarios" button, which calls ``seed.seed()``.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import streamlit as st

from freshness import Execution, FreshnessResult, evaluate_pipeline
from seed import ConfigError, resolve_db_path, seed

STATUS_ICONS = {"NORMAL": "🟢", "DEGRADE": "🟠", "CRITIQUE": "🔴"}
ERROR_ICON = "⚠️"
NO_VALIDATION = "aucune validation"


class DatabaseUnavailable(Exception):
    """The database is missing or cannot be read."""


@dataclass(frozen=True)
class PipelineView:
    """One pipeline ready for display: a result or a readable error."""

    code_pipeline: str
    nom: str
    result: FreshnessResult | None = None
    error: str | None = None
    executions: list[dict] = field(default_factory=list)


def load_views(db_path: Path, now: datetime) -> list[PipelineView]:
    """Read every pipeline and evaluate it; never writes to the database."""
    if not Path(db_path).is_file():
        raise DatabaseUnavailable(f"Base introuvable : {db_path}")
    try:
        conn = sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise DatabaseUnavailable(f"Base illisible : {db_path} ({exc})") from exc
    try:
        pipelines = conn.execute(
            "SELECT code_pipeline, nom, frequence_minutes, seuil_degrade_minutes, "
            "seuil_critique_minutes FROM pipeline ORDER BY code_pipeline"
        ).fetchall()
        runs = conn.execute(
            "SELECT code_pipeline, id_execution, statut, date_debut, date_validation "
            "FROM execution_ingestion ORDER BY date_debut DESC"
        ).fetchall()
    except sqlite3.Error as exc:
        raise DatabaseUnavailable(f"Base illisible : {db_path} ({exc})") from exc
    finally:
        conn.close()

    views = []
    for code, nom, frequency, degraded, critical in pipelines:
        own = [r for r in runs if r[0] == code]
        table = [
            {"Exécution": r[1], "Statut": r[2], "Début": r[3], "Validation": r[4] or "—"}
            for r in own
        ]
        try:
            try:
                executions = [
                    Execution(
                        statut,
                        datetime.fromisoformat(debut),
                        datetime.fromisoformat(validation) if validation else None,
                    )
                    for _, _, statut, debut, validation in own
                ]
            except ValueError as exc:  # rule 6: unreadable date
                raise ValueError(f"Pipeline {code}: date illisible, format ISO 8601 attendu ({exc})") from exc
            result = evaluate_pipeline(code, frequency, degraded, critical, executions, now)
        except ValueError as exc:  # rule 5 (unknown status) or rule 6
            views.append(PipelineView(code, nom, error=str(exc), executions=table))
        else:
            views.append(PipelineView(code, nom, result=result, executions=table))
    return views


def delay_label(result: FreshnessResult) -> str:
    if result.retard_minutes is None:
        return NO_VALIDATION
    return f"{result.retard_minutes:.0f} min"


def render_detail(view: PipelineView) -> None:
    st.subheader(f"{view.code_pipeline} — {view.nom}")
    if view.error:
        st.error(f"Erreur sur le pipeline {view.code_pipeline} : {view.error}")
    else:
        assert view.result is not None
        st.write(f"**État** : {STATUS_ICONS[view.result.statut_calcule]} {view.result.statut_calcule}")
        st.write(f"**Retard** : {delay_label(view.result)}")
    st.write("**Exécutions**")
    if view.executions:
        st.table(view.executions)
    else:
        st.info("Aucune exécution enregistrée.")


def main() -> None:
    st.set_page_config(page_title="Fraîcheur des pipelines", page_icon="🟢")
    st.title("Fraîcheur des pipelines d'ingestion")
    st.caption(
        "Un pipeline n'est à jour qu'après une validation métier réussie : "
        "le retard est mesuré depuis la dernière exécution VALIDE + sa fréquence."
    )

    try:
        db_path = resolve_db_path()
    except ConfigError as exc:
        st.error(f"Erreur de configuration : {exc}")
        return

    if st.button("Actualiser les scénarios"):
        try:
            seed()
        except (ConfigError, sqlite3.Error, OSError) as exc:
            st.error(f"Impossible de régénérer les données : {exc}")
            return

    try:
        views = load_views(db_path, datetime.now())
    except DatabaseUnavailable as exc:
        st.warning(
            f"{exc}. La base est introuvable ou illisible : cliquez sur "
            "« Actualiser les scénarios » pour la créer."
        )
        return

    if not views:
        st.info("Aucun pipeline dans la base. Cliquez sur « Actualiser les scénarios ».")
        return

    columns = st.columns(len(views))
    for column, view in zip(columns, views):
        with column:
            if view.error:
                st.markdown(f"### {ERROR_ICON} {view.code_pipeline}")
                st.error(view.error)
            else:
                assert view.result is not None
                st.markdown(f"### {STATUS_ICONS[view.result.statut_calcule]} {view.code_pipeline}")
                st.write(view.nom)
                st.write(f"{view.result.statut_calcule} — retard : {delay_label(view.result)}")

    st.divider()
    by_code = {v.code_pipeline: v for v in views}
    chosen = st.selectbox(
        "Scénario à examiner",
        list(by_code),
        format_func=lambda code: f"{code} — {by_code[code].nom}",
    )
    render_detail(by_code[chosen])


if __name__ == "__main__":
    main()
