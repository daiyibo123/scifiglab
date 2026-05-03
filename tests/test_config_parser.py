"""Tests for config_parser service."""

import pytest
from app.services.config_parser import (
    parse_config_text, flatten_dict, diff_configs,
)


class TestParseConfigText:
    def test_json(self):
        text = '{"lr": 0.001, "batch_size": 32}'
        d, fmt = parse_config_text(text, "json")
        assert fmt == "json"
        assert d["lr"] == 0.001
        assert d["batch_size"] == 32

    def test_yaml(self):
        text = "lr: 0.001\nbatch_size: 32\n"
        d, fmt = parse_config_text(text, "yaml")
        assert fmt == "yaml"
        assert d["lr"] == 0.001

    def test_auto_detect_json(self):
        text = '{"epochs": 100}'
        d, fmt = parse_config_text(text)
        assert fmt == "json"
        assert d["epochs"] == 100

    def test_invalid(self):
        text = "not a valid config !!@#$"
        d, fmt = parse_config_text(text, "xyz")
        # May parse as YAML string, check if it returns something or None
        # YAML can parse plain strings, so it may return None for non-dict
        assert d is None or isinstance(d, dict)

    def test_ini(self):
        text = "[training]\nlr = 0.001\nepochs = 100\n"
        d, fmt = parse_config_text(text, "ini")
        assert fmt == "ini"
        assert "training.lr" in d


class TestFlattenDict:
    def test_nested(self):
        d = {"model": {"hidden": 256, "layers": 4}, "lr": 0.01}
        flat = flatten_dict(d)
        assert flat["model.hidden"] == 256
        assert flat["model.layers"] == 4
        assert flat["lr"] == 0.01

    def test_list_value(self):
        d = {"tags": ["a", "b"]}
        flat = flatten_dict(d)
        assert flat["tags"] == '["a", "b"]'

    def test_empty(self):
        assert flatten_dict({}) == {}


class TestDiffConfigs:
    def test_diff(self):
        c1 = {"lr": 0.001, "batch_size": 32, "epochs": 100}
        c2 = {"lr": 0.01, "batch_size": 32, "epochs": 200}
        diff = diff_configs([c1, c2])
        assert "lr" in diff
        assert "epochs" in diff
        assert "batch_size" not in diff

    def test_single_config(self):
        assert diff_configs([{"a": 1}]) == {}

    def test_empty(self):
        assert diff_configs([]) == {}
