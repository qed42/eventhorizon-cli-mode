"""Static analysis scanner using YAML-defined regex rules.

Regex-based static analysis engine using YAML rule definitions.
"""

import functools
import logging
import re
from collections import defaultdict
from importlib.resources import files as pkg_files
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from eventhorizon.scanner.types import Finding

log = logging.getLogger("EventHorizon.StaticAnalyzer")

MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB


@functools.lru_cache(maxsize=1)
def _load_rules() -> List[Dict[str, Any]]:
    """Load custom rules from the bundled YAML file."""
    rules_path = pkg_files("eventhorizon.scanner.rules").joinpath("custom_rules.yml")
    try:
        with open(str(rules_path), "r") as f:
            data = yaml.safe_load(f)
            return (data or {}).get("custom_checks", [])
    except (OSError, yaml.YAMLError) as e:
        log.error(f"Failed to load custom rules: {e}", exc_info=True)
        return []


def _compile_rules(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pre-compile regex patterns and index rules by file extension."""
    compiled = []
    for rule in rules:
        try:
            is_multiline = rule.get("multiline", False)
            flags = re.DOTALL if is_multiline else 0
            compiled.append({
                **rule,
                "_compiled": re.compile(rule["pattern"], flags),
                "_multiline": is_multiline,
            })
        except re.error as e:
            log.error(f"Invalid regex in rule '{rule.get('id', 'N/A')}': {e}")
    return compiled


def _index_rules_by_ext(compiled_rules: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group compiled rules by file extension for file-first scanning.

    Handles compound extensions like '.routing.yml' and '.libraries.yml'
    by indexing under the simple suffix (e.g. '.yml') as well.
    """
    by_ext: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for rule in compiled_rules:
        for ext in rule.get("file_types", []):
            by_ext[ext].append(rule)
    return dict(by_ext)


def _get_matching_exts(file_path: Path, scannable_exts: set) -> List[str]:
    """Return all matching extension keys for a file, handling compound extensions."""
    matched = []
    name = file_path.name
    # Check compound extensions (e.g. '.routing.yml', '.libraries.yml')
    for ext in scannable_exts:
        if ext.count(".") > 1 and name.endswith(ext):
            matched.append(ext)
    # Also check simple suffix
    if file_path.suffix in scannable_exts and file_path.suffix not in matched:
        matched.append(file_path.suffix)
    return matched


class StaticAnalyzer:
    """Runs custom, file-based static analysis checks against a Drupal codebase."""

    def __init__(self, drupal_root: str, scan_targets: List[str], filter_name: str) -> None:
        self.drupal_root = Path(drupal_root).resolve()
        self.filter_name = filter_name
        self.scan_targets = [
            target for target in scan_targets
            if (self.drupal_root / target).exists()
        ]
        if not self.scan_targets:
            log.warning(f"No valid scan targets found for filter '{filter_name}'.")

        rules = _load_rules()
        self._compiled_rules = _compile_rules(rules)
        self._rules_by_ext = _index_rules_by_ext(self._compiled_rules)

    def run_custom_checks(self, progress_callback: Optional[Callable[[str], None]] = None) -> List[Finding]:
        """Scan files against YAML-defined regex rules.

        Args:
            progress_callback: Optional callable(file_path: str) called per file scanned.
        """
        if not self._compiled_rules or not self.scan_targets:
            return []

        findings: List[Finding] = []
        scannable_exts = set(self._rules_by_ext.keys())

        for target_dir_str in self.scan_targets:
            target_dir = self.drupal_root / target_dir_str
            if not target_dir.is_dir():
                continue

            for file_path in target_dir.rglob("*"):
                if file_path.is_symlink():
                    continue
                matched_exts = _get_matching_exts(file_path, scannable_exts)
                if not matched_exts:
                    continue
                try:
                    if file_path.stat().st_size > MAX_FILE_SIZE:
                        log.warning(f"Skipping oversized file ({file_path.stat().st_size} bytes): {file_path}")
                        continue
                except OSError:
                    continue

                if progress_callback:
                    progress_callback(str(file_path))

                # Collect rules from all matching extensions, dedup by id
                seen_rule_ids: set = set()
                applicable_rules: List[Dict[str, Any]] = []
                for ext in matched_exts:
                    for rule in self._rules_by_ext[ext]:
                        rid = id(rule)
                        if rid not in seen_rule_ids:
                            seen_rule_ids.add(rid)
                            applicable_rules.append(rule)
                try:
                    with file_path.open("r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except (OSError, UnicodeDecodeError) as file_e:
                    log.warning(f"Could not read file {file_path}: {file_e}")
                    continue

                relative_path = file_path.relative_to(self.drupal_root).as_posix()
                lines: Optional[List[str]] = None

                for rule in applicable_rules:
                    pattern = rule["_compiled"]
                    if rule["_multiline"]:
                        for match in pattern.finditer(content):
                            line_num = content[: match.start()].count("\n") + 1
                            findings.append({
                                "tool": "custom",
                                "file": relative_path,
                                "line": line_num,
                                "severity": rule.get("severity", "warning"),
                                "message": rule.get("message"),
                                "rule": rule.get("id", "custom-rule"),
                                "category": rule.get("category", "other"),
                            })
                    else:
                        if lines is None:
                            lines = content.splitlines()
                        for line_num, line_content in enumerate(lines, 1):
                            if pattern.search(line_content):
                                findings.append({
                                    "tool": "custom",
                                    "file": relative_path,
                                    "line": line_num,
                                    "severity": rule.get("severity", "warning"),
                                    "message": rule.get("message"),
                                    "rule": rule.get("id", "custom-rule"),
                                    "category": rule.get("category", "other"),
                                })

        log.info(f"Custom scan complete. Found {len(findings)} issues.")
        return findings

    def run_all_scans(self, progress_callback: Optional[Callable[[str], None]] = None) -> List[Finding]:
        """Run all scans and return a flat list of findings."""
        log.info(f"Starting static analysis on targets: {self.scan_targets}")
        findings = self.run_custom_checks(progress_callback=progress_callback)
        findings.sort(key=lambda x: (x["file"], x.get("line", 0)))
        log.info(f"All scans finished. Total issues: {len(findings)}")
        return findings
