"""CSV file report exporter."""

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List

from eventhorizon.utils.severity import map_severity

log = logging.getLogger("EventHorizon.CSVReporter")

HEADERS = ["Category", "Severity", "File", "Line", "Rule", "Message", "Tool", "Recommendation"]


def export_csv(
    findings: List[Dict[str, Any]],
    output_path: Path,
) -> Path:
    """Write findings to a CSV file.

    Args:
        findings: List of finding dicts.
        output_path: Full path for the output CSV file.

    Returns:
        The path to the written file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        for finding in findings:
            writer.writerow([
                finding.get("category", "").capitalize(),
                map_severity(finding.get("severity", "info")),
                finding.get("file", ""),
                finding.get("line", ""),
                finding.get("rule", ""),
                finding.get("message", ""),
                finding.get("tool", ""),
                finding.get("recommendation", ""),
            ])

    log.info(f"CSV report written to {output_path} ({len(findings)} rows)")
    return output_path
