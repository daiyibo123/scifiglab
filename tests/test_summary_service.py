"""Tests for summary_service — metric direction, smoothing, build_series, summarize."""

import pytest
from app.services.summary_service import (
    get_metric_direction,
    smooth,
    _best_point,
    _last_point,
)


# ─── get_metric_direction ────────────────────────────────────────────────

class TestMetricDirection:
    def test_lower_better_keywords(self):
        assert get_metric_direction("train_loss") == "lower_better"
        assert get_metric_direction("val_loss") == "lower_better"
        assert get_metric_direction("MAE") == "lower_better"
        assert get_metric_direction("test_mse") == "lower_better"
        assert get_metric_direction("rmse") == "lower_better"
        assert get_metric_direction("Error_Rate") == "lower_better"
        assert get_metric_direction("Latency_ms") == "lower_better"

    def test_higher_better_keywords(self):
        assert get_metric_direction("psnr") == "higher_better"
        assert get_metric_direction("SSIM") == "higher_better"
        assert get_metric_direction("test_accuracy") == "higher_better"
        assert get_metric_direction("f1_score") == "higher_better"
        assert get_metric_direction("dice_coeff") == "higher_better"
        assert get_metric_direction("IoU") == "higher_better"
        assert get_metric_direction("AUC") == "higher_better"
        assert get_metric_direction("Recall") == "higher_better"
        assert get_metric_direction("Precision") == "higher_better"
        assert get_metric_direction("Yield_percent") == "higher_better"

    def test_unknown_defaults_higher(self):
        assert get_metric_direction("learning_rate") == "higher_better"
        assert get_metric_direction("xyz_metric") == "higher_better"

    def test_loss_takes_priority_over_score(self):
        # "loss" appears before "score" in lower-better check
        assert get_metric_direction("loss_score") == "lower_better"


# ─── smooth ──────────────────────────────────────────────────────────────

class TestSmooth:
    def test_window_1_noop(self):
        vals = [1.0, 2.0, 3.0]
        assert smooth(vals, 1) == [1.0, 2.0, 3.0]

    def test_empty(self):
        assert smooth([], 5) == []

    def test_window_3(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = smooth(vals, 3)
        assert len(result) == 5
        # first element: avg of [1,2] = 1.5
        assert abs(result[0] - 1.5) < 1e-9
        # middle: avg of [1,2,3] = 2.0
        assert abs(result[1] - 2.0) < 1e-9
        # center: avg of [2,3,4] = 3.0
        assert abs(result[2] - 3.0) < 1e-9
        # last: avg of [4,5] = 4.5
        assert abs(result[4] - 4.5) < 1e-9

    def test_window_larger_than_data(self):
        vals = [10.0, 20.0]
        result = smooth(vals, 10)
        assert len(result) == 2
        # boundaries capped
        assert abs(result[0] - 15.0) < 1e-9
        assert abs(result[1] - 15.0) < 1e-9


# ─── _best_point / _last_point ──────────────────────────────────────────

class TestBestLastPoint:
    def test_best_higher(self):
        points = [
            {"x": 1, "raw_y": 0.5, "epoch": 1, "step": None, "time": None},
            {"x": 2, "raw_y": 0.9, "epoch": 2, "step": None, "time": None},
            {"x": 3, "raw_y": 0.7, "epoch": 3, "step": None, "time": None},
        ]
        bp = _best_point(points, "higher_better")
        assert bp["y"] == 0.9
        assert bp["x"] == 2

    def test_best_lower(self):
        points = [
            {"x": 1, "raw_y": 0.5, "epoch": 1, "step": None, "time": None},
            {"x": 2, "raw_y": 0.1, "epoch": 2, "step": None, "time": None},
            {"x": 3, "raw_y": 0.3, "epoch": 3, "step": None, "time": None},
        ]
        bp = _best_point(points, "lower_better")
        assert bp["y"] == 0.1
        assert bp["x"] == 2

    def test_best_empty(self):
        assert _best_point([], "higher_better") is None

    def test_last_point(self):
        points = [
            {"x": 1, "raw_y": 0.5, "epoch": 1, "step": None, "time": None},
            {"x": 2, "raw_y": 0.9, "epoch": 2, "step": None, "time": None},
        ]
        lp = _last_point(points)
        assert lp["y"] == 0.9
        assert lp["x"] == 2

    def test_last_empty(self):
        assert _last_point([]) is None
