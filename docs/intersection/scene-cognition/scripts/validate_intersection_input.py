from __future__ import annotations

REQUIRED_METRICS = {"volume", "capacity", "avg_delay_s"}


def validate_intersection_input(payload: dict) -> list[str]:
    errors: list[str] = []
    scope = payload.get("scope", {}) or {}
    metrics = payload.get("metrics", {}) or {}
    signal = payload.get("signal", {}) or {}
    context = payload.get("context", {}) or {}

    for field in sorted(REQUIRED_METRICS - set(metrics)):
        errors.append(f"missing metrics.{field}")
    if not scope.get("level"):
        errors.append("missing scope.level")
    if not scope.get("intersection_id") and not scope.get("name"):
        errors.append("missing scope.intersection_id or scope.name")

    capacity = metrics.get("capacity")
    volume = metrics.get("volume")
    try:
        capacity_value = float(capacity)
        volume_value = float(volume or 0)
    except (TypeError, ValueError):
        errors.append("metrics.volume and metrics.capacity must be numeric")
    else:
        if capacity_value <= 0 and volume_value > 0:
            errors.append("metrics.capacity must be positive when volume exists")

    data_quality = context.get("data_quality") or {}
    detector_online_rate = data_quality.get("detector_online_rate")
    if detector_online_rate is not None:
        try:
            if float(detector_online_rate) < 0.9:
                errors.append("context.data_quality.detector_online_rate below 0.9")
        except (TypeError, ValueError):
            errors.append("context.data_quality.detector_online_rate must be numeric")

    if not signal:
        errors.append("missing signal")
    elif "current_cycle_s" not in signal:
        errors.append("missing signal.current_cycle_s")

    return errors
