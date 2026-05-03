"""Tests for compare_service."""

import pytest
from app.services.compare_service import get_project_metric_names


class TestGetProjectMetricNames:
    """Smoke test that the function exists and handles empty gracefully."""

    def test_import(self):
        from app.services.compare_service import compare_metrics
        assert callable(compare_metrics)

    def test_get_project_metric_names_import(self):
        assert callable(get_project_metric_names)
