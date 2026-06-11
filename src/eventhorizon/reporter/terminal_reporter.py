"""Rich terminal summary reporter."""

from __future__ import annotations

from typing import Any, Dict, List

from rich.console import Console
from rich.table import Table

from eventhorizon.utils.severity import map_severity, severity_sort_key


def print_summary(
    findings: List[Dict[str, Any]],
    report_type: str,
    console: Console | None = None,
) -> Dict[str, int]:
    """Print a summary table to the terminal and return severity counts.

    Args:
        findings: List of finding dicts.
        report_type: Label for the report (e.g. "Performance", "Security").
        console: Optional Rich Console instance.

    Returns:
        Dict with keys "High", "Medium", "Low" and their counts.
    """
    if console is None:
        console = Console()

    counts = {"High": 0, "Medium": 0, "Low": 0}
    for f in findings:
        display = map_severity(f.get("severity", "info"))
        counts[display] = counts.get(display, 0) + 1

    total = len(findings)

    console.print(f"\n[bold]{report_type} Analysis Summary[/]")
    console.print(f"  Total issues: [bold]{total}[/]\n")

    summary_table = Table(show_header=True, header_style="bold")
    summary_table.add_column("Severity", style="bold", width=10)
    summary_table.add_column("Count", justify="right", width=8)

    severity_styles = {"High": "red", "Medium": "yellow", "Low": "blue"}
    for sev in ["High", "Medium", "Low"]:
        style = severity_styles[sev]
        summary_table.add_row(f"[{style}]{sev}[/]", str(counts[sev]))

    console.print(summary_table)

    if total == 0:
        console.print("[green]No issues found![/]\n")
        return counts

    # Top issues table (up to 15 rows)
    detail_table = Table(
        show_header=True,
        header_style="bold cyan",
        title=f"Top {report_type} Issues",
        show_lines=False,
        pad_edge=True,
    )
    detail_table.add_column("Severity", width=8)
    detail_table.add_column("Rule", width=26)
    detail_table.add_column("File", width=40)
    detail_table.add_column("Line", justify="right", width=6)
    detail_table.add_column("Message", width=60, no_wrap=True)

    sorted_findings = sorted(findings, key=lambda x: severity_sort_key(x.get("severity", "info")))

    for f in sorted_findings[:15]:
        sev = map_severity(f.get("severity", "info"))
        style = severity_styles.get(sev, "white")
        detail_table.add_row(
            f"[{style}]{sev}[/]",
            f.get("rule", ""),
            f.get("file", ""),
            str(f.get("line", "")),
            (f.get("message", "") or "")[:60],
        )

    console.print()
    console.print(detail_table)

    if total > 15:
        console.print(f"\n  [dim]... and {total - 15} more issues. See exported files for full report.[/]")
    else:
        console.print(f"\n  [dim]Messages truncated in terminal. See exported files for full details.[/]")

    console.print()
    return counts
