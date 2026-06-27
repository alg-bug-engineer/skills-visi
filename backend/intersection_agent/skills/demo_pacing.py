"""Demo pacing for leadership presentation (total ≤40s)."""

from __future__ import annotations

# Total target duration for absorption + interleaved skill write
TOTAL_BUDGET_SEC = 40.0

# Per-stage time budgets (seconds) — mind phase before落笔
STAGE_BUDGETS: dict[str, float] = {
    "recap": 5.5,
    "retrieve": 7.5,
    "compare": 5.2,
    "value": 10.0,
    "blueprint_intro": 2.8,
}

WRITE_PHASE_BUDGET_SEC = 13.0
FILE_COUNT = 5
FILE_WRITE_BUDGET_SEC = WRITE_PHASE_BUDGET_SEC / FILE_COUNT
L3_LINE_BUDGET_SEC = 2.2

RETRIEVE_SCAN_PAUSE_SEC = 1.8
VALUE_DWELL_SEC = 3.2
STAGE_GAP_SEC = 0.75

CHAR_DELAY_MS = 72
CHUNK_CHAR_SIZE = 3

# Left drawer file_delta typing: 1.3× faster than baseline
FILE_TYPING_SPEED_FACTOR = 1.3

PACKAGING_BUDGET_SEC = 1.2
