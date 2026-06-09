"""Drupal configuration analyzer — parses config/sync YAML files.

Drupal configuration structure analyzer.
Parses content types, block types, paragraphs, fields, views, taxonomies,
and builds a relationship map.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

log = logging.getLogger("EventHorizon.ConfigAnalyzer")


class DrupalConfigAnalyzer:
    """Parses Drupal config sync directory into structured data."""

    def __init__(self, config_sync_dir: str) -> None:
        self.config_dir = Path(config_sync_dir)
        self._configs: Dict[str, Any] = {}
        self._load_all_configs()

    def _load_all_configs(self) -> None:
        """Load all YAML files from the config sync directory."""
        if not self.config_dir.is_dir():
            log.warning(f"Config sync directory not found: {self.config_dir}")
            return

        for yml_file in self.config_dir.glob("*.yml"):
            try:
                with yml_file.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data:
                        self._configs[yml_file.stem] = data
            except (OSError, yaml.YAMLError) as e:
                log.warning(f"Failed to parse config file {yml_file.name}: {e}")

    def analyze_all_configs(self) -> Dict[str, Any]:
        """Analyze all config files and return structured data."""
        return {
            "content_types": self.parse_content_types(),
            "block_types": self.parse_block_types(),
            "paragraphs": self.parse_paragraphs(),
            "fields": self.parse_fields(),
            "views": self.parse_views(),
            "taxonomies": self.parse_taxonomies(),
            "relationships": self.build_relationships(),
        }

    def parse_content_types(self) -> List[Dict[str, Any]]:
        """Parse node.type.* config files."""
        types = []
        for name, data in self._configs.items():
            if name.startswith("node.type."):
                bundle = name.replace("node.type.", "")
                types.append({
                    "id": bundle,
                    "label": data.get("name", bundle),
                    "description": data.get("description", ""),
                })
        return types

    def parse_block_types(self) -> List[Dict[str, Any]]:
        """Parse block_content.type.* config files."""
        types = []
        for name, data in self._configs.items():
            if name.startswith("block_content.type."):
                bundle = name.replace("block_content.type.", "")
                types.append({
                    "id": bundle,
                    "label": data.get("label", bundle),
                    "description": data.get("description", ""),
                })
        return types

    def parse_paragraphs(self) -> List[Dict[str, Any]]:
        """Parse paragraphs.paragraphs_type.* config files."""
        types = []
        for name, data in self._configs.items():
            if name.startswith("paragraphs.paragraphs_type."):
                bundle = name.replace("paragraphs.paragraphs_type.", "")
                # Extract paragraph field references for relationship building
                types.append({
                    "id": bundle,
                    "label": data.get("label", bundle),
                    "description": data.get("description", ""),
                    "icon_default": data.get("icon_default", ""),
                    "behavior_plugins": data.get("behavior_plugins", {}),
                })
        return types

    def parse_fields(self) -> Dict[str, Any]:
        """Parse field.storage.* and field.field.* config files."""
        storages: List[Dict[str, Any]] = []
        instances: List[Dict[str, Any]] = []

        for name, data in self._configs.items():
            if name.startswith("field.storage."):
                parts = name.replace("field.storage.", "").split(".", 1)
                entity_type = parts[0] if parts else ""
                field_name = parts[1] if len(parts) > 1 else ""
                storages.append({
                    "id": name,
                    "entity_type": entity_type,
                    "field_name": field_name,
                    "type": data.get("type", ""),
                    "settings": data.get("settings", {}),
                })
            elif name.startswith("field.field."):
                # field.field.<entity_type>.<bundle>.<field_name>
                remainder = name.replace("field.field.", "")
                parts = remainder.split(".", 2)
                entity_type = parts[0] if parts else ""
                bundle = parts[1] if len(parts) > 1 else ""
                field_name = parts[2] if len(parts) > 2 else ""
                storages_ref = data.get("field_storage_config_id", "")
                instances.append({
                    "id": name,
                    "entity_type": entity_type,
                    "bundle": bundle,
                    "field_name": field_name,
                    "label": data.get("label", field_name),
                    "description": data.get("description", ""),
                    "required": data.get("required", False),
                    "field_type": data.get("field_type", ""),
                    "dependencies": data.get("dependencies", {}),
                })

        return {"storages": storages, "instances": instances}

    def parse_views(self) -> List[Dict[str, Any]]:
        """Parse views.view.* config files."""
        views = []
        for name, data in self._configs.items():
            if name.startswith("views.view."):
                view_id = name.replace("views.view.", "")
                displays = data.get("display", {})
                views.append({
                    "id": view_id,
                    "label": data.get("label", view_id),
                    "description": data.get("description", ""),
                    "base_table": data.get("base_table", ""),
                    "display_count": len(displays),
                    "displays": list(displays.keys()),
                })
        return views

    def parse_taxonomies(self) -> List[Dict[str, Any]]:
        """Parse taxonomy.vocabulary.* config files."""
        vocabs = []
        for name, data in self._configs.items():
            if name.startswith("taxonomy.vocabulary."):
                vid = name.replace("taxonomy.vocabulary.", "")
                vocabs.append({
                    "id": vid,
                    "label": data.get("name", vid),
                    "description": data.get("description", ""),
                })
        return vocabs

    def build_relationships(self) -> List[Dict[str, Any]]:
        """Build relationships between entities based on field references."""
        relationships = []
        fields = self.parse_fields()

        for instance in fields["instances"]:
            # Link field instance to its entity/bundle
            relationships.append({
                "type": "field_of",
                "source": instance["field_name"],
                "target": f"{instance['entity_type']}.{instance['bundle']}",
                "field_type": instance.get("field_type", ""),
            })

            # Check for entity reference fields pointing to other bundles
            deps = instance.get("dependencies", {})
            config_deps = deps.get("config", [])
            for dep in config_deps:
                if dep.startswith("node.type.") or dep.startswith("taxonomy.vocabulary."):
                    relationships.append({
                        "type": "references",
                        "source": f"{instance['entity_type']}.{instance['bundle']}",
                        "target": dep,
                        "via_field": instance["field_name"],
                    })

        return relationships
