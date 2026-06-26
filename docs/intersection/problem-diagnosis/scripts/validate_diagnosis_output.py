from __future__ import annotations

REQUIRED_FIELDS = {"issues", "priority_order"}
REQUIRED_ISSUE_FIELDS = {
    "severity",
    "confidence",
    "evidence",
    "root_cause",
    "control_leverage",
}
VALID_SEVERITIES = {"high", "medium", "low"}
VALID_CONTROL_LEVERAGE = {"high", "medium", "low", "none"}


def validate_diagnosis_output(diagnosis: dict) -> list[str]:
    errors = [f"missing field: {field}" for field in sorted(REQUIRED_FIELDS - set(diagnosis))]
    issues = diagnosis.get("issues")
    priority_order = diagnosis.get("priority_order")

    if issues is None or priority_order is None:
        return errors
    if not isinstance(issues, list):
        errors.append("issues must be a list")
        return errors
    if not isinstance(priority_order, list):
        errors.append("priority_order must be a list")
        return errors

    issue_codes: list[str] = []
    for index, issue in enumerate(issues):
        if not isinstance(issue, dict):
            errors.append(f"issues[{index}] must be an object")
            continue
        issue_code = issue.get("issue_code") or issue.get("code")
        if not issue_code:
            errors.append(f"issues[{index}] missing field: issue_code")
        else:
            issue_codes.append(str(issue_code))
        for field in sorted(REQUIRED_ISSUE_FIELDS - set(issue)):
            errors.append(f"issues[{index}] missing field: {field}")
        if "severity" in issue and issue["severity"] not in VALID_SEVERITIES:
            errors.append(f"issues[{index}].severity invalid: {issue['severity']}")
        if "control_leverage" in issue and issue["control_leverage"] not in VALID_CONTROL_LEVERAGE:
            errors.append(f"issues[{index}].control_leverage invalid: {issue['control_leverage']}")
        if "confidence" in issue:
            try:
                confidence = float(issue["confidence"])
            except (TypeError, ValueError):
                errors.append(f"issues[{index}].confidence must be numeric")
            else:
                if confidence < 0 or confidence > 1:
                    errors.append(f"issues[{index}].confidence must be between 0 and 1")
        evidence = issue.get("evidence")
        if "evidence" in issue and not isinstance(evidence, list):
            errors.append(f"issues[{index}].evidence must be a list")
        if isinstance(evidence, list) and not evidence:
            errors.append(f"issues[{index}].evidence must not be empty")

    unknown_priority = [code for code in priority_order if str(code) not in issue_codes]
    if unknown_priority:
        errors.append("priority_order contains unknown issue codes: " + ", ".join(map(str, unknown_priority)))
    if issue_codes and [str(code) for code in priority_order[: len(issue_codes)]] != issue_codes[: len(priority_order)]:
        errors.append("priority_order should follow issues ordering")
    return errors
