"""Tests for the scanner modules."""

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample_drupal"


class TestStaticAnalyzer:
    """Tests for StaticAnalyzer."""

    def test_finds_security_issues(self):
        from eventhorizon.scanner.static_analyzer import StaticAnalyzer

        analyzer = StaticAnalyzer(
            drupal_root=str(FIXTURES_DIR),
            scan_targets=["modules/custom"],
            filter_name="custom",
        )
        findings = analyzer.run_all_scans()

        security_findings = [f for f in findings if f["category"] == "security"]
        assert len(security_findings) > 0, "Should find security issues in example_module"

        rules_found = {f["rule"] for f in security_findings}
        assert "insecure_unserialize" in rules_found
        assert "route_access_true" in rules_found
        assert "render_array_markup_xss" in rules_found

    def test_finds_performance_issues(self):
        from eventhorizon.scanner.static_analyzer import StaticAnalyzer

        analyzer = StaticAnalyzer(
            drupal_root=str(FIXTURES_DIR),
            scan_targets=["modules/custom"],
            filter_name="custom",
        )
        findings = analyzer.run_all_scans()

        perf_findings = [f for f in findings if f["category"] == "performance"]
        assert len(perf_findings) > 0, "Should find performance issues in example_module"

        rules_found = {f["rule"] for f in perf_findings}
        assert "debug_code_leftover" in rules_found
        assert "cache_disabled" in rules_found

    def test_finding_format(self):
        from eventhorizon.scanner.static_analyzer import StaticAnalyzer

        analyzer = StaticAnalyzer(
            drupal_root=str(FIXTURES_DIR),
            scan_targets=["modules/custom"],
            filter_name="custom",
        )
        findings = analyzer.run_all_scans()
        assert len(findings) > 0

        required_keys = {"tool", "file", "line", "severity", "message", "rule", "category"}
        for finding in findings:
            assert required_keys.issubset(finding.keys()), f"Missing keys in finding: {required_keys - finding.keys()}"

    def test_relative_file_paths(self):
        from eventhorizon.scanner.static_analyzer import StaticAnalyzer

        analyzer = StaticAnalyzer(
            drupal_root=str(FIXTURES_DIR),
            scan_targets=["modules/custom"],
            filter_name="custom",
        )
        findings = analyzer.run_all_scans()

        for finding in findings:
            assert not finding["file"].startswith("/"), f"File path should be relative: {finding['file']}"

    def test_no_findings_for_empty_targets(self):
        from eventhorizon.scanner.static_analyzer import StaticAnalyzer

        analyzer = StaticAnalyzer(
            drupal_root=str(FIXTURES_DIR),
            scan_targets=["nonexistent/path"],
            filter_name="custom",
        )
        findings = analyzer.run_all_scans()
        assert findings == []

    def test_progress_callback(self):
        from eventhorizon.scanner.static_analyzer import StaticAnalyzer

        scanned = []
        analyzer = StaticAnalyzer(
            drupal_root=str(FIXTURES_DIR),
            scan_targets=["modules/custom"],
            filter_name="custom",
        )
        analyzer.run_all_scans(progress_callback=lambda f: scanned.append(f))
        assert len(scanned) > 0


class TestCachingAnalyzer:
    """Tests for SmartCachingAnalyzer."""

    def test_finds_caching_issues(self):
        from eventhorizon.scanner.caching_analyzer import run_caching_analysis

        findings = run_caching_analysis(
            drupal_root=FIXTURES_DIR,
            scan_targets=["modules/custom"],
        )
        assert len(findings) > 0, "Should find caching issues in example_module"

    def test_all_findings_are_performance(self):
        from eventhorizon.scanner.caching_analyzer import run_caching_analysis

        findings = run_caching_analysis(
            drupal_root=FIXTURES_DIR,
            scan_targets=["modules/custom"],
        )
        for f in findings:
            assert f.get("category") == "performance"

    def test_finding_has_required_keys(self):
        from eventhorizon.scanner.caching_analyzer import run_caching_analysis

        findings = run_caching_analysis(
            drupal_root=FIXTURES_DIR,
            scan_targets=["modules/custom"],
        )
        required = {"tool", "file", "line", "severity", "message", "rule", "category"}
        for finding in findings:
            assert required.issubset(finding.keys()), f"Missing keys: {required - finding.keys()}"
