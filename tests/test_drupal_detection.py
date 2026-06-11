"""Tests for Drupal project structure detection."""

from pathlib import Path

from eventhorizon.utils.drupal_detection import (
    build_scan_targets,
    detect_project_structure,
    detect_scan_targets,
    flatten_targets,
    validate_drupal_path,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RESTRICTED_FIXTURE = FIXTURES_DIR / "sample_drupal"
STANDARD_FIXTURE = FIXTURES_DIR / "sample_drupal_standard"
MULTISITE_FIXTURE = FIXTURES_DIR / "sample_drupal_multisite"


class TestDetectProjectStructure:

    def test_restricted_layout(self):
        s = detect_project_structure(RESTRICTED_FIXTURE)
        assert s.valid is True
        assert s.project_type == "restricted"
        assert s.webroot is None
        assert s.drupal_root == RESTRICTED_FIXTURE.resolve()
        assert s.config_path == "config/sync"
        assert s.config_sync_dir == (RESTRICTED_FIXTURE / "config" / "sync").resolve()

    def test_standard_layout(self):
        s = detect_project_structure(STANDARD_FIXTURE)
        assert s.valid is True
        assert s.project_type == "standard"
        assert s.webroot == "web"
        assert s.drupal_root == (STANDARD_FIXTURE / "web").resolve()
        assert s.config_path == "config/sync"

    def test_standard_layout_discovers_modules(self):
        s = detect_project_structure(STANDARD_FIXTURE)
        # Should discover web/modules/custom as a module root
        assert len(s.module_roots) > 0
        assert len(s.theme_roots) > 0
        # Scanner paths should be webroot-relative (no "web/" prefix)
        for root in s.module_roots:
            assert not root.startswith("web/"), f"module_root should be webroot-relative: {root}"

    def test_standard_layout_pointed_at_webroot(self):
        """User runs `eh analyze /path/to/project/web` — should detect parent as project root."""
        s = detect_project_structure(STANDARD_FIXTURE / "web")
        assert s.valid is True
        assert s.project_type == "standard"
        assert s.webroot == "web"
        assert s.project_root == STANDARD_FIXTURE.resolve()
        assert s.drupal_root == (STANDARD_FIXTURE / "web").resolve()

    def test_multisite_detection(self):
        s = detect_project_structure(MULTISITE_FIXTURE)
        assert s.valid is True
        assert s.project_type == "multisite"
        assert s.webroot == "web"
        assert "site1" in s.sites
        assert "site2" in s.sites
        assert "default" not in s.sites

    def test_config_outside_webroot(self):
        """Standard layout: config/sync lives at project root, not inside web/."""
        s = detect_project_structure(STANDARD_FIXTURE)
        assert s.config_path == "config/sync"
        assert s.config_sync_dir.is_dir()

    def test_excludes_vendor_modules(self, tmp_path):
        """Modules inside vendor/ should not be discovered."""
        (tmp_path / "vendor" / "some_pkg" / "fake_mod").mkdir(parents=True)
        (tmp_path / "vendor" / "some_pkg" / "fake_mod" / "fake_mod.info.yml").write_text(
            "name: Fake\ntype: module"
        )
        (tmp_path / "modules" / "custom" / "real_mod").mkdir(parents=True)
        (tmp_path / "modules" / "custom" / "real_mod" / "real_mod.info.yml").write_text(
            "name: Real\ntype: module"
        )

        s = detect_project_structure(tmp_path)
        assert s.valid is True
        all_paths = s.custom_code_paths
        assert not any("vendor" in p for p in all_paths)
        assert any("modules/custom" in p for p in all_paths)

    def test_excludes_core_modules(self, tmp_path):
        """Modules inside core/ should not be discovered."""
        (tmp_path / "core" / "modules" / "node").mkdir(parents=True)
        (tmp_path / "core" / "modules" / "node" / "node.info.yml").write_text(
            "name: Node\ntype: module"
        )
        (tmp_path / "modules" / "custom" / "my_mod").mkdir(parents=True)
        (tmp_path / "modules" / "custom" / "my_mod" / "my_mod.info.yml").write_text(
            "name: My Mod\ntype: module"
        )

        s = detect_project_structure(tmp_path)
        assert not any("core" in p for p in s.custom_code_paths)

    def test_invalid_directory(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        s = detect_project_structure(empty)
        assert s.valid is False
        assert len(s.errors) > 0

    def test_nonexistent_path(self, tmp_path):
        s = detect_project_structure(tmp_path / "does_not_exist")
        assert s.valid is False


class TestBuildScanTargets:

    def test_custom_filter_standard(self):
        s = detect_project_structure(STANDARD_FIXTURE)
        targets = build_scan_targets(s, "custom")
        flat = flatten_targets(targets)
        assert len(flat) > 0
        assert all("contrib" not in p for p in flat)

    def test_contrib_filter_standard(self):
        s = detect_project_structure(STANDARD_FIXTURE)
        targets = build_scan_targets(s, "contrib")
        flat = flatten_targets(targets)
        assert len(flat) > 0
        assert all("contrib" in p for p in flat)

    def test_all_filter_standard(self):
        s = detect_project_structure(STANDARD_FIXTURE)
        targets = build_scan_targets(s, "all")
        flat = flatten_targets(targets)
        has_custom = any("contrib" not in p for p in flat)
        has_contrib = any("contrib" in p for p in flat)
        assert has_custom
        assert has_contrib

    def test_multisite_with_site_selection(self):
        s = detect_project_structure(MULTISITE_FIXTURE)
        targets = build_scan_targets(s, "custom", site="site1")
        flat = flatten_targets(targets)
        assert any("site1" in p for p in flat)
        assert not any("site2" in p for p in flat)

    def test_fallback_to_standard_paths(self):
        """Restricted fixture with standard layout should use discovered paths or fallback."""
        s = detect_project_structure(RESTRICTED_FIXTURE)
        targets = build_scan_targets(s, "custom")
        flat = flatten_targets(targets)
        assert len(flat) > 0


class TestBackwardCompatibility:

    def test_validate_drupal_path_wrapper(self):
        assert validate_drupal_path(RESTRICTED_FIXTURE) is True

    def test_validate_drupal_path_invalid(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert validate_drupal_path(empty) is False

    def test_detect_scan_targets_wrapper(self):
        targets = detect_scan_targets(RESTRICTED_FIXTURE, "custom")
        flat = flatten_targets(targets)
        assert len(flat) > 0

    def test_existing_fixture_end_to_end(self):
        """The restricted fixture should work exactly as before."""
        s = detect_project_structure(RESTRICTED_FIXTURE)
        assert s.valid is True
        targets = build_scan_targets(s, "all")
        flat = flatten_targets(targets)
        assert len(flat) > 0
