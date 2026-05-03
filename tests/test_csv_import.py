"""
tests/test_csv_import.py — CSV 指标导入的单元测试。

覆盖：
  1. 标准 epoch CSV
  2. step CSV
  3. time CSV
  4. 没有横轴时使用行号作为 step
  5. 科学计数法
  6. 百分号
  7. 带单位数值
  8. 空值跳过
  9. 非数值跳过
  10. nan/inf 跳过
  11. metric_name 归一化
  12. overwrite 覆盖旧指标（纯解析层面验证去重逻辑）
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.metric_service import parse_csv_text


def _metrics_dict(records):
    """records -> {metric_name: [values]}"""
    d = {}
    for r in records:
        d.setdefault(r.metric_name, []).append(r.metric_value)
    return d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 标准 epoch CSV
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_epoch_csv():
    text = "epoch,train_loss,val_loss,psnr,ssim,dice,lr\n1,0.1823,0.1542,24.31,0.812,0.763,0.0002\n2,0.1518,0.1329,25.02,0.834,0.781,0.0002\n"
    records, result = parse_csv_text(text)
    d = _metrics_dict(records)
    assert "train_loss" in d
    assert len(d["train_loss"]) == 2
    assert abs(d["psnr"][1] - 25.02) < 1e-5
    assert result.epoch_min == 1
    assert result.epoch_max == 2
    assert "epoch" not in d  # epoch 是横轴，不作为指标


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. step CSV
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_step_csv():
    text = "step,loss,accuracy,error_rate\n100,0.231,0.88,0.12\n200,0.198,0.90,0.10\n"
    records, result = parse_csv_text(text)
    d = _metrics_dict(records)
    assert "loss" in d
    assert "accuracy" in d
    assert result.step_min == 100
    assert result.step_max == 200
    assert "step" not in d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. time CSV
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_time_csv():
    text = "time,temperature,pressure,voltage,current\n0,25.1,101.3,3.7,0.12\n10,26.2,101.1,3.6,0.13\n"
    records, result = parse_csv_text(text)
    d = _metrics_dict(records)
    assert "temperature" in d
    assert "pressure" in d
    assert len(d["temperature"]) == 2
    assert result.time_min == 0.0
    assert result.time_max == 10.0
    # time -> step fallback
    assert result.step_min == 0
    assert result.step_max == 10
    assert "time" not in d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 没有横轴 -> 行号作为 step
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_no_axis_uses_row_number():
    text = "loss,accuracy\n0.5,0.8\n0.3,0.9\n0.1,0.95\n"
    records, result = parse_csv_text(text)
    # step should be row numbers: 1, 2, 3
    steps = sorted(set(r.step for r in records))
    assert steps == [1, 2, 3]
    assert result.step_min == 1
    assert result.step_max == 3


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 科学计数法
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_scientific_notation():
    text = "epoch,lr,loss\n1,1e-4,2E-5\n2,1e-3,3E-6\n"
    records, result = parse_csv_text(text)
    d = _metrics_dict(records)
    assert abs(d["lr"][0] - 1e-4) < 1e-10
    assert abs(d["loss"][0] - 2e-5) < 1e-10


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. 百分号
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_percent_values():
    text = "epoch,accuracy\n1,88%\n2,92%\n"
    records, result = parse_csv_text(text)
    d = _metrics_dict(records)
    assert abs(d["accuracy"][0] - 88.0) < 1e-5
    assert abs(d["accuracy"][1] - 92.0) < 1e-5


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. 带单位数值
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_unit_suffix():
    text = "epoch,gpu_mem,vram\n1,3.21G,1.5M\n2,3.22G,1.6M\n"
    records, result = parse_csv_text(text)
    d = _metrics_dict(records)
    assert abs(d["gpu_mem"][0] - 3.21) < 1e-5
    assert abs(d["vram"][0] - 1.5) < 1e-5


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. 空值跳过
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_empty_values_skipped():
    text = "epoch,loss,psnr\n1,0.5,\n2,,25.0\n3,0.1,26.0\n"
    records, result = parse_csv_text(text)
    d = _metrics_dict(records)
    # epoch 1: loss=0.5, psnr empty -> 1 metric
    # epoch 2: loss empty, psnr=25.0 -> 1 metric
    # epoch 3: both present -> 2 metrics
    assert len(d["loss"]) == 2  # epoch 1 and 3
    assert len(d["psnr"]) == 2  # epoch 2 and 3


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. 非数值跳过
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_non_numeric_skipped():
    text = "epoch,model,loss\n1,ResNet50,0.5\n2,VGG16,0.3\n"
    records, result = parse_csv_text(text)
    d = _metrics_dict(records)
    assert "loss" in d
    # model column has non-numeric values -> all cells skipped
    # but 'model' is still a metric column (just no values parsed)
    assert "model" not in d or len(d.get("model", [])) == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10. nan/inf 跳过
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_nan_inf_skipped():
    text = "epoch,loss,psnr\n1,nan,24.0\n2,inf,25.0\n3,0.1,NaN\n4,0.05,26.0\n"
    records, result = parse_csv_text(text)
    d = _metrics_dict(records)
    # nan/inf values should be skipped
    assert len(d.get("loss", [])) == 2  # only epochs 3, 4
    # epoch 1: loss=nan skip, psnr=24.0 ok
    # epoch 2: loss=inf skip, psnr=25.0 ok
    # epoch 3: loss=0.1 ok, psnr=NaN skip
    # epoch 4: both ok
    assert len(d["psnr"]) == 3  # epochs 1, 2, 4


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 11. metric_name 归一化
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_metric_name_normalization():
    text = "epoch,train/loss,val.loss,GPU_mem,learning_rate\n1,0.5,0.4,3.2,0.001\n"
    records, result = parse_csv_text(text)
    names = result.metric_names
    assert "train_loss" in names
    assert "val_loss" in names
    assert "gpu_mem" in names
    assert "lr" in names  # learning_rate -> lr alias


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 12. overwrite 去重
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_dedup_within_file():
    """Duplicate rows in same CSV should produce separate records (same epoch/step but different values)."""
    text = "epoch,loss\n1,0.5\n1,0.4\n2,0.3\n"
    records, result = parse_csv_text(text)
    # epoch 1 appears twice with different loss -> both records kept
    d = _metrics_dict(records)
    assert len(d["loss"]) == 3


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 额外：空 CSV
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_empty_csv():
    records, result = parse_csv_text("")
    assert len(records) == 0
    assert "CSV 为空" in result.warnings


def test_header_only():
    text = "epoch,loss\n"
    records, result = parse_csv_text(text)
    assert len(records) == 0
    assert result.imported_records_count == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 额外：iter 列
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_iter_column():
    text = "iter,loss,psnr\n100,0.5,24.0\n200,0.3,25.0\n"
    records, result = parse_csv_text(text)
    assert result.step_min == 100
    assert result.step_max == 200
    d = _metrics_dict(records)
    assert "loss" in d


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
