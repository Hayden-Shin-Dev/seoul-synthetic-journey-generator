from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_simple_yaml(path: Path) -> dict[str, Any]:
    """Read the deliberately small YAML subset used by the project configs."""
    try:
        import yaml  # type: ignore
    except ImportError:
        return _load_yaml_subset(path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_config(config_dir: Path) -> dict[str, Any]:
    return {
        "generator": load_simple_yaml(config_dir / "generator.yaml"),
        "noise": load_simple_yaml(config_dir / "noise.yaml"),
        "scenarios": load_simple_yaml(config_dir / "scenarios.yaml"),
    }


def config_hash(config: dict[str, Any]) -> str:
    import hashlib

    payload = json.dumps(config, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_yaml_subset(path: Path) -> dict[str, Any]:
    """Fallback parser for mappings, lists, scalars and inline mappings."""
    # Config files remain valid JSON-compatible YAML, so this fallback covers
    # the scalar and nested mapping forms used here without adding a runtime dependency.
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError("PyYAML is required to read the project YAML configs")

