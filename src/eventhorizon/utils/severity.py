"""Severity level mapping utilities."""


# Maps internal severity values to display labels.
# "critical" is reserved for future use — no scanner currently emits it.
SEVERITY_MAP: dict[str, str] = {
    "error": "High",
    "warning": "Medium",
    "info": "Low",
}

# Ordering for sorting (lower number = higher priority)
SEVERITY_ORDER: dict[str, int] = {
    "error": 0,
    "High": 0,
    "warning": 1,
    "Medium": 1,
    "info": 2,
    "Low": 2,
}


def map_severity(raw: str) -> str:
    """Map internal severity (error/warning/info) to display label (High/Medium/Low)."""
    return SEVERITY_MAP.get(raw, raw)


def severity_sort_key(severity: str) -> int:
    """Return a sort key for severity ordering (High first)."""
    return SEVERITY_ORDER.get(severity, 99)
