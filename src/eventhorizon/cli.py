"""EventHorizon CLI — Drupal codebase static analysis from the terminal."""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from eventhorizon import __version__
from eventhorizon.discovery.module_finder import discover_modules
from eventhorizon.reporter import csv_reporter, xlsx_reporter
from eventhorizon.reporter.terminal_reporter import print_summary
from eventhorizon.scanner.caching_analyzer import run_caching_analysis
from eventhorizon.scanner.code_metrics import run_code_metrics
from eventhorizon.scanner.config_validator import run_config_validation
from eventhorizon.scanner.static_analyzer import StaticAnalyzer
from eventhorizon.splash import show_splash
from eventhorizon.utils.drupal_detection import (
    build_scan_targets,
    detect_project_structure,
    flatten_targets,
)
from eventhorizon.utils.severity import map_severity


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(name)s %(levelname)s: %(message)s",
        stream=sys.stderr,
    )


class _DefaultGroup(click.Group):
    """Click group that defaults to 'analyze' when an unknown subcommand is given."""

    def parse_args(self, ctx: click.Context, args: List[str]) -> List[str]:
        # If the first arg isn't a registered command or option, prepend 'analyze'
        if args and not args[0].startswith("-") and args[0] not in self.commands:
            args = ["analyze"] + args
        return super().parse_args(ctx, args)


@click.group(cls=_DefaultGroup, invoke_without_command=True)
@click.version_option(__version__, prog_name="eventhorizon")
@click.pass_context
def main(ctx: click.Context) -> None:
    """EventHorizon — Drupal codebase static analysis CLI."""
    if ctx.invoked_subcommand is None:
        stdout_console = Console()
        show_splash(stdout_console)
        click.echo(ctx.get_help())


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option(
    "--type", "analysis_type",
    type=click.Choice(["performance", "security", "code-metrics", "all"], case_sensitive=False),
    default="all",
    help="Type of analysis to run.",
)
@click.option(
    "--filter", "filter_name",
    type=click.Choice(["custom", "contrib", "all"], case_sensitive=False),
    default="custom",
    help="Scope analysis to custom, contrib, or all modules.",
)
@click.option(
    "--format", "output_format",
    type=click.Choice(["csv", "xlsx", "both"], case_sensitive=False),
    default="both",
    help="Output file format.",
)
@click.option(
    "--output", "output_dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Output directory for report files. Defaults to <path>/eventhorizon-reports.",
)
@click.option(
    "--site",
    default=None,
    help="For multisite projects: site name to scan (e.g. 'site1').",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging.")
@click.option("--quiet", "-q", is_flag=True, help="Suppress terminal output (only exit code and exports).")
@click.pass_context
def analyze(
    ctx: click.Context,
    path: str,
    analysis_type: str,
    filter_name: str,
    output_format: str,
    output_dir: str,
    site: str,
    verbose: bool,
    quiet: bool,
) -> None:
    """Analyze a Drupal codebase for performance and security issues."""
    _setup_logging(verbose)

    stderr_console = Console(stderr=True)
    stdout_console = Console(quiet=quiet)

    show_splash(stdout_console)

    # Detect project structure
    structure = detect_project_structure(Path(path))

    if not structure.valid:
        stderr_console.print(
            f"[bold red]Error:[/] '{path}' does not appear to be a Drupal codebase.\n"
            f"  {'; '.join(structure.errors) or 'Expected modules/, core/, themes/, or sites/.'}"
        )
        ctx.exit(2)
        return

    drupal_root = structure.drupal_root

    # Default output dir to inside the project root, timestamped per run
    if output_dir is None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_dir = str(structure.project_root / "eventhorizon-reports" / timestamp)

    # Multisite info
    if structure.sites and not site:
        stderr_console.print(
            f"  [bold]Multisite detected.[/] Sites: {', '.join(structure.sites)}\n"
            "  Use --site <name> to scan a specific site.\n"
        )

    if site and site not in structure.sites:
        stderr_console.print(
            f"[bold red]Error:[/] Site '{site}' not found.\n"
            f"  Available sites: {', '.join(structure.sites) or '(none detected)'}"
        )
        ctx.exit(2)
        return

    # Build scan targets
    targets = build_scan_targets(structure, filter_name, site=site)
    flat_targets = flatten_targets(targets)

    if not flat_targets:
        stderr_console.print(
            f"[bold red]Error:[/] No scan targets found for filter '{filter_name}' in '{drupal_root}'.\n"
            "  No custom code paths were discovered."
        )
        ctx.exit(2)
        return

    # Discover modules
    discovery = discover_modules(drupal_root, flat_targets)

    # Show structure info
    type_label = structure.project_type.capitalize()
    if structure.webroot:
        type_label += f" (webroot: {structure.webroot})"
    stdout_console.print(
        f"  [bold]Project type:[/] {type_label}\n"
        f"  [bold]Drupal root:[/] {drupal_root}\n"
        f"  [bold]Filter:[/] {filter_name}\n"
        f"  [bold]Modules found:[/] {len(discovery.modules)} "
        f"({len(discovery.custom_modules)} custom, {len(discovery.contrib_modules)} contrib)\n"
        f"  [bold]Scan targets:[/] {', '.join(flat_targets)}\n"
    )

    if not discovery.modules:
        stderr_console.print("[yellow]Warning:[/] No modules discovered. Check that the path contains .info.yml files.")

    # --- Run Scans ---
    all_findings: List[Dict[str, Any]] = []
    scanned_files: Set[str] = set()

    def _progress_callback(file_path: str) -> None:
        scanned_files.add(file_path)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=stderr_console,
    ) as progress:
        # Static analysis (rules-based)
        if analysis_type in ("all", "security", "performance"):
            task = progress.add_task("Running static analysis...", total=None)
            analyzer = StaticAnalyzer(
                drupal_root=str(drupal_root),
                scan_targets=flat_targets,
                filter_name=filter_name,
            )
            static_findings = analyzer.run_all_scans(progress_callback=_progress_callback)
            all_findings.extend(static_findings)
            progress.update(task, description=f"Static analysis: {len(static_findings)} issues found")

        # Caching analysis (for performance reports)
        if analysis_type in ("all", "performance"):
            task = progress.add_task("Running caching analysis...", total=None)
            caching_findings = run_caching_analysis(
                drupal_root=drupal_root,
                scan_targets=flat_targets,
                progress_callback=_progress_callback,
            )
            all_findings.extend(caching_findings)
            progress.update(task, description=f"Caching analysis: {len(caching_findings)} issues found")

        # Code metrics analysis
        if analysis_type in ("all", "code-metrics"):
            task = progress.add_task("Running code metrics analysis...", total=None)
            metrics_findings = run_code_metrics(
                drupal_root=drupal_root,
                scan_targets=flat_targets,
                progress_callback=_progress_callback,
            )
            all_findings.extend(metrics_findings)
            progress.update(task, description=f"Code metrics: {len(metrics_findings)} issues found")

        # Config validation (runs for security, performance, and all)
        if analysis_type in ("all", "security", "performance"):
            config_sync = structure.config_sync_dir
            if config_sync and config_sync.is_dir():
                task = progress.add_task("Running config validation...", total=None)
                config_findings = run_config_validation(
                    drupal_root=drupal_root,
                    config_sync_dir=config_sync,
                    progress_callback=_progress_callback,
                )
                all_findings.extend(config_findings)
                progress.update(task, description=f"Config validation: {len(config_findings)} issues found")

    stdout_console.print(f"  [bold]Files scanned:[/] {len(scanned_files)}")
    stdout_console.print(f"  [bold]Total issues:[/] {len(all_findings)}\n")

    # --- Filter by category ---
    perf_findings = [f for f in all_findings if f.get("category") == "performance"]
    sec_findings = [f for f in all_findings if f.get("category") == "security"]

    # Derive project name from directory
    project_name = drupal_root.name.replace(" ", "_").lower()
    out_path = Path(output_dir)
    exported_files: List[str] = []

    has_high = False

    # --- Performance Report ---
    if analysis_type in ("all", "performance") and perf_findings:
        counts = print_summary(perf_findings, "Performance", stdout_console)
        if counts.get("High", 0) > 0:
            has_high = True

        base = f"performance_report_{project_name}_{filter_name}"
        if output_format in ("csv", "both"):
            p = csv_reporter.export_csv(perf_findings, out_path / f"{base}.csv")
            exported_files.append(str(p))
        if output_format in ("xlsx", "both"):
            p = xlsx_reporter.export_xlsx(perf_findings, out_path / f"{base}.xlsx")
            exported_files.append(str(p))

    # --- Security Report ---
    if analysis_type in ("all", "security") and sec_findings:
        counts = print_summary(sec_findings, "Security", stdout_console)
        if counts.get("High", 0) > 0:
            has_high = True

        base = f"security_report_{project_name}_{filter_name}"
        if output_format in ("csv", "both"):
            p = csv_reporter.export_csv(sec_findings, out_path / f"{base}.csv")
            exported_files.append(str(p))
        if output_format in ("xlsx", "both"):
            p = xlsx_reporter.export_xlsx(sec_findings, out_path / f"{base}.xlsx")
            exported_files.append(str(p))

    # --- Code Metrics Report ---
    metrics_findings = [f for f in all_findings if f.get("tool") == "code_metrics"]
    if analysis_type in ("all", "code-metrics") and metrics_findings:
        counts = print_summary(metrics_findings, "Code Metrics", stdout_console)
        if counts.get("High", 0) > 0:
            has_high = True

        base = f"code_metrics_report_{project_name}_{filter_name}"
        if output_format in ("csv", "both"):
            p = csv_reporter.export_csv(metrics_findings, out_path / f"{base}.csv")
            exported_files.append(str(p))
        if output_format in ("xlsx", "both"):
            p = xlsx_reporter.export_xlsx(metrics_findings, out_path / f"{base}.xlsx")
            exported_files.append(str(p))

    # --- No issues ---
    if not perf_findings and not sec_findings and not metrics_findings:
        stdout_console.print("[bold green]No issues found! Your codebase looks clean.[/]\n")

    # --- Exported files summary ---
    if exported_files:
        stdout_console.print("[bold]Exported reports:[/]")
        for fp in exported_files:
            stdout_console.print(f"  [cyan]{fp}[/]")
        stdout_console.print()

    # --- Final status ---
    if has_high:
        stdout_console.print("[bold red]High-severity issues detected.[/]\n")


def cli() -> None:
    """Entry point wrapper that translates the analyze return into an exit code.

    This avoids calling sys.exit() directly inside Click commands,
    which raises SystemExit and can cause terminal windows to close.
    """
    # standalone_mode=False prevents Click from calling sys.exit()
    # and instead returns the exit code (or None for 0).
    try:
        result = main(standalone_mode=False)
        sys.exit(result or 0)
    except SystemExit as e:
        sys.exit(e.code)


if __name__ == "__main__":
    cli()
