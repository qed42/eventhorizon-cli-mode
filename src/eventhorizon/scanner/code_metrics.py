"""Code metrics analyzer — LOC, cyclomatic complexity, maintainability index.

Code complexity and maintainability metrics analyzer.
Extracts function bodies directly from PHP files.
"""

import logging
import math
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from eventhorizon.scanner.types import Finding

log = logging.getLogger("EventHorizon.CodeMetrics")

# Thresholds for generating findings
CCN_THRESHOLD = 10
MI_THRESHOLD = 65
ANTIPATTERN_THRESHOLD = 5

# Anti-pattern regexes
ANTIPATTERN_PATTERNS = [
    (r"\\Drupal::", "service_locator"),
    (r"\$\w+\[.+\]\[.+\]\[.+\]", "deep_array_access"),
    (r"['\"]#(markup|prefix|suffix|children)['\"]", "magic_render_key"),
    (r"\bglobal\s+\$", "global_variable"),
    (r"@(trigger_error|suppress)", "error_suppression"),
]

# CCN branch keywords
CCN_KEYWORDS = re.compile(
    r"\b(?:if|elseif|else\s*if|for|foreach|while|case|catch|and|or)\b"
    r"|&&|\|\||\?\?|\?(?!=)"
)


def calculate_loc(source: str) -> int:
    """Calculate source lines of code, excluding blanks and comments."""
    sloc = 0
    in_block_comment = False
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            continue
        if stripped.startswith("/*"):
            if "*/" not in stripped:
                in_block_comment = True
            continue
        if stripped.startswith("//") or stripped.startswith("#"):
            continue
        sloc += 1
    return sloc


def calculate_ccn(source: str) -> int:
    """Calculate cyclomatic complexity number.

    Starts at 1 (for the function itself) and adds 1 for each branch.
    """
    cleaned = _strip_strings_and_comments(source)
    return 1 + len(CCN_KEYWORDS.findall(cleaned))


def calculate_mi(loc: int, ccn: int) -> float:
    """Calculate Maintainability Index (0–100 scale).

    Based on the SEI formula:
        MI = 171 - 5.2*ln(HV) - 0.23*CC - 16.2*ln(LOC)
    Normalised to 0-100. Uses LOC as a proxy for Halstead Volume.
    """
    if loc == 0:
        return 100.0
    log_loc = math.log(max(loc, 1))
    raw = 171.0 - 5.2 * log_loc - 0.23 * ccn - 16.2 * log_loc
    return max(0.0, min(100.0, raw * 100.0 / 171.0))


def count_antipatterns(source: str) -> Dict[str, int]:
    """Count occurrences of Drupal anti-patterns in source code."""
    counts: Dict[str, int] = {}
    for pattern_str, name in ANTIPATTERN_PATTERNS:
        matches = re.findall(pattern_str, source)
        if matches:
            counts[name] = len(matches)
    return counts


def _strip_strings_and_comments(source: str) -> str:
    """Remove string literals and comments to avoid false positives in CCN."""
    # Remove block comments
    result = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    # Remove line comments
    result = re.sub(r"//[^\n]*", "", result)
    result = re.sub(r"#[^\n]*", "", result)
    # Remove string literals
    result = re.sub(r"'(?:[^'\\]|\\.)*'", "''", result)
    result = re.sub(r'"(?:[^"\\]|\\.)*"', '""', result)
    return result


def _extract_function_bodies(source: str) -> List[Tuple[str, str, int]]:
    """Extract PHP function bodies from source code.

    Returns list of (function_name, function_body, line_number) tuples.
    """
    functions: List[Tuple[str, str, int]] = []
    pattern = re.compile(
        r"(?:public|protected|private|static|\s)*\s*function\s+(\w+)\s*\([^)]*\)\s*(?::\s*\S+\s*)?\{",
    )

    lines = source.split("\n")
    full_text = source

    for match in pattern.finditer(full_text):
        func_name = match.group(1)
        brace_start = match.end() - 1  # position of opening {
        line_number = full_text[:match.start()].count("\n") + 1

        # Find matching closing brace
        depth = 0
        pos = brace_start
        while pos < len(full_text):
            ch = full_text[pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    body = full_text[brace_start + 1 : pos]
                    functions.append((func_name, body, line_number))
                    break
            pos += 1

    return functions


def run_code_metrics(
    drupal_root: Path,
    scan_targets: List[str],
    progress_callback: Optional[Callable[[str], None]] = None,
) -> List[Finding]:
    """Run code metrics analysis on PHP files in scan targets.

    Args:
        drupal_root: Path to the Drupal root directory.
        scan_targets: List of relative paths to scan (e.g. ["modules/custom"]).
        progress_callback: Optional callback invoked with each scanned file path.

    Returns:
        List of finding dicts with tool="code_metrics".
    """
    findings: List[Dict[str, Any]] = []
    root = Path(drupal_root)

    for target in scan_targets:
        target_path = root / target
        if not target_path.is_dir():
            continue

        for php_file in target_path.rglob("*.php"):
            _scan_php_file(php_file, root, findings)
            if progress_callback:
                progress_callback(str(php_file.relative_to(root)))

        for module_file in target_path.rglob("*.module"):
            _scan_php_file(module_file, root, findings)
            if progress_callback:
                progress_callback(str(module_file.relative_to(root)))

        for inc_file in target_path.rglob("*.inc"):
            _scan_php_file(inc_file, root, findings)
            if progress_callback:
                progress_callback(str(inc_file.relative_to(root)))

        for theme_file in target_path.rglob("*.theme"):
            _scan_php_file(theme_file, root, findings)
            if progress_callback:
                progress_callback(str(theme_file.relative_to(root)))

    return findings


def _scan_php_file(
    file_path: Path,
    root: Path,
    findings: List[Dict[str, Any]],
) -> None:
    """Scan a single PHP file for code metrics issues."""
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return

    relative_path = str(file_path.relative_to(root))
    functions = _extract_function_bodies(source)

    for func_name, body, line_number in functions:
        loc = calculate_loc(body)
        ccn = calculate_ccn(body)
        mi = calculate_mi(loc, ccn)
        antipatterns = count_antipatterns(body)
        total_antipatterns = sum(antipatterns.values())

        if ccn > CCN_THRESHOLD:
            findings.append({
                "tool": "code_metrics",
                "file": relative_path,
                "line": line_number,
                "severity": "warning",
                "category": "performance",
                "rule": "high_cyclomatic_complexity",
                "message": (
                    f"Function '{func_name}' has cyclomatic complexity of {ccn} "
                    f"(threshold: {CCN_THRESHOLD}). Consider breaking it into smaller functions."
                ),
            })

        if mi < MI_THRESHOLD:
            findings.append({
                "tool": "code_metrics",
                "file": relative_path,
                "line": line_number,
                "severity": "warning",
                "category": "performance",
                "rule": "low_maintainability_index",
                "message": (
                    f"Function '{func_name}' has a maintainability index of {mi:.1f} "
                    f"(threshold: {MI_THRESHOLD}). Consider refactoring for readability."
                ),
            })

        if total_antipatterns > ANTIPATTERN_THRESHOLD:
            pattern_summary = ", ".join(f"{k}:{v}" for k, v in antipatterns.items())
            findings.append({
                "tool": "code_metrics",
                "file": relative_path,
                "line": line_number,
                "severity": "info",
                "category": "performance",
                "rule": "excessive_antipatterns",
                "message": (
                    f"Function '{func_name}' has {total_antipatterns} anti-pattern occurrences "
                    f"(threshold: {ANTIPATTERN_THRESHOLD}). Patterns: {pattern_summary}"
                ),
            })
