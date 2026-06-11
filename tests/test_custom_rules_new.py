"""Tests for additional custom rules."""

from pathlib import Path

from eventhorizon.scanner.static_analyzer import StaticAnalyzer, _load_rules

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample_drupal"


def _get_findings():
    analyzer = StaticAnalyzer(
        drupal_root=str(FIXTURES_DIR),
        scan_targets=["modules/custom"],
        filter_name="custom",
    )
    return analyzer.run_all_scans()


def _rules_found(findings):
    return {f["rule"] for f in findings}


class TestTwigRules:
    """Tests for Twig-specific rules."""

    def test_twig_dump_debug_detected(self):
        findings = _get_findings()
        assert "twig_dump_debug" in _rules_found(findings)

    def test_twig_inline_js_detected(self):
        findings = _get_findings()
        assert "twig_inline_js" in _rules_found(findings)

    def test_twig_inline_styles_detected(self):
        findings = _get_findings()
        assert "twig_inline_styles" in _rules_found(findings)

    def test_twig_raw_filter_detected(self):
        findings = _get_findings()
        assert "twig_raw_filter" in _rules_found(findings)

    def test_twig_safe_join_detected(self):
        findings = _get_findings()
        assert "twig_safe_join" in _rules_found(findings)


class TestPHPRules:
    """Tests for PHP-based rules."""

    def test_anonymous_session_tempstore_detected(self):
        findings = _get_findings()
        assert "anonymous_session_tempstore" in _rules_found(findings)

    def test_cache_max_age_zero_api_detected(self):
        findings = _get_findings()
        assert "cache_max_age_zero_api" in _rules_found(findings)

    def test_kernel_events_request_response_detected(self):
        findings = _get_findings()
        assert "kernel_events_request_response" in _rules_found(findings)

    def test_load_multiple_all_entities_detected(self):
        findings = _get_findings()
        assert "load_multiple_all_entities" in _rules_found(findings)

    def test_page_cache_kill_switch_detected(self):
        findings = _get_findings()
        assert "page_cache_kill_switch" in _rules_found(findings)

    def test_theme_preprocess_db_detected(self):
        findings = _get_findings()
        assert "theme_preprocess_db" in _rules_found(findings)

    def test_user_cache_context_broad_detected(self):
        findings = _get_findings()
        assert "user_cache_context_broad" in _rules_found(findings)


class TestRuleCount:
    """Test total rule count."""

    def test_total_rule_count_is_45(self):
        _load_rules.cache_clear()
        rules = _load_rules()
        assert len(rules) == 45, f"Expected 45 rules, got {len(rules)}"
