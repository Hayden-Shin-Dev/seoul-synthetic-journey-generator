from __future__ import annotations

import json
import re
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
    """Parse the small mapping/list/scalar YAML subset used in the configs."""
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    parsed, _ = _parse_block(lines, 0, 0)
    return parsed


def _parse_block(lines: list[str], index: int, indent: int) -> tuple[Any, int]:
    is_list = lines[index].startswith(" " * indent + "-")
    result: Any = [] if is_list else {}
    while index < len(lines):
        line = lines[index]
        current_indent = len(line) - len(line.lstrip(" "))
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ValueError(f"unexpected indentation in {line}")
        content = line[indent:]
        if is_list:
            if not content.startswith("- "):
                break
            result.append(_parse_scalar(content[2:].strip()))
        else:
            key, separator, value = content.partition(":")
            if not separator:
                raise ValueError(f"invalid config line: {line}")
            value = value.strip()
            if value:
                result[key.strip()] = _parse_scalar(value)
            elif index + 1 < len(lines) and len(lines[index + 1]) - len(lines[index + 1].lstrip(" ")) > indent:
                child_indent = len(lines[index + 1]) - len(lines[index + 1].lstrip(" "))
                result[key.strip()], index = _parse_block(lines, index + 1, child_indent)
                continue
            else:
                result[key.strip()] = {}
        index += 1
    return result, index


def _parse_scalar(value: str) -> Any:
    if value.startswith("{") or value.startswith("["):
        inner = value[1:-1].strip()
        if value.startswith("["):
            return [_parse_scalar(part.strip()) for part in inner.split(",") if part.strip()]
        result = {}
        for part in re.split(r",\s*(?=[A-Za-z_][A-Za-z0-9_]*\s*:)", inner):
            key, _, item = part.partition(":")
            result[key.strip().strip("\"'")] = _parse_scalar(item.strip())
        return result
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value
