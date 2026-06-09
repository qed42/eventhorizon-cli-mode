"""Tests for the code metrics analyzer."""

from pathlib import Path

import pytest

from eventhorizon.scanner.code_metrics import (
    calculate_ccn,
    calculate_loc,
    calculate_mi,
    count_antipatterns,
    run_code_metrics,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample_drupal"


class TestCalculateLoc:
    """Tests for calculate_loc()."""

    def test_calculate_loc_skips_comments(self):
        source = """
        // This is a comment
        $a = 1;
        /* block comment */
        $b = 2;
        # hash comment
        $c = 3;
        """
        assert calculate_loc(source) == 3

    def test_calculate_loc_empty_returns_zero(self):
        assert calculate_loc("") == 0
        assert calculate_loc("   \n\n  ") == 0


class TestCalculateCcn:
    """Tests for calculate_ccn()."""

    def test_calculate_ccn_linear_function(self):
        source = """
        $a = 1;
        $b = 2;
        return $a + $b;
        """
        assert calculate_ccn(source) == 1

    def test_calculate_ccn_with_branches(self):
        source = """
        if ($a) { $b = 1; }
        elseif ($c) { $d = 2; }
        for ($i = 0; $i < 10; $i++) { $e = $i; }
        """
        assert calculate_ccn(source) == 4  # 1 + if + elseif + for

    def test_calculate_ccn_logical_operators(self):
        source = """
        if ($a && $b || $c) { return true; }
        """
        assert calculate_ccn(source) == 4  # 1 + if + && + ||


class TestCalculateMi:
    """Tests for calculate_mi()."""

    def test_calculate_mi_known_values(self):
        # LOC=10, CCN=1 should give a high MI (well-maintained)
        mi = calculate_mi(10, 1)
        assert mi > 65

        # LOC=200, CCN=30 should give a low MI
        mi_low = calculate_mi(200, 30)
        assert mi_low < 65

    def test_calculate_mi_zero_loc(self):
        assert calculate_mi(0, 0) == 100.0


class TestCountAntipatterns:
    """Tests for count_antipatterns()."""

    def test_count_antipatterns_service_locator(self):
        source = r"""
        $service = \Drupal::service('foo');
        $db = \Drupal::database();
        """
        counts = count_antipatterns(source)
        assert counts.get("service_locator", 0) == 2

    def test_count_antipatterns_deep_arrays(self):
        source = "$data = $a['x']['y']['z'];"
        counts = count_antipatterns(source)
        assert counts.get("deep_array_access", 0) >= 1

    def test_count_antipatterns_magic_keys(self):
        source = "$build['#markup'] = 'test';"
        counts = count_antipatterns(source)
        assert counts.get("magic_render_key", 0) >= 1


class TestRunCodeMetrics:
    """Integration tests for run_code_metrics()."""

    def test_run_code_metrics_integration(self):
        findings = run_code_metrics(
            drupal_root=FIXTURES_DIR,
            scan_targets=["modules/custom"],
        )
        assert isinstance(findings, list)
        assert len(findings) > 0

    def test_findings_standard_format(self):
        findings = run_code_metrics(
            drupal_root=FIXTURES_DIR,
            scan_targets=["modules/custom"],
        )
        required_keys = {"tool", "file", "line", "severity", "message", "rule", "category"}
        for finding in findings:
            assert required_keys.issubset(finding.keys()), (
                f"Missing keys: {required_keys - finding.keys()}"
            )
            assert finding["tool"] == "code_metrics"
            assert finding["category"] == "performance"

    def test_high_complexity_flagged(self):
        findings = run_code_metrics(
            drupal_root=FIXTURES_DIR,
            scan_targets=["modules/custom"],
        )
        ccn_findings = [f for f in findings if f["rule"] == "high_cyclomatic_complexity"]
        assert len(ccn_findings) > 0, "Should flag complex_module_process_data as high CCN"
