"""Wrappers around mature Ring-Barrier parsing and standard-table builders."""

from __future__ import annotations

from pathlib import Path

from preprocessing.timing.ring_to_stage.cycle_stage_exec_history import (
    build_cycle_stage_exec_history as build_cycle_stage_exec_history_table,
)
from preprocessing.timing.ring_to_stage.period_plan_exec_history import (
    build_period_plan_exec_history as build_period_plan_exec_history_table,
)
from preprocessing.timing.ring_to_stage.standard_timing_tables import (
    build_standard_tables,
)
from preprocessing.timing.stage_to_ring_table import convert_csv as convert_stage_csv_to_ring_csv
from preprocessing.timing.timing_csv_to_stage_table import convert_csv


def convert_timing_csv_to_stage_table(input_csv: str | Path, output_csv: str | Path) -> None:
    """Convert vendor timing CSV to a CSV with stage descriptions and durations."""
    convert_csv(Path(input_csv), Path(output_csv))


def convert_stage_csv_to_ring_table(
    input_csv: str | Path,
    output_csv: str | Path,
    *,
    yellow_sec: int = 0,
    all_red_sec: int = 0,
) -> None:
    """Convert stage descriptions and durations back to replayable Ring-Barrier CSV fields."""
    convert_stage_csv_to_ring_csv(
        Path(input_csv),
        Path(output_csv),
        yellow_sec=yellow_sec,
        all_red_sec=all_red_sec,
    )


def build_standard_timing_tables(
    timing_csv: str | Path,
    schedule_csv: str | Path,
    output_dir: str | Path,
    *,
    batch_id: str | None = None,
) -> dict[str, int]:
    """Build signal-control standard table CSV files from timing and schedule CSV."""
    return build_standard_tables(
        Path(timing_csv),
        Path(schedule_csv),
        Path(output_dir),
        batch_id=batch_id,
    )


def build_cycle_stage_exec_history(
    input_csv: str | Path,
    output_csv: str | Path,
    *,
    batch_id: str | None = None,
) -> dict[str, int]:
    """Build cycle-stage execution history standard CSV."""
    return build_cycle_stage_exec_history_table(
        Path(input_csv),
        Path(output_csv),
        batch_id=batch_id,
    )


def build_period_plan_exec_history(
    input_csv: str | Path,
    output_csv: str | Path,
    *,
    batch_id: str | None = None,
) -> dict[str, int]:
    """Build period-plan execution history standard CSV."""
    return build_period_plan_exec_history_table(
        Path(input_csv),
        Path(output_csv),
        batch_id=batch_id,
    )
