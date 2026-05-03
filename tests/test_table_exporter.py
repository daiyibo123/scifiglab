"""Tests for table_exporter service."""

import pytest
from app.services.table_exporter import format_metric_value, find_best_values


class TestFormatMetricValue:
    def test_none(self):
        assert format_metric_value(None) == "-"

    def test_default_decimals(self):
        assert format_metric_value(0.123456) == "0.1235"

    def test_custom_decimals(self):
        assert format_metric_value(0.123456, 2) == "0.12"

    def test_zero(self):
        assert format_metric_value(0.0, 3) == "0.000"


class TestFindBestValues:
    def test_higher_better(self):
        rows = [{"acc": 0.9}, {"acc": 0.95}, {"acc": 0.88}]
        directions = {"acc": "higher_better"}
        best = find_best_values(rows, ["acc"], directions)
        assert best["acc"] == (0.95, 1)

    def test_lower_better(self):
        rows = [{"loss": 0.5}, {"loss": 0.3}, {"loss": 0.4}]
        directions = {"loss": "lower_better"}
        best = find_best_values(rows, ["loss"], directions)
        assert best["loss"] == (0.3, 1)

    def test_missing_values(self):
        rows = [{"acc": None}, {"acc": 0.9}]
        directions = {"acc": "higher_better"}
        best = find_best_values(rows, ["acc"], directions)
        assert best["acc"] == (0.9, 1)

    def test_empty(self):
        best = find_best_values([], ["acc"], {"acc": "higher_better"})
        assert best == {}

    def test_multi_metric(self):
        rows = [{"acc": 0.9, "loss": 0.5}, {"acc": 0.95, "loss": 0.3}]
        directions = {"acc": "higher_better", "loss": "lower_better"}
        best = find_best_values(rows, ["acc", "loss"], directions)
        assert best["acc"] == (0.95, 1)
        assert best["loss"] == (0.3, 1)
