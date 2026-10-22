"""Pure freshness engine for ingestion pipelines.

No SQLite access and no internal clock: the caller supplies the pipeline
parameters, the already-read executions and the current time (``now``).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

STATUS_VALID = "VALIDE"
STATUS_ERROR = "EN_ERREUR"
STATUS_NORMAL = "NORMAL"
STATUS_DEGRADED = "DEGRADE"
STATUS_CRITICAL = "CRITIQUE"


@dataclass(frozen=True)
class Execution:
    """One ingestion run, as read from storage."""

    statut: str  # 'VALIDE' or 'EN_ERREUR'
    date_debut: datetime
    date_validation: datetime | None  # None on error


@dataclass(frozen=True)
class FreshnessResult:
    """Freshness evaluation of one pipeline."""

    code_pipeline: str
    retard_minutes: float | None  # None when no usable validation exists
    statut_calcule: str  # 'NORMAL', 'DEGRADE' or 'CRITIQUE'


def evaluate_pipeline(
    code_pipeline: str,
    frequence_minutes: int,
    seuil_degrade_minutes: int,
    seuil_critique_minutes: int,
    executions: Sequence[Execution],
    now: datetime,
) -> FreshnessResult:
    """Evaluate the freshness of a pipeline at time ``now``.

    Rules:
    - 1B: delay is measured against the expected deadline, i.e. the latest
      validation date plus the pipeline frequency (never below 0).
    - 2B: only ``VALIDE`` runs set the reference; errors are ignored. The
      reference is ``date_validation``, never ``date_debut``. A ``VALIDE`` run
      without ``date_validation`` is not usable.
    - 5: an execution status other than ``VALIDE`` or ``EN_ERREUR`` raises
      ``ValueError`` naming the pipeline and the received status.
    - 3B: no usable validation -> delay None, status CRITIQUE.
    - 4A: NORMAL if delay <= degraded threshold, DEGRADE if delay <= critical
      threshold, CRITIQUE above.
    """
    for run in executions:
        if run.statut not in (STATUS_VALID, STATUS_ERROR):
            raise ValueError(
                f"Pipeline {code_pipeline}: unknown execution status {run.statut!r}"
            )

    validations = [
        run.date_validation
        for run in executions
        if run.statut == STATUS_VALID and run.date_validation is not None
    ]
    if not validations:
        return FreshnessResult(code_pipeline, None, STATUS_CRITICAL)

    deadline = max(validations) + timedelta(minutes=frequence_minutes)
    delay = max(0.0, (now - deadline).total_seconds() / 60)

    if delay <= seuil_degrade_minutes:
        status = STATUS_NORMAL
    elif delay <= seuil_critique_minutes:
        status = STATUS_DEGRADED
    else:
        status = STATUS_CRITICAL
    return FreshnessResult(code_pipeline, delay, status)
