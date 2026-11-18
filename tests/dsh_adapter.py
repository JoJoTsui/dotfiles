"""Classify the installed DSH TUI adapter's own compatibility report."""
import json


def capability_status(output, installed_version):
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return {"status": "unknown"}
    if not isinstance(data, dict) or data.get("runtimeVersion") != installed_version:
        return {"status": "unknown"}
    validated = data.get("validated")
    if not isinstance(validated, bool):
        return {"status": "unknown"}
    return {"status": "validated" if validated else "unvalidated",
            "runtime_version": installed_version}
