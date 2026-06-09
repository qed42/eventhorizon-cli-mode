"""Tests for the config analyzer."""

from pathlib import Path

import pytest

from eventhorizon.scanner.config_analyzer import DrupalConfigAnalyzer

CONFIG_DIR = Path(__file__).parent / "fixtures" / "sample_drupal" / "config" / "sync"


@pytest.fixture
def analyzer():
    return DrupalConfigAnalyzer(str(CONFIG_DIR))


class TestConfigAnalyzer:
    """Tests for DrupalConfigAnalyzer."""

    def test_parse_content_types(self, analyzer):
        types = analyzer.parse_content_types()
        ids = {ct["id"] for ct in types}
        assert "article" in ids
        assert "page" in ids

    def test_parse_fields(self, analyzer):
        fields = analyzer.parse_fields()
        storage_names = {s["field_name"] for s in fields["storages"]}
        assert "field_body" in storage_names

        # Check storage has correct entity type
        body_storage = [s for s in fields["storages"] if s["field_name"] == "field_body"][0]
        assert body_storage["entity_type"] == "node"

    def test_parse_views(self, analyzer):
        views = analyzer.parse_views()
        view_ids = {v["id"] for v in views}
        assert "content" in view_ids

    def test_parse_taxonomies(self, analyzer):
        taxonomies = analyzer.parse_taxonomies()
        vocab_ids = {t["id"] for t in taxonomies}
        assert "tags" in vocab_ids

    def test_parse_paragraphs(self, analyzer):
        paragraphs = analyzer.parse_paragraphs()
        para_ids = {p["id"] for p in paragraphs}
        assert "text" in para_ids
        assert "image" in para_ids

    def test_build_relationships(self, analyzer):
        relationships = analyzer.build_relationships()
        # field_body should be linked to node.article
        field_of_rels = [r for r in relationships if r["type"] == "field_of"]
        targets = {r["target"] for r in field_of_rels}
        assert "node.article" in targets

    def test_analyze_all_returns_complete_data(self, analyzer):
        result = analyzer.analyze_all_configs()
        expected_keys = {"content_types", "block_types", "paragraphs", "fields", "views", "taxonomies", "relationships"}
        assert expected_keys == set(result.keys())

    def test_missing_config_dir_returns_empty(self):
        analyzer = DrupalConfigAnalyzer("/nonexistent/path")
        result = analyzer.analyze_all_configs()
        assert result["content_types"] == []
        assert result["views"] == []
        assert result["fields"]["storages"] == []
