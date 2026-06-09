"""Shared type definitions for scanner findings."""

from typing import TypedDict


class Finding(TypedDict):
    """Standard finding dict produced by all scanners."""

    tool: str       # "custom", "caching_analyzer", "code_metrics", "config_validator"
    file: str       # relative path from Drupal root, forward slashes
    line: int       # 1-based line number
    severity: str   # "error", "warning", or "info"
    message: str    # human-readable description
    rule: str       # rule ID or detection method name
    category: str   # "security" or "performance"
