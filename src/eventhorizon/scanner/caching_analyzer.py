"""Drupal caching issue analyzer with context-aware detection.

Context-aware Drupal caching issue analyzer.
All findings are normalized to the standard finding dict format.
"""

import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from eventhorizon.scanner.types import Finding

log = logging.getLogger("EventHorizon.CachingAnalyzer")

MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB


class DrupalContextDetector:
    """Detects Drupal-specific code contexts for accurate analysis."""

    def identify_context(self, content: str, file_path: str) -> Dict:
        context = {
            "type": "unknown",
            "hooks": [],
            "has_expensive_operations": False,
            "file_path": file_path,
        }

        hook_pattern = r"function\s+(\w+)_(menu|init|preprocess|block_view|page_build|page_attachments)"
        for match in re.finditer(hook_pattern, content):
            hook_name = f"{match.group(1)}_{match.group(2)}"
            is_expensive = match.group(2) in [
                "menu", "init", "preprocess", "block_view", "page_build", "page_attachments",
            ]
            context["hooks"].append({
                "name": hook_name,
                "type": match.group(2),
                "line": content[: match.start()].count("\n") + 1,
                "is_expensive": is_expensive,
            })
            if is_expensive:
                context["has_expensive_operations"] = True

        if re.search(r"class\s+(\w+)Controller.*?extends.*?ControllerBase", content, re.DOTALL):
            context["type"] = "controller"
            context["has_expensive_operations"] = True

        if "@Block" in content:
            context["type"] = "block_plugin"
            context["has_expensive_operations"] = True

        if re.search(r"class\s+(\w+)\s+extends.*?(ContentEntityBase|ConfigEntityBase)", content):
            context["type"] = "entity"

        return context


class SmartCachingAnalyzer:
    """Smart analyzer that detects real caching problems with context awareness."""

    def __init__(self) -> None:
        self.context_detector = DrupalContextDetector()
        self.critical_patterns = [
            self._detect_missing_render_cache,
            self._detect_improper_user_context,
            self._detect_user_context_overuse,
            self._detect_early_rendering,
            self._detect_uncached_database_queries,
            self._detect_missing_cache_tags,
            self._detect_missed_drupal_static_opportunity,
            self._detect_cache_bin_opportunity,
            self._detect_missing_specific_contexts,
            self._detect_missing_entity_tags,
            self._detect_bigpipe_opportunity,
            # Deep caching detectors
            self._detect_cacheable_metadata_bubbling,
            self._detect_dependency_chain_break,
            self._detect_stale_cache_tag_pattern,
            self._detect_render_rebuilt_every_request,
            self._detect_block_cacheability_leak,
        ]

    def analyze_file(self, file_path: Path) -> List[Dict]:
        """Analyze a single file for caching issues."""
        try:
            with file_path.open("r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except (UnicodeDecodeError, IOError) as e:
            return [{
                "type": "file_error", "severity": "warning", "line": 1,
                "message": f"Error reading file: {e}", "file_path": str(file_path),
            }]

        context = self.context_detector.identify_context(content, str(file_path))
        issues: List[Dict] = []

        for detector_func in self.critical_patterns:
            try:
                issues.extend(detector_func(content, str(file_path), context))
            except Exception as e:
                log.error(f"Error in {detector_func.__name__} for {file_path}: {e}", exc_info=True)

        return self._prioritize_issues(issues)

    # --- Detectors ---

    def _detect_missing_render_cache(self, content: str, file_path: str, context: Dict) -> List[Dict]:
        issues = []
        render_patterns = [
            r"return\s+\[\s*['\"]#(theme|markup|template|type|prefix|suffix)['\"].*?\];",
            r"\$build\s*=\s*\[\s*['\"]#(theme|markup|template|type|prefix|suffix)['\"].*?\];",
            r"\$\w+\s*\[\s*['\"][\w_]+['\"]?\s*\]\s*=\s*\[\s*['\"]#(theme|markup|template|type|prefix|suffix)['\"].*?\];",
        ]
        form_exclusion = [r"\$form\s*\[", r"FormStateInterface", r"function\s+\w+_(form|validate|submit)"]
        for pattern in render_patterns:
            for match in re.finditer(pattern, content, re.DOTALL):
                array_content = match.group(0)
                if self._is_commented_code(content, match.start()):
                    continue
                if any(re.search(excl, array_content) for excl in form_exclusion):
                    continue
                if not re.search(r"#cache\s*=>\s*\[", array_content):
                    line_num = content[: match.start()].count("\n") + 1
                    func_ctx = self._get_function_context(content, match.start())
                    is_expensive = self._is_expensive_render_context(func_ctx, context)
                    issues.append(self._make_finding(
                        "missing_cache_metadata",
                        "error" if is_expensive else "warning",
                        line_num, file_path,
                        "Render array is missing #cache metadata.",
                    ))
        return issues

    def _detect_improper_user_context(self, content: str, file_path: str, context: Dict) -> List[Dict]:
        issues = []
        user_patterns = [r"\$user->", r"current_user\(\)", r"user_access\(", r"user_load\("]
        for pattern in user_patterns:
            for match in re.finditer(pattern, content):
                surrounding = self._get_surrounding_code(content, match.start())
                if self._is_render_context(surrounding) and not self._has_user_cache_context(surrounding):
                    issues.append(self._make_finding(
                        "missing_user_context", "error",
                        content[: match.start()].count("\n") + 1, file_path,
                        "User-specific content rendered without a 'user' cache context — may leak data.",
                    ))
        return issues

    def _detect_user_context_overuse(self, content: str, file_path: str, context: Dict) -> List[Dict]:
        issues = []
        pattern = r"'contexts'\s*=>\s*\[.*?'user'(?!\.[a-z])"
        for match in re.finditer(pattern, content, re.DOTALL):
            if self._is_commented_code(content, match.start()):
                continue
            surrounding = self._get_surrounding_code(content, match.start(), 1200)
            if not self._has_user_specific_content(surrounding):
                issues.append(self._make_finding(
                    "user_context_overuse", "warning",
                    content[: match.start()].count("\n") + 1, file_path,
                    "Broad 'user' cache context used — 'user.permissions' may be sufficient.",
                ))
        return issues

    def _detect_early_rendering(self, content: str, file_path: str, context: Dict) -> List[Dict]:
        issues = []
        for pattern in [r"drupal_render\s*\(", r"render\(\s*\$"]:
            for match in re.finditer(pattern, content):
                func_ctx = self._get_function_context(content, match.start())
                if self._is_problematic_render_context(func_ctx, context):
                    issues.append(self._make_finding(
                        "early_rendering", "error",
                        content[: match.start()].count("\n") + 1, file_path,
                        "Early rendering detected — breaks cacheability bubbling.",
                    ))
        return issues

    def _detect_uncached_database_queries(self, content: str, file_path: str, context: Dict) -> List[Dict]:
        issues = []
        query_patterns = [
            (r"\\?Drupal::entityQuery", "Entity query"),
            (r"->getStorage.*?->load", "Entity loading"),
            (r"db_query\s*\(", "Legacy db_query() call"),
            (r"Views::getView", "Views query execution"),
        ]
        acceptable = ["hook_install", "hook_update", "hook_schema", "migrate", "batch", "drush", "cron"]
        for pattern, desc in query_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                if self._is_commented_code(content, match.start()):
                    continue
                func_ctx = self._get_function_context(content, match.start())
                if any(ctx in func_ctx.get("code", "").lower() for ctx in acceptable):
                    continue
                if self._is_expensive_render_context(func_ctx, context):
                    if not self._has_caching_nearby(content, match.start()):
                        line_num = content[: match.start()].count("\n") + 1
                        issues.append(self._make_finding(
                            "uncached_database_query", "warning",
                            line_num, file_path,
                            f"Uncached database operation ({desc}) in performance-critical context.",
                        ))
        return issues

    def _detect_missing_cache_tags(self, content: str, file_path: str, context: Dict) -> List[Dict]:
        issues = []
        for match in re.finditer(r"#cache\s*=>\s*\[([^\]]+)\]", content, re.DOTALL):
            cache_content = match.group(1)
            if not re.search(r"['\"]tags['\"]?\s*=>", cache_content):
                issues.append(self._make_finding(
                    "missing_cache_tags", "warning",
                    content[: match.start()].count("\n") + 1, file_path,
                    "#cache array found without cache tags — can lead to stale content.",
                ))
        return issues

    def _detect_missed_drupal_static_opportunity(self, content: str, file_path: str, context: Dict) -> List[Dict]:
        issues = []
        func_pattern = r"function\s+(\w+)\s*\((.*?)\)\s*\{"
        expensive_ops = r"->getStorage.*?->load|entityQuery|db_query"

        for func_match in re.finditer(func_pattern, content, re.DOTALL):
            func_name = func_match.group(1)
            func_body_start = func_match.end()
            brace_level, pos = 1, func_body_start
            while pos < len(content) and brace_level > 0:
                if content[pos] == "{":
                    brace_level += 1
                elif content[pos] == "}":
                    brace_level -= 1
                pos += 1
            func_body = content[func_body_start : pos - 1]

            if re.search(expensive_ops, func_body) and "drupal_static" not in func_body:
                call_count = len(re.findall(r"\b" + re.escape(func_name) + r"\s*\(", content))
                if call_count > 1:
                    issues.append(self._make_finding(
                        "missed_drupal_static", "info",
                        content[: func_match.start()].count("\n") + 1, file_path,
                        f'Function "{func_name}" has expensive ops and is called multiple times — consider drupal_static.',
                    ))
        return issues

    def _detect_cache_bin_opportunity(self, content: str, file_path: str, context: Dict) -> List[Dict]:
        default_bin_calls = re.findall(r"->cache\(\s*\)\s*->|cache_get\s*\(|cache_set\s*\(", content)
        if len(default_bin_calls) > 3:
            return [self._make_finding(
                "cache_bin_opportunity", "info", 1, file_path,
                "Module uses default cache bin multiple times — consider a custom cache bin.",
            )]
        return []

    def _detect_missing_specific_contexts(self, content: str, file_path: str, context: Dict) -> List[Dict]:
        issues = []
        for match in re.finditer(r"#cache\s*=>\s*\[([^\]]+)\]", content, re.DOTALL):
            cache_block = match.group(1)
            if ("routeMatch" in content or "getParameter" in content) and "url." not in cache_block:
                issues.append(self._make_finding(
                    "missing_url_context", "warning",
                    content[: match.start()].count("\n") + 1, file_path,
                    "Code depends on URL/route but #cache is missing a 'url.*' context.",
                ))
        return issues

    def _detect_missing_entity_tags(self, content: str, file_path: str, context: Dict) -> List[Dict]:
        issues = []
        load_pattern = r"\b(Node|User|Term)::load\(\s*\$(\w+)\s*\)|->getStorage\(['\"](\w+)['\"]\)->load\(\s*\$(\w+)\s*\)"
        for load_match in re.finditer(load_pattern, content):
            entity_type = (load_match.group(1) or load_match.group(3)).lower()
            surrounding = self._get_surrounding_code(content, load_match.start(), 800)
            for cache_match in re.finditer(r"#cache\s*=>\s*\[([^\]]+)\]", surrounding):
                cache_block = cache_match.group(1)
                if f"'{entity_type}:'" not in cache_block and f'"{entity_type}:"' not in cache_block:
                    issues.append(self._make_finding(
                        "missing_entity_tag", "warning",
                        content[: load_match.start()].count("\n") + 1, file_path,
                        f"Entity ({entity_type}) loaded but nearby #cache is missing its cache tag.",
                    ))
        return issues

    def _detect_bigpipe_opportunity(self, content: str, file_path: str, context: Dict) -> List[Dict]:
        issues = []
        pattern = r"#cache\s*=>\s*\[[^\]]*?(max-age\s*=>\s*0|['\"]user['\"](?!\.))"
        for match in re.finditer(pattern, content, re.DOTALL):
            issues.append(self._make_finding(
                "bigpipe_opportunity", "info",
                content[: match.start()].count("\n") + 1, file_path,
                "Highly dynamic render array — consider BigPipe #lazy_builder.",
            ))
        return issues

    # --- Deep caching detectors ---

    def _detect_cacheable_metadata_bubbling(self, content: str, file_path: str, context: Dict) -> List[Dict]:
        """Detect array_merge on render arrays that loses cache metadata."""
        issues = []
        pattern = r"array_merge\s*\([^)]*\$\w+.*?\)"
        for match in re.finditer(pattern, content):
            if self._is_commented_code(content, match.start()):
                continue
            surrounding = self._get_surrounding_code(content, match.start(), 600)
            if re.search(r"#(theme|markup|type|cache)", surrounding):
                if not re.search(r"addCacheableDependency|CacheableMetadata::createFromRenderArray", surrounding):
                    issues.append(self._make_finding(
                        "metadata_bubbling_lost", "warning",
                        content[: match.start()].count("\n") + 1, file_path,
                        "array_merge() on render arrays loses cache metadata. Use addCacheableDependency() to preserve cacheability.",
                    ))
        return issues

    def _detect_dependency_chain_break(self, content: str, file_path: str, context: Dict) -> List[Dict]:
        """Detect entity loaded but its cache tag not propagated to the returned render array."""
        issues = []
        entity_load_pattern = r"(\$\w+)\s*=\s*(?:(?:Node|User|Term|Media)::load\(|->getStorage\(['\"][\w]+['\"]\)->load\()"
        for match in re.finditer(entity_load_pattern, content):
            var_name = match.group(1)
            if self._is_commented_code(content, match.start()):
                continue
            after_code = content[match.start() : min(len(content), match.start() + 2000)]
            has_return_build = re.search(r"return\s+\$\w+\s*;|return\s+\[", after_code)
            if has_return_build:
                has_dependency_add = re.search(
                    rf"addCacheableDependency\s*\(\s*{re.escape(var_name)}|"
                    rf"getCacheTags|getCacheContexts|"
                    rf"#cache.*tags.*{re.escape(var_name)}",
                    after_code, re.DOTALL,
                )
                if not has_dependency_add:
                    issues.append(self._make_finding(
                        "dependency_chain_break", "warning",
                        content[: match.start()].count("\n") + 1, file_path,
                        f"Entity loaded into {var_name} but its cache tags are not propagated to the render array.",
                    ))
        return issues

    def _detect_stale_cache_tag_pattern(self, content: str, file_path: str, context: Dict) -> List[Dict]:
        """Detect only list-level tags without entity-specific tags — causes over-invalidation."""
        issues = []
        cache_tag_pattern = r"'tags'\s*=>\s*\[([^\]]+)\]"
        for match in re.finditer(cache_tag_pattern, content, re.DOTALL):
            tags_content = match.group(1)
            if self._is_commented_code(content, match.start()):
                continue
            has_list_tag = re.search(r"'(node_list|user_list|taxonomy_term_list|media_list)'", tags_content)
            has_entity_tag = re.search(r"'\w+:'\s*\.", tags_content) or re.search(r"getCacheTags", tags_content)
            if has_list_tag and not has_entity_tag:
                surrounding = self._get_surrounding_code(content, match.start(), 600)
                if re.search(r"(Node|User|Term|Media)::load|->getStorage.*->load", surrounding):
                    issues.append(self._make_finding(
                        "stale_cache_tag", "info",
                        content[: match.start()].count("\n") + 1, file_path,
                        "Only list-level cache tags used without entity-specific tags — causes over-invalidation.",
                    ))
        return issues

    def _detect_render_rebuilt_every_request(self, content: str, file_path: str, context: Dict) -> List[Dict]:
        """Detect hook_page_attachments/hook_page_build with no #cache metadata."""
        issues = []
        hook_patterns = [
            r"function\s+\w+_page_attachments\s*\(",
            r"function\s+\w+_page_build\s*\(",
            r"function\s+\w+_page_attachments_alter\s*\(",
        ]
        for hook_pattern in hook_patterns:
            for match in re.finditer(hook_pattern, content):
                if self._is_commented_code(content, match.start()):
                    continue
                func_body_start = match.end()
                brace_level, pos = 0, func_body_start
                while pos < len(content):
                    if content[pos] == "{":
                        brace_level += 1
                    elif content[pos] == "}":
                        brace_level -= 1
                        if brace_level == 0:
                            break
                    pos += 1
                func_body = content[func_body_start:pos]
                if func_body and "#cache" not in func_body and "CacheableMetadata" not in func_body:
                    issues.append(self._make_finding(
                        "render_rebuilt_every_request", "error",
                        content[: match.start()].count("\n") + 1, file_path,
                        "Page hook adds render elements without #cache metadata — content rebuilt every request.",
                    ))
        return issues

    def _detect_block_cacheability_leak(self, content: str, file_path: str, context: Dict) -> List[Dict]:
        """Detect BlockBase::build() using currentUser/request without matching cache contexts."""
        issues = []
        if context.get("type") != "block_plugin" and "@Block" not in content:
            return issues
        build_pattern = r"public\s+function\s+build\s*\(\s*\)\s*\{"
        for match in re.finditer(build_pattern, content):
            if self._is_commented_code(content, match.start()):
                continue
            func_body_start = match.end()
            brace_level, pos = 1, func_body_start
            while pos < len(content) and brace_level > 0:
                if content[pos] == "{":
                    brace_level += 1
                elif content[pos] == "}":
                    brace_level -= 1
                pos += 1
            func_body = content[func_body_start : pos - 1]
            leaks = []
            if re.search(r"\\?Drupal::currentUser\(\)|->currentUser\(\)", func_body):
                if not re.search(r"'user'|'user\.", func_body):
                    leaks.append("\\Drupal::currentUser() without user cache context")
            if re.search(r"\\?Drupal::request\(\)|->getRequest\(\)", func_body):
                if not re.search(r"'url\.|'route\.", func_body):
                    leaks.append("\\Drupal::request() without url/route cache context")
            for leak in leaks:
                issues.append(self._make_finding(
                    "block_cacheability_leak", "warning",
                    content[: match.start()].count("\n") + 1, file_path,
                    f"Block build() uses {leak}. Can cause stale/incorrect cached content.",
                ))
        return issues

    # --- Helpers ---

    @staticmethod
    def _make_finding(rule: str, severity: str, line: int, file_path: str, message: str) -> Dict[str, Any]:
        """Create a normalized finding dict matching the standard format."""
        return {
            "tool": "caching_analyzer",
            "file": file_path,
            "line": line,
            "severity": severity,
            "message": message,
            "rule": rule,
            "category": "performance",
        }

    @staticmethod
    def _prioritize_issues(issues: List[Dict]) -> List[Dict]:
        order = {"error": 0, "warning": 1, "info": 2}
        return sorted(issues, key=lambda x: order.get(x.get("severity", "info"), 3))

    @staticmethod
    def _get_surrounding_code(content: str, position: int, length: int = 300) -> str:
        start = max(0, position - length // 2)
        end = min(len(content), position + length // 2)
        return content[start:end]

    @staticmethod
    def _get_function_context(content: str, position: int) -> Dict:
        lines = content.split("\n")
        current_line = content[:position].count("\n")
        function_start, function_type = current_line, "unknown"
        for i in range(current_line, max(0, current_line - 50), -1):
            line = lines[i] if i < len(lines) else ""
            if re.search(r"function\s+(\w+)", line):
                function_type, function_start = "function", i
                break
            elif re.search(r"public\s+function\s+(\w+)", line):
                function_type, function_start = "method", i
                break
        function_end = min(len(lines), function_start + 20)
        return {"type": function_type, "start_line": function_start + 1, "code": "\n".join(lines[function_start:function_end])}

    @staticmethod
    def _is_render_context(code: str) -> bool:
        return bool(re.search(r"return\s+\[.*?#", code, re.DOTALL))

    @staticmethod
    def _has_user_cache_context(code: str) -> bool:
        return bool(re.search(r"contexts.*?user", code, re.DOTALL))

    @staticmethod
    def _has_user_specific_content(code: str) -> bool:
        return bool(re.search(r"\$user->|current_user\(\)|user_access\(", code, re.DOTALL))

    @staticmethod
    def _is_problematic_render_context(function_context: Dict, file_context: Dict) -> bool:
        problematic = ["controller", "hook_menu", "hook_init", "hook_preprocess"]
        if any(ctx in function_context["code"].lower() for ctx in problematic):
            return True
        if file_context["type"] == "controller":
            return True
        return any(hook["type"] in ["menu", "init", "preprocess"] for hook in file_context.get("hooks", []))

    @staticmethod
    def _is_expensive_render_context(function_context: Dict, file_context: Dict) -> bool:
        expensive = ["hook_menu", "hook_init", "hook_preprocess", "controller::", "build()"]
        if any(p.lower() in function_context.get("code", "").lower() for p in expensive):
            return True
        return file_context.get("has_expensive_operations", False) or file_context.get("type") in ["controller", "block_plugin"]

    @staticmethod
    def _has_caching_nearby(content: str, position: int, distance: int = 1000) -> bool:
        start = max(0, position - distance // 2)
        end = min(len(content), position + distance // 2)
        nearby = content[start:end]
        patterns = [r"cache_get", r"cache_set", r"Drupal::cache", r"#cache\s*=>", r"drupal_static"]
        return any(re.search(p, nearby, re.IGNORECASE) for p in patterns)

    @staticmethod
    def _is_commented_code(content: str, position: int) -> bool:
        line_start = content.rfind("\n", 0, position) + 1
        line_end = content.find("\n", position)
        if line_end == -1:
            line_end = len(content)
        line_content = content[line_start:line_end].strip()
        if line_content.startswith(("//", "#", "*")):
            return True
        comment_start = content.rfind("/*", 0, position)
        if comment_start != -1 and (content.find("*/", comment_start, position) == -1 or content.find("*/", comment_start) > position):
            return True
        return False


def run_caching_analysis(
    drupal_root: Path,
    scan_targets: List[str],
    progress_callback: Optional[Callable[[str], None]] = None,
) -> List[Finding]:
    """Run caching analysis and return normalized findings list."""
    log.info(f"Starting caching analysis on targets: {scan_targets}")
    analyzer = SmartCachingAnalyzer()

    php_files: List[Path] = []
    for target_path in scan_targets:
        abs_path = drupal_root / target_path
        if abs_path.is_dir():
            for file_path in abs_path.rglob("*"):
                if file_path.is_symlink():
                    continue
                if file_path.suffix in [".php", ".module", ".inc", ".install", ".theme"]:
                    try:
                        if file_path.stat().st_size > MAX_FILE_SIZE:
                            log.warning(f"Skipping oversized file ({file_path.stat().st_size} bytes): {file_path}")
                            continue
                    except OSError:
                        continue
                    php_files.append(file_path)

    log.info(f"Found {len(php_files)} files for caching analysis.")
    findings: List[Dict[str, Any]] = []

    for file_path in php_files:
        if progress_callback:
            progress_callback(str(file_path))
        issues = analyzer.analyze_file(file_path)
        for issue in issues:
            if issue:
                # Normalize file path to relative with forward slashes
                if "file" not in issue and "file_path" in issue:
                    try:
                        issue["file"] = Path(issue["file_path"]).relative_to(drupal_root).as_posix()
                    except ValueError:
                        issue["file"] = issue["file_path"]
                elif "file" in issue:
                    try:
                        issue["file"] = Path(issue["file"]).relative_to(drupal_root).as_posix()
                    except ValueError:
                        pass
                # Ensure standard keys
                issue.setdefault("tool", "caching_analyzer")
                issue.setdefault("category", "performance")
                issue.setdefault("rule", issue.get("type", "caching-issue"))
                findings.append(issue)

    log.info(f"Caching analysis finished. Found {len(findings)} issues.")
    return findings
