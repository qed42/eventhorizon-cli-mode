"""Tests for the config validator."""

from pathlib import Path

import pytest

from eventhorizon.scanner.config_analyzer import DrupalConfigAnalyzer
from eventhorizon.scanner.config_validator import (
    DrupalConfigValidator,
    run_config_validation,
)

CONFIG_DIR = Path(__file__).parent / "fixtures" / "sample_drupal" / "config" / "sync"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample_drupal"


@pytest.fixture
def config_data():
    analyzer = DrupalConfigAnalyzer(str(CONFIG_DIR))
    return analyzer.analyze_all_configs()


@pytest.fixture
def validator(config_data):
    return DrupalConfigValidator(config_data)


class TestConfigValidator:
    """Tests for DrupalConfigValidator."""

    def test_detects_orphaned_paragraphs(self, validator):
        """Paragraph types not referenced by any field should be flagged."""
        issues = validator.validate_all()
        orphaned = [i for i in issues if i.issue_type == "orphaned_entity"]
        # Both text and image paragraphs may be orphaned since they aren't referenced
        # via config deps from a non-paragraph field
        assert len(orphaned) > 0

    def test_detects_broken_field_references(self):
        """Field targeting a non-existent bundle should be flagged."""
        data = {
            "content_types": [{"id": "article"}],
            "block_types": [],
            "paragraphs": [],
            "taxonomies": [],
            "views": [],
            "fields": {
                "storages": [],
                "instances": [{
                    "entity_type": "node",
                    "bundle": "nonexistent_type",
                    "field_name": "field_test",
                    "dependencies": {},
                }],
            },
            "relationships": [],
        }
        validator = DrupalConfigValidator(data)
        issues = validator.validate_all()
        broken = [i for i in issues if i.issue_type == "broken_reference"]
        assert len(broken) >= 1
        assert "nonexistent_type" in broken[0].message

    def test_detects_circular_paragraph_deps(self):
        """A->B->A cycle should be detected."""
        data = {
            "content_types": [],
            "block_types": [],
            "paragraphs": [{"id": "alpha"}, {"id": "beta"}],
            "taxonomies": [],
            "views": [],
            "fields": {
                "storages": [],
                "instances": [
                    {
                        "entity_type": "paragraph",
                        "bundle": "alpha",
                        "field_name": "field_ref_beta",
                        "dependencies": {"config": ["paragraphs.paragraphs_type.beta"]},
                    },
                    {
                        "entity_type": "paragraph",
                        "bundle": "beta",
                        "field_name": "field_ref_alpha",
                        "dependencies": {"config": ["paragraphs.paragraphs_type.alpha"]},
                    },
                ],
            },
            "relationships": [],
        }
        validator = DrupalConfigValidator(data)
        issues = validator.validate_all()
        circular = [i for i in issues if i.issue_type == "circular_dependency"]
        assert len(circular) >= 1

    def test_detects_overly_complex_entities(self):
        """Content type with >30 fields should be flagged."""
        instances = [
            {"entity_type": "node", "bundle": "megabundle", "field_name": f"field_{i}", "dependencies": {}}
            for i in range(35)
        ]
        data = {
            "content_types": [{"id": "megabundle"}],
            "block_types": [],
            "paragraphs": [],
            "taxonomies": [],
            "views": [],
            "fields": {"storages": [], "instances": instances},
            "relationships": [],
        }
        validator = DrupalConfigValidator(data)
        issues = validator.validate_all()
        complex_issues = [i for i in issues if i.issue_type == "overly_complex"]
        assert len(complex_issues) >= 1

    def test_detects_unused_fields(self, validator):
        """field_orphaned has a storage but no instances."""
        issues = validator.validate_all()
        unused = [i for i in issues if i.issue_type == "unused_field"]
        orphaned_names = [i.entity_name for i in unused]
        assert "field_orphaned" in orphaned_names

    def test_detects_missing_field_descriptions(self, validator):
        """Fields without description/help text should be flagged."""
        issues = validator.validate_all()
        missing = [i for i in issues if i.issue_type == "missing_description"]
        assert len(missing) > 0

    def test_detects_duplicate_paragraphs(self):
        """Paragraph types with similar names should be flagged."""
        data = {
            "content_types": [],
            "block_types": [],
            "paragraphs": [{"id": "text_block"}, {"id": "textblock"}],
            "taxonomies": [],
            "views": [],
            "fields": {"storages": [], "instances": []},
            "relationships": [],
        }
        validator = DrupalConfigValidator(data)
        issues = validator.validate_all()
        dupes = [i for i in issues if i.issue_type == "consolidation_opportunity"]
        assert len(dupes) >= 1

    def test_validate_all_runs_all_checks(self, validator):
        """All check methods should execute without error."""
        issues = validator.validate_all()
        assert isinstance(issues, list)

    def test_validation_issue_to_finding_format(self):
        """run_config_validation should return standard finding dicts."""
        findings = run_config_validation(FIXTURES_DIR, CONFIG_DIR)
        required_keys = {"tool", "file", "line", "severity", "category", "rule", "message"}
        for finding in findings:
            assert required_keys.issubset(finding.keys()), (
                f"Missing keys: {required_keys - finding.keys()}"
            )
            assert finding["tool"] == "config_validator"

    def test_get_summary_stats(self, validator):
        validator.validate_all()
        stats = validator.get_summary_stats()
        assert "total" in stats
        assert "by_severity" in stats
        assert "by_type" in stats
        assert stats["total"] == len(validator.issues)
