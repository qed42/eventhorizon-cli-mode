"""Drupal codebase structure detection and validation.

Supports standard (composer with web/docroot), restricted (no webroot),
and multisite Drupal project layouts via smart .info.yml discovery.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("EventHorizon.DrupalDetection")

# Legacy standard paths — used as fallback when .info.yml discovery finds nothing
STANDARD_PATHS = {
    "custom": ["modules/custom", "themes/custom"],
    "contrib": ["modules/contrib", "themes/contrib"],
}

# Directories to skip during filesystem walk
_EXCLUDE_DIRS = frozenset({
    "vendor", "core", "node_modules", ".git", ".ddev", "tests", "test",
})
_EXCLUDE_PREFIXES = ("core-", ".octane", ".ci")

# Sites to ignore during multisite detection
_SKIP_SITES = frozenset({"default", "all", "simpletest"})


@dataclass
class ProjectStructure:
    """Complete description of a detected Drupal project layout."""

    valid: bool = False
    project_type: str = "restricted"  # "standard" | "restricted" | "multisite"
    project_root: Optional[Path] = None
    webroot: Optional[str] = None  # e.g. "web", "docroot", None
    drupal_root: Optional[Path] = None  # Resolved absolute path scanners receive
    custom_code_paths: list[str] = field(default_factory=list)  # Project-root-relative
    module_roots: list[str] = field(default_factory=list)  # Webroot-relative for scanners
    theme_roots: list[str] = field(default_factory=list)  # Webroot-relative for scanners
    config_path: Optional[str] = None  # Project-root-relative (e.g. "config/sync")
    config_sync_dir: Optional[Path] = None  # Resolved absolute path
    sites: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def detect_project_structure(user_path: Path) -> ProjectStructure:
    """Detect a Drupal project's layout from any path the user provides.

    Handles standard (composer with web/docroot), restricted (no webroot),
    and multisite layouts. The user can point at the project root or directly
    at the webroot — both are handled.

    Returns a ProjectStructure with all resolved paths ready for scanners.
    """
    structure = ProjectStructure()
    user_path = user_path.resolve()

    if not user_path.is_dir():
        structure.errors.append("Path does not exist or is not a directory")
        return structure

    # --- Phase 1: Resolve project_root vs webroot ---
    project_root, webroot = _resolve_roots(user_path)
    structure.project_root = project_root
    structure.webroot = webroot
    structure.drupal_root = (project_root / webroot) if webroot else project_root

    log.debug(
        "Phase 1 — project_root=%s, webroot=%s, drupal_root=%s",
        project_root, webroot, structure.drupal_root,
    )

    # --- Phase 2: Smart .info.yml discovery ---
    module_roots, theme_roots = _discover_info_yml_roots(project_root)
    structure.custom_code_paths = sorted(module_roots | theme_roots)

    log.debug(
        "Phase 2 — module_roots=%s, theme_roots=%s",
        sorted(module_roots), sorted(theme_roots),
    )

    # --- Phase 3: Config detection ---
    config_path = _detect_config_path(project_root, webroot)
    structure.config_path = config_path
    if config_path:
        structure.config_sync_dir = (project_root / config_path).resolve()

    log.debug("Phase 3 — config_path=%s", config_path)

    # --- Phase 4: Multisite detection ---
    sites = _detect_multisite(module_roots | theme_roots, webroot)
    structure.sites = sorted(sites)

    log.debug("Phase 4 — sites=%s", structure.sites)

    # --- Phase 5: Classify ---
    has_custom_code = bool(module_roots) or bool(theme_roots)
    has_config = config_path is not None
    is_drupal = has_custom_code or has_config

    if not is_drupal:
        # Fallback: check for standard Drupal markers
        drupal_root = structure.drupal_root
        markers = [drupal_root / "modules", drupal_root / "core", drupal_root / "themes", drupal_root / "sites"]
        is_drupal = any(m.is_dir() for m in markers)

    if is_drupal:
        structure.valid = True
        if webroot and sites:
            structure.project_type = "multisite"
        elif webroot:
            structure.project_type = "standard"
        else:
            structure.project_type = "restricted"
    else:
        structure.errors.append(
            "No Drupal project detected. Expected custom modules/themes, "
            "config directory, or standard Drupal markers (modules/, core/, themes/, sites/)."
        )

    log.debug("Phase 5 — valid=%s, project_type=%s", structure.valid, structure.project_type)

    # --- Phase 6: Build scanner-ready paths ---
    webroot_prefix = (webroot + "/") if webroot else ""
    structure.module_roots = _to_scanner_paths(sorted(module_roots), webroot_prefix, webroot)
    structure.theme_roots = _to_scanner_paths(sorted(theme_roots), webroot_prefix, webroot)

    log.debug(
        "Phase 6 — module_roots=%s, theme_roots=%s",
        structure.module_roots, structure.theme_roots,
    )

    return structure


def build_scan_targets(
    structure: ProjectStructure,
    filter_name: str,
    site: Optional[str] = None,
) -> dict[str, list[str]]:
    """Build scanner-ready target dict from a detected project structure.

    Returns dict with 'custom' and/or 'contrib' keys mapping to
    lists of webroot-relative path strings that exist on disk.
    """
    targets: dict[str, list[str]] = {}

    if site:
        # Multisite: scan site-specific paths
        custom_paths = [f"sites/{site}/modules", f"sites/{site}/themes"]
        existing = [p for p in custom_paths if (structure.drupal_root / p).is_dir()]
        if existing and filter_name in ("custom", "all"):
            targets["custom"] = existing
        return targets

    # Use discovered roots
    all_module = structure.module_roots
    all_theme = structure.theme_roots

    if all_module or all_theme:
        if filter_name in ("custom", "all"):
            custom = [p for p in all_module + all_theme if "contrib" not in p]
            existing = [p for p in custom if (structure.drupal_root / p).resolve().is_dir()]
            if existing:
                targets["custom"] = existing

        if filter_name in ("contrib", "all"):
            contrib = [p for p in all_module + all_theme if "contrib" in p]
            existing = [p for p in contrib if (structure.drupal_root / p).resolve().is_dir()]
            if existing:
                targets["contrib"] = existing
    else:
        # Fallback to legacy standard paths
        log.debug("No discovered roots, falling back to STANDARD_PATHS")
        groups_to_check = []
        if filter_name in ("custom", "all"):
            groups_to_check.append("custom")
        if filter_name in ("contrib", "all"):
            groups_to_check.append("contrib")

        for group in groups_to_check:
            existing = [
                p for p in STANDARD_PATHS[group]
                if (structure.drupal_root / p).is_dir()
            ]
            if existing:
                targets[group] = existing

    return targets


def flatten_targets(targets: dict[str, list[str]]) -> list[str]:
    """Flatten a targets dict into a single list of path strings."""
    result: list[str] = []
    for paths in targets.values():
        result.extend(paths)
    return result


# --- Deprecated wrappers (backward compatibility) ---


def validate_drupal_path(path: Path) -> bool:
    """Check if the given path looks like a Drupal codebase root.

    .. deprecated:: Use detect_project_structure() instead.
    """
    structure = detect_project_structure(path)
    return structure.valid


def detect_scan_targets(drupal_root: Path, filter_name: str) -> dict[str, list[str]]:
    """Auto-detect scan target directories based on filter.

    .. deprecated:: Use detect_project_structure() + build_scan_targets() instead.
    """
    structure = detect_project_structure(drupal_root)
    return build_scan_targets(structure, filter_name)


# --- Internal helpers ---


def _resolve_roots(user_path: Path) -> tuple:
    """Phase 1: Determine project_root and webroot from the user-provided path."""
    # Check if user_path contains a webroot subdirectory
    for candidate in ("web", "docroot"):
        if (user_path / candidate).is_dir():
            return user_path, candidate

    # Check nested: {subdir}/web or {subdir}/docroot (one level deep)
    for entry in user_path.iterdir():
        if not entry.is_dir() or entry.name in _EXCLUDE_DIRS:
            continue
        for candidate in ("web", "docroot"):
            if (entry / candidate).is_dir():
                return user_path, f"{entry.name}/{candidate}"

    # Check if user pointed directly at the webroot
    if user_path.name in ("web", "docroot"):
        parent = user_path.parent
        # Verify parent looks like a project root (has composer.json or similar)
        project_indicators = [
            parent / "composer.json",
            parent / "config",
            parent / ".ddev",
            parent / ".lando.yml",
        ]
        if any(p.exists() for p in project_indicators):
            return parent, user_path.name

    # No webroot detected — restricted/legacy layout
    return user_path, None


def _discover_info_yml_roots(project_root: Path) -> tuple:
    """Phase 2: Walk filesystem to discover .info.yml files and derive scan roots."""
    module_roots: set = set()
    theme_roots: set = set()

    info_pattern = re.compile(r"^(.+)/([^/]+)/[^/]+\.info\.yml$")

    for dirpath, dirnames, filenames in os.walk(project_root):
        # Prune excluded directories in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in _EXCLUDE_DIRS and not any(d.startswith(px) for px in _EXCLUDE_PREFIXES)
        ]

        for filename in filenames:
            if not filename.endswith(".info.yml"):
                continue

            # Skip config export files (multiple dots: core.base_field_override.*.info.yml)
            if filename.count(".") > 2:
                continue

            full_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(full_path, project_root)
            # Normalize to forward slashes
            rel_path = rel_path.replace(os.sep, "/")

            m = info_pattern.match(rel_path)
            if not m:
                continue

            scan_root = m.group(1)  # grandparent of .info.yml

            if "theme" in scan_root.lower():
                theme_roots.add(scan_root)
            else:
                module_roots.add(scan_root)

    return module_roots, theme_roots


def _detect_config_path(project_root: Path, webroot: Optional[str]) -> Optional[str]:
    """Phase 3: Detect the config sync directory location."""
    # Priority 1: config/sync at project root
    if (project_root / "config" / "sync").is_dir():
        return "config/sync"

    # Priority 2: config/default at project root
    if (project_root / "config" / "default").is_dir():
        return "config/default"

    # Priority 3: any config/{subdir} at project root
    config_dir = project_root / "config"
    if config_dir.is_dir():
        for entry in sorted(config_dir.iterdir()):
            # Must be a non-hidden directory that actually contains .yml files
            if entry.is_dir() and not entry.name.startswith(".") and any(entry.glob("*.yml")):
                return f"config/{entry.name}"

    # Priority 4: sites/default/config/ inside webroot
    if webroot:
        sites_config = project_root / webroot / "sites" / "default" / "config"
        if sites_config.is_dir():
            for entry in sorted(sites_config.iterdir()):
                if entry.is_dir():
                    return f"{webroot}/sites/default/config/{entry.name}"

    return None


def _detect_multisite(all_roots: set, webroot: Optional[str]) -> set:
    """Phase 4: Detect multisite names from discovered scan roots."""
    sites: set = set()
    webroot_prefix = re.escape((webroot + "/") if webroot else "")
    site_pattern = re.compile(rf"^{webroot_prefix}sites/([^/]+)/")

    for root in all_roots:
        m = site_pattern.match(root)
        if m and m.group(1) not in _SKIP_SITES:
            sites.add(m.group(1))

    return sites


def _to_scanner_paths(
    code_paths: list[str],
    webroot_prefix: str,
    webroot: Optional[str],
) -> list[str]:
    """Phase 6: Convert project-root-relative paths to webroot-relative scanner paths."""
    result: list[str] = []
    for code_path in code_paths:
        if webroot_prefix and code_path.startswith(webroot_prefix):
            # Inside webroot: strip prefix
            result.append(code_path[len(webroot_prefix):])
        elif webroot:
            # Outside webroot: use ../ relative path
            result.append(f"../{code_path}")
        else:
            # No webroot: already relative to project root = drupal_root
            result.append(code_path)
    return result
