"""Drupal configuration validator — detects config quality issues.

Drupal config validation: field references, orphaned paragraphs, circular dependencies.
Checks for orphaned paragraphs, broken references, circular dependencies,
unused fields, overly complex entities, and missing descriptions.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from eventhorizon.scanner.config_analyzer import DrupalConfigAnalyzer
from eventhorizon.scanner.types import Finding

log = logging.getLogger("EventHorizon.ConfigValidator")

# Thresholds
MAX_FIELDS_PER_ENTITY = 30


@dataclass
class ValidationIssue:
    """Represents a single config validation finding."""

    issue_type: str
    severity: str
    entity_type: str
    entity_name: str
    message: str
    details: str = ""
    recommendation: str = ""


class DrupalConfigValidator:
    """Validates Drupal config for structural issues."""

    def __init__(self, config_data: Dict[str, Any]) -> None:
        self.data = config_data
        self.issues: List[ValidationIssue] = []

    def validate_all(self) -> List[ValidationIssue]:
        """Run all validation checks."""
        self.issues = []
        self.check_orphaned_paragraphs()
        self.check_broken_field_references()
        self.check_circular_paragraph_dependencies()
        self.check_duplicate_paragraphs()
        self.check_overly_complex_entities()
        self.check_unused_fields()
        self.check_missing_field_descriptions()
        return self.issues

    def check_orphaned_paragraphs(self) -> None:
        """Find paragraph types not referenced by any non-paragraph entity field.

        A paragraph type referenced only by other paragraphs (but never by a
        content type, block type, etc.) is effectively orphaned — it can never
        be reached by editors.
        """
        paragraphs = self.data.get("paragraphs", [])
        if not paragraphs:
            return

        fields = self.data.get("fields", {})
        instances = fields.get("instances", [])

        # Collect paragraph types referenced from non-paragraph entity fields
        referenced_paragraphs: Set[str] = set()
        for inst in instances:
            # Only count references from non-paragraph entities
            if inst.get("entity_type") == "paragraph":
                continue
            deps = inst.get("dependencies", {})
            config_deps = deps.get("config", [])
            for dep in config_deps:
                if dep.startswith("paragraphs.paragraphs_type."):
                    referenced_paragraphs.add(dep.replace("paragraphs.paragraphs_type.", ""))

        for para in paragraphs:
            if para["id"] not in referenced_paragraphs:
                self.issues.append(ValidationIssue(
                    issue_type="orphaned_entity",
                    severity="warning",
                    entity_type="paragraph",
                    entity_name=para["id"],
                    message=f"Paragraph type '{para['id']}' is not referenced by any content entity field.",
                    recommendation="Remove the paragraph type or add a field that references it.",
                ))

    def check_broken_field_references(self) -> None:
        """Find field instances that reference non-existent bundles."""
        content_types = {ct["id"] for ct in self.data.get("content_types", [])}
        paragraphs = {p["id"] for p in self.data.get("paragraphs", [])}
        taxonomies = {t["id"] for t in self.data.get("taxonomies", [])}
        block_types = {b["id"] for b in self.data.get("block_types", [])}

        known_bundles = {
            "node": content_types,
            "paragraph": paragraphs,
            "taxonomy_term": taxonomies,
            "block_content": block_types,
        }

        fields = self.data.get("fields", {})
        for inst in fields.get("instances", []):
            entity_type = inst.get("entity_type", "")
            bundle = inst.get("bundle", "")
            bundles_for_type = known_bundles.get(entity_type, set())

            if bundles_for_type and bundle not in bundles_for_type:
                self.issues.append(ValidationIssue(
                    issue_type="broken_reference",
                    severity="error",
                    entity_type=entity_type,
                    entity_name=f"{entity_type}.{bundle}.{inst.get('field_name', '')}",
                    message=(
                        f"Field '{inst.get('field_name', '')}' targets bundle '{bundle}' "
                        f"of type '{entity_type}', but that bundle does not exist."
                    ),
                    recommendation=f"Create the '{bundle}' bundle or remove this field config.",
                ))

    def check_circular_paragraph_dependencies(self) -> None:
        """Detect circular references between paragraph types."""
        fields = self.data.get("fields", {})
        instances = fields.get("instances", [])

        # Build adjacency map: paragraph -> set of paragraph types it references
        graph: Dict[str, Set[str]] = {}
        for inst in instances:
            if inst.get("entity_type") != "paragraph":
                continue
            source = inst.get("bundle", "")
            deps = inst.get("dependencies", {})
            config_deps = deps.get("config", [])
            for dep in config_deps:
                if dep.startswith("paragraphs.paragraphs_type."):
                    target = dep.replace("paragraphs.paragraphs_type.", "")
                    graph.setdefault(source, set()).add(target)

        # DFS cycle detection
        visited: Set[str] = set()
        path: Set[str] = set()
        cycles_found: Set[frozenset] = set()

        def _dfs(node: str) -> None:
            if node in path:
                cycle = frozenset(path)
                if cycle not in cycles_found:
                    cycles_found.add(cycle)
                    self.issues.append(ValidationIssue(
                        issue_type="circular_dependency",
                        severity="error",
                        entity_type="paragraph",
                        entity_name=node,
                        message=f"Circular paragraph dependency detected involving: {', '.join(sorted(path))}",
                        recommendation="Break the cycle by removing one of the paragraph references.",
                    ))
                return
            if node in visited:
                return
            visited.add(node)
            path.add(node)
            for neighbour in graph.get(node, set()):
                _dfs(neighbour)
            path.discard(node)

        for node in graph:
            _dfs(node)

    def check_duplicate_paragraphs(self) -> None:
        """Flag paragraph types with very similar names (potential duplicates)."""
        paragraphs = self.data.get("paragraphs", [])
        if len(paragraphs) < 2:
            return

        seen: Dict[str, str] = {}
        for para in paragraphs:
            # Normalise: strip common prefixes/suffixes, lowercase
            normalized = para["id"].lower().replace("_", "").replace("-", "")
            if normalized in seen:
                self.issues.append(ValidationIssue(
                    issue_type="consolidation_opportunity",
                    severity="info",
                    entity_type="paragraph",
                    entity_name=para["id"],
                    message=(
                        f"Paragraph types '{para['id']}' and '{seen[normalized]}' "
                        f"have very similar names and may be duplicates."
                    ),
                    recommendation="Consider consolidating into a single paragraph type.",
                ))
            else:
                seen[normalized] = para["id"]

    def check_overly_complex_entities(self) -> None:
        """Flag content types with more than MAX_FIELDS_PER_ENTITY fields."""
        fields = self.data.get("fields", {})
        instances = fields.get("instances", [])

        # Count fields per bundle
        bundle_counts: Dict[str, int] = {}
        for inst in instances:
            key = f"{inst.get('entity_type', '')}.{inst.get('bundle', '')}"
            bundle_counts[key] = bundle_counts.get(key, 0) + 1

        for bundle_key, count in bundle_counts.items():
            if count > MAX_FIELDS_PER_ENTITY:
                self.issues.append(ValidationIssue(
                    issue_type="overly_complex",
                    severity="warning",
                    entity_type=bundle_key.split(".")[0],
                    entity_name=bundle_key,
                    message=(
                        f"Entity '{bundle_key}' has {count} fields "
                        f"(threshold: {MAX_FIELDS_PER_ENTITY}). Consider splitting into paragraphs or sub-entities."
                    ),
                    recommendation="Break up the entity into smaller components using paragraphs or entity references.",
                ))

    def check_unused_fields(self) -> None:
        """Find field storages with no field instances."""
        fields = self.data.get("fields", {})
        storages = fields.get("storages", [])
        instances = fields.get("instances", [])

        # Collect all field names that have instances
        used_fields: Set[str] = set()
        for inst in instances:
            used_fields.add(f"{inst.get('entity_type', '')}.{inst.get('field_name', '')}")

        for storage in storages:
            storage_key = f"{storage.get('entity_type', '')}.{storage.get('field_name', '')}"
            if storage_key not in used_fields:
                self.issues.append(ValidationIssue(
                    issue_type="unused_field",
                    severity="warning",
                    entity_type=storage.get("entity_type", ""),
                    entity_name=storage.get("field_name", ""),
                    message=(
                        f"Field storage '{storage.get('field_name', '')}' "
                        f"(type: {storage.get('entity_type', '')}) has no field instances."
                    ),
                    recommendation="Remove the unused field storage or create an instance for it.",
                ))

    def check_missing_field_descriptions(self) -> None:
        """Flag field instances without help text/description."""
        fields = self.data.get("fields", {})
        for inst in fields.get("instances", []):
            if not inst.get("description"):
                self.issues.append(ValidationIssue(
                    issue_type="missing_description",
                    severity="info",
                    entity_type=inst.get("entity_type", ""),
                    entity_name=f"{inst.get('bundle', '')}.{inst.get('field_name', '')}",
                    message=(
                        f"Field '{inst.get('field_name', '')}' on "
                        f"'{inst.get('entity_type', '')}.{inst.get('bundle', '')}' has no help text."
                    ),
                    recommendation="Add a description to help content editors understand this field.",
                ))

    def get_summary_stats(self) -> Dict[str, Any]:
        """Return counts grouped by severity and issue type."""
        by_severity: Dict[str, int] = {}
        by_type: Dict[str, int] = {}

        for issue in self.issues:
            by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1
            by_type[issue.issue_type] = by_type.get(issue.issue_type, 0) + 1

        return {
            "total": len(self.issues),
            "by_severity": by_severity,
            "by_type": by_type,
        }


# Issue type -> finding category mapping
_SECURITY_ISSUE_TYPES = {"broken_reference", "circular_dependency", "orphaned_entity"}
_PERFORMANCE_ISSUE_TYPES = {"overly_complex", "unused_field", "missing_description", "consolidation_opportunity"}


def run_config_validation(
    drupal_root: Path,
    config_sync_dir: Path,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> List[Finding]:
    """Run config analysis + validation, returning standard finding dicts.

    Args:
        drupal_root: Path to Drupal root (for relative path display).
        config_sync_dir: Path to the config/sync directory.
        progress_callback: Optional callback invoked per config file.

    Returns:
        List of finding dicts compatible with the rest of the CLI pipeline.
    """
    if not config_sync_dir.is_dir():
        return []

    if progress_callback:
        try:
            rel = str(config_sync_dir.relative_to(drupal_root))
        except ValueError:
            rel = str(config_sync_dir.name)
        progress_callback(rel)

    analyzer = DrupalConfigAnalyzer(str(config_sync_dir))
    config_data = analyzer.analyze_all_configs()
    validator = DrupalConfigValidator(config_data)
    issues = validator.validate_all()

    findings: List[Dict[str, Any]] = []
    for issue in issues:
        if issue.issue_type in _SECURITY_ISSUE_TYPES:
            category = "security"
        elif issue.issue_type in _PERFORMANCE_ISSUE_TYPES:
            category = "performance"
        else:
            category = "performance"

        finding: Dict[str, Any] = {
            "tool": "config_validator",
            "file": f"config/sync ({issue.entity_type})",
            "line": 0,
            "severity": _map_validator_severity(issue.severity),
            "category": category,
            "rule": issue.issue_type,
            "message": issue.message,
        }
        if issue.recommendation:
            finding["recommendation"] = issue.recommendation

        findings.append(finding)

    return findings


def _map_validator_severity(severity: str) -> str:
    """Map validator severity to standard severity values."""
    mapping = {
        "critical": "error",
        "error": "error",
        "warning": "warning",
        "info": "info",
    }
    return mapping.get(severity, severity)
