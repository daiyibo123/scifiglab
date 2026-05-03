"""Config file parser — parse YAML / JSON / TOML config files for hyperparameters."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _try_yaml(text: str) -> Optional[dict]:
    try:
        import yaml
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _try_json(text: str) -> Optional[dict]:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _try_toml(text: str) -> Optional[dict]:
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            return None
    try:
        data = tomllib.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _try_ini(text: str) -> Optional[dict]:
    import configparser
    import io
    try:
        cp = configparser.ConfigParser()
        cp.read_string(text)
        result = {}
        for section in cp.sections():
            for k, v in cp.items(section):
                result[f"{section}.{k}"] = v
        return result if result else None
    except Exception:
        return None


def parse_config_text(text: str, ext: str = "") -> Tuple[Optional[dict], str]:
    """Parse config text and return (parsed_dict, format_name).

    Tries to detect format from extension, falls back to auto-detection.
    """
    ext = ext.lower().lstrip(".")

    # Try based on extension first
    if ext in ("yaml", "yml"):
        d = _try_yaml(text)
        if d is not None:
            return d, "yaml"
    elif ext == "json":
        d = _try_json(text)
        if d is not None:
            return d, "json"
    elif ext == "toml":
        d = _try_toml(text)
        if d is not None:
            return d, "toml"
    elif ext in ("ini", "cfg", "conf"):
        d = _try_ini(text)
        if d is not None:
            return d, "ini"

    # Auto-detect
    for parser, name in [
        (_try_json, "json"),
        (_try_yaml, "yaml"),
        (_try_toml, "toml"),
        (_try_ini, "ini"),
    ]:
        d = parser(text)
        if d is not None:
            return d, name

    return None, "unknown"


def flatten_dict(d: dict, prefix: str = "", sep: str = ".") -> Dict[str, Any]:
    """Flatten nested dict into flat key-value pairs."""
    items: Dict[str, Any] = {}
    for k, v in d.items():
        new_key = f"{prefix}{sep}{k}" if prefix else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep))
        elif isinstance(v, (list, tuple)):
            items[new_key] = json.dumps(v, ensure_ascii=False)
        else:
            items[new_key] = v
    return items


def parse_config_file(file_path: str, secret: str = "") -> Tuple[Optional[Dict[str, Any]], str]:
    """Parse a config file from disk. Returns (flat_dict, format).

    If secret is provided, attempts to decrypt the file first.
    """
    p = Path(file_path)
    if not p.exists():
        return None, "not_found"
    try:
        raw = p.read_bytes()
        # Try decryption
        if secret:
            from app.services.encryption import is_encrypted, decrypt_bytes
            if is_encrypted(raw):
                raw = decrypt_bytes(raw, secret) or raw
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        try:
            text = p.read_text(encoding="gbk")
        except Exception:
            return None, "read_error"

    ext = p.suffix.lstrip(".")
    parsed, fmt = parse_config_text(text, ext)
    if parsed is None:
        return None, fmt

    flat = flatten_dict(parsed)
    return flat, fmt


def diff_configs(configs: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    """Find keys that differ across multiple config dicts.

    Returns {key: [val_config1, val_config2, ...]} for keys that differ.
    """
    if len(configs) < 2:
        return {}

    all_keys = set()
    for c in configs:
        all_keys.update(c.keys())

    diff = {}
    for key in sorted(all_keys):
        values = [c.get(key) for c in configs]
        if len(set(str(v) for v in values)) > 1:
            diff[key] = values

    return diff
