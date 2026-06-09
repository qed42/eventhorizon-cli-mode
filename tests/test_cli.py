"""Tests for the CLI entry point."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from eventhorizon.cli import main

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample_drupal"


class TestCLI:

    def test_shows_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "analyze" in result.output

    def test_shows_version(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_shows_splash_without_command(self):
        runner = CliRunner()
        result = runner.invoke(main, [])
        assert result.exit_code == 0
        assert "EVENT" in result.output or "HORIZON" in result.output or "eventhorizon" in result.output.lower()

    def test_analyze_invalid_path(self):
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", "/nonexistent/path"])
        assert result.exit_code != 0

    def test_analyze_non_drupal_path(self, tmp_path):
        # Create an empty directory (not a Drupal root)
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", str(tmp_path)])
        assert result.exit_code == 2

    def test_analyze_sample_drupal(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            result = runner.invoke(main, [
                "analyze", str(FIXTURES_DIR),
                "--filter", "custom",
                "--format", "csv",
                "--output", td,
            ])
            # Should find high-severity issues -> exit code 1
            assert result.exit_code in (0, 1)

            # Check report files were created
            output_path = Path(td)
            csv_files = list(output_path.glob("*.csv"))
            assert len(csv_files) > 0, f"Expected CSV files in {td}"

    def test_analyze_security_only(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            result = runner.invoke(main, [
                "analyze", str(FIXTURES_DIR),
                "--type", "security",
                "--format", "csv",
                "--output", td,
            ])
            assert result.exit_code in (0, 1)

            output_path = Path(td)
            csv_files = list(output_path.glob("security_*.csv"))
            assert len(csv_files) > 0
            perf_files = list(output_path.glob("performance_*.csv"))
            assert len(perf_files) == 0

    def test_analyze_performance_only(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            result = runner.invoke(main, [
                "analyze", str(FIXTURES_DIR),
                "--type", "performance",
                "--format", "csv",
                "--output", td,
            ])
            assert result.exit_code in (0, 1)

            output_path = Path(td)
            perf_files = list(output_path.glob("performance_*.csv"))
            assert len(perf_files) > 0

    def test_analyze_xlsx_format(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            result = runner.invoke(main, [
                "analyze", str(FIXTURES_DIR),
                "--format", "xlsx",
                "--output", td,
            ])
            assert result.exit_code in (0, 1)

            output_path = Path(td)
            xlsx_files = list(output_path.glob("*.xlsx"))
            assert len(xlsx_files) > 0


class TestDrupalDetection:

    def test_validates_drupal_path(self):
        from eventhorizon.utils.drupal_detection import validate_drupal_path

        assert validate_drupal_path(FIXTURES_DIR) is True

    def test_rejects_non_drupal_path(self, tmp_path):
        from eventhorizon.utils.drupal_detection import validate_drupal_path

        assert validate_drupal_path(tmp_path) is False

    def test_detects_scan_targets(self):
        from eventhorizon.utils.drupal_detection import detect_scan_targets

        targets = detect_scan_targets(FIXTURES_DIR, "all")
        assert "custom" in targets
        assert "contrib" in targets

    def test_custom_filter(self):
        from eventhorizon.utils.drupal_detection import detect_scan_targets

        targets = detect_scan_targets(FIXTURES_DIR, "custom")
        assert "custom" in targets
        assert "contrib" not in targets


class TestModuleFinder:

    def test_discovers_modules(self):
        from eventhorizon.discovery.module_finder import discover_modules

        result = discover_modules(FIXTURES_DIR, ["modules/custom", "modules/contrib", "themes/custom"])
        assert len(result.modules) >= 2  # example_module + contrib_module + possibly theme
        assert len(result.custom_modules) >= 1
        assert len(result.contrib_modules) >= 1

    def test_module_names(self):
        from eventhorizon.discovery.module_finder import discover_modules

        result = discover_modules(FIXTURES_DIR, ["modules/custom"])
        names = {m.name for m in result.modules}
        assert "example_module" in names
