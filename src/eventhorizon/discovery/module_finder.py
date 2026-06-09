"""Drupal module discovery by scanning for .info.yml files."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

log = logging.getLogger("EventHorizon.ModuleFinder")


@dataclass
class DrupalModule:
    """Represents a discovered Drupal module or theme."""

    name: str
    path: Path
    info_file: Path
    group: str  # "custom" or "contrib"

    @property
    def relative_path(self) -> str:
        return str(self.path)


@dataclass
class DiscoveryResult:
    """Result of module discovery across all scan targets."""

    modules: List[DrupalModule] = field(default_factory=list)
    scan_targets: List[str] = field(default_factory=list)

    @property
    def custom_modules(self) -> List[DrupalModule]:
        return [m for m in self.modules if m.group == "custom"]

    @property
    def contrib_modules(self) -> List[DrupalModule]:
        return [m for m in self.modules if m.group == "contrib"]


def discover_modules(
    drupal_root: Path,
    scan_targets: List[str],
    group_label: str = "custom",
) -> DiscoveryResult:
    """Find all Drupal modules/themes under the given scan target directories.

    Modules are identified by the presence of a *.info.yml file.
    """
    result = DiscoveryResult(scan_targets=scan_targets)

    for target_rel in scan_targets:
        target_dir = drupal_root / target_rel
        if not target_dir.is_dir():
            log.warning(f"Scan target does not exist: {target_dir}")
            continue

        # Determine group from path
        group = "contrib" if "contrib" in target_rel else "custom"

        for info_file in target_dir.rglob("*.info.yml"):
            if info_file.is_symlink():
                continue
            # e.g. "example_module.info.yml" -> stem is "example_module.info" -> strip ".info"
            module_name = info_file.stem.removesuffix(".info")
            module_dir = info_file.parent

            result.modules.append(
                DrupalModule(
                    name=module_name,
                    path=module_dir.relative_to(drupal_root),
                    info_file=info_file.relative_to(drupal_root),
                    group=group,
                )
            )

    log.info(
        f"Discovered {len(result.modules)} modules/themes "
        f"({len(result.custom_modules)} custom, {len(result.contrib_modules)} contrib)"
    )
    return result
