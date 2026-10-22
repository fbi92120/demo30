"""Unit tests for the pure freshness engine (contract: SPECS.md section 4)."""
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta

import pytest

from freshness import Execution, FreshnessResult, evaluate_pipeline

NOW = datetime(2026, 10, 22, 12, 0, 0)


def ago(minutes: float) -> datetime:
    return NOW - timedelta(minutes=minutes)


def valid_run(validated_minutes_ago: float, started_minutes_ago: float | None = None) -> Execution:
    start = validated_minutes_ago + 5 if started_minutes_ago is None else started_minutes_ago
    return Execution("VALIDE", ago(start), ago(validated_minutes_ago))


def failed_run(started_minutes_ago: float) -> Execution:
    return Execution("EN_ERREUR", ago(started_minutes_ago), None)


def evaluate(executions, code="PL-X", frequency=60, degraded=30, critical=60) -> FreshnessResult:
    return evaluate_pipeline(code, frequency, degraded, critical, executions, NOW)


# --- Contract of the data classes -------------------------------------------

def test_execution_is_frozen():
    run = valid_run(10)
    with pytest.raises(FrozenInstanceError):
        run.statut = "EN_ERREUR"  # type: ignore[misc]


def test_freshness_result_is_frozen():
    result = FreshnessResult("PL-X", 0.0, "NORMAL")
    with pytest.raises(FrozenInstanceError):
        result.statut_calcule = "CRITIQUE"  # type: ignore[misc]


def test_result_carries_pipeline_code():
    assert evaluate([valid_run(30)], code="PL-777").code_pipeline == "PL-777"


# --- Acceptance scenarios (SPECS.md section 6) ------------------------------

def test_case_1_nominal():
    result = evaluate([valid_run(30)], code="PL-101")
    assert result == FreshnessResult("PL-101", 0, "NORMAL")


def test_case_2_light_delay():
    result = evaluate([valid_run(105)], code="PL-102")
    assert result == FreshnessResult("PL-102", 45, "DEGRADE")


def test_case_3_errors_ignored():
    result = evaluate([valid_run(140), failed_run(10)], code="PL-103")
    assert result == FreshnessResult("PL-103", 80, "CRITIQUE")


def test_case_4_zero_validation():
    result = evaluate([], code="PL-104")
    assert result.retard_minutes is None
    assert result.statut_calcule == "CRITIQUE"
    assert result.code_pipeline == "PL-104"


def test_only_errors_means_no_validation():
    result = evaluate([failed_run(10), failed_run(200)])
    assert result.retard_minutes is None
    assert result.statut_calcule == "CRITIQUE"


# --- Rule 1B: reference is date_validation, never date_debut ----------------

def test_delay_computed_from_date_validation_not_date_debut():
    # Started 300 min ago, validated 105 min ago: delay must be 105 - 60 = 45.
    run = valid_run(validated_minutes_ago=105, started_minutes_ago=300)
    result = evaluate([run])
    assert result.retard_minutes == 45
    assert result.statut_calcule == "DEGRADE"


def test_latest_validation_is_the_reference_regardless_of_order():
    older, newer = valid_run(200), valid_run(105)
    assert evaluate([older, newer]).retard_minutes == 45
    assert evaluate([newer, older]).retard_minutes == 45


def test_latest_by_validation_date_not_by_start_date():
    # "late" starts earlier but is validated later: it is the reference.
    early_start_late_validation = valid_run(validated_minutes_ago=105, started_minutes_ago=400)
    late_start_early_validation = valid_run(validated_minutes_ago=200, started_minutes_ago=210)
    result = evaluate([late_start_early_validation, early_start_late_validation])
    assert result.retard_minutes == 45


def test_delay_is_never_negative():
    # Deadline still in the future: delay is 0, not negative.
    assert evaluate([valid_run(10)]).retard_minutes == 0


def test_deadline_exactly_now_gives_zero():
    assert evaluate([valid_run(60)]).retard_minutes == 0


def test_frequency_is_used_for_the_deadline():
    assert evaluate([valid_run(100)], frequency=90).retard_minutes == 10


# --- Rule 2B: only VALIDE runs reset the reference --------------------------

def test_recent_error_does_not_reset_reference():
    assert evaluate([valid_run(105), failed_run(1)]).retard_minutes == 45


def test_error_with_a_validation_date_is_still_ignored():
    odd_error = Execution("EN_ERREUR", ago(20), ago(5))
    assert evaluate([valid_run(105), odd_error]).retard_minutes == 45


# --- Rule 4A: thresholds, boundaries 30/31/60/61 ----------------------------
# delay = minutes since validation - frequency (60)

@pytest.mark.parametrize(
    "delay, expected",
    [
        (30, "NORMAL"),     # <= degraded threshold
        (31, "DEGRADE"),    # > degraded threshold
        (60, "DEGRADE"),    # <= critical threshold
        (61, "CRITIQUE"),   # > critical threshold
    ],
)
def test_threshold_boundaries(delay, expected):
    result = evaluate([valid_run(60 + delay)], degraded=30, critical=60)
    assert result.retard_minutes == delay
    assert result.statut_calcule == expected


def test_zero_delay_is_normal():
    assert evaluate([valid_run(60)]).statut_calcule == "NORMAL"


def test_custom_thresholds_are_respected():
    run = valid_run(60 + 15)
    assert evaluate([run], degraded=10, critical=20).statut_calcule == "DEGRADE"
    assert evaluate([run], degraded=15, critical=20).statut_calcule == "NORMAL"
    assert evaluate([run], degraded=5, critical=10).statut_calcule == "CRITIQUE"


# --- VALIDE without date_validation (contract section 4) --------------------

def test_valide_without_validation_date_is_not_a_reference():
    result = evaluate([Execution("VALIDE", ago(10), None)])
    assert result.retard_minutes is None
    assert result.statut_calcule == "CRITIQUE"


def test_valide_without_validation_date_falls_back_to_other_validation():
    broken = Execution("VALIDE", ago(10), None)
    assert evaluate([valid_run(105), broken]).retard_minutes == 45


# --- Rule 5: unknown execution status is an explicit error ------------------

def test_unknown_status_raises_value_error_with_code_and_status():
    runs = [valid_run(30), Execution("PAUSE", ago(5), None)]
    with pytest.raises(ValueError) as error:
        evaluate(runs, code="PL-999")
    assert "PL-999" in str(error.value)
    assert "PAUSE" in str(error.value)
