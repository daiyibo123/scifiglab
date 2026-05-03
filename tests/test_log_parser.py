"""
tests/test_log_parser.py — 智能日志解析模块的单元测试。

覆盖：
  1. 冒号竖线格式
  2. key=value 格式
  3. Step 格式
  4. tqdm 进度条格式
  5. JSON Lines 格式
  6. CSV 风格格式
  7. 表格型日志
  8. YOLO 风格日志
  9. 科学计数法
  10. 带时间戳日志
  11. 多行上下文日志
  12. 非数值字段跳过
  13. nan/inf 跳过
  14. metric_name 归一化
"""

import sys
from pathlib import Path

# 让 import app.services.log_parser 能找到项目根
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.log_parser import (
    LogParser,
    MetricRecord,
    ParseResult,
    CustomParseRule,
    normalize_name,
    parse_number,
)

parser = LogParser()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 辅助函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _metrics_dict(result: ParseResult):
    """把 records 转为 {metric_name: [values]} 方便断言。"""
    d = {}
    for r in result.records:
        d.setdefault(r.metric_name, []).append(r.metric_value)
    return d


def _first_epoch(result: ParseResult):
    for r in result.records:
        if r.epoch is not None:
            return r.epoch
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 冒号竖线格式
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_colon_pipe_format():
    text = """Epoch: 1 | train_loss: 0.1823 | val_loss: 0.1542 | psnr: 24.31 | ssim: 0.812 | dice: 0.763 | lr: 0.0002
Epoch: 2 | train_loss: 0.1518 | val_loss: 0.1329 | psnr: 25.02 | ssim: 0.834 | dice: 0.781 | lr: 0.0002"""
    r = parser.parse_text(text)
    assert r.parsed_line_count == 2
    d = _metrics_dict(r)
    assert "train_loss" in d
    assert "psnr" in d
    assert len(d["train_loss"]) == 2
    assert abs(d["train_loss"][0] - 0.1823) < 1e-5
    assert r.epoch_min == 1
    assert r.epoch_max == 2


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. key=value 格式
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_key_equals_value():
    text = """[Epoch 1] train_loss=0.1823 val_loss=0.1542 psnr=24.31 ssim=0.812 dice=0.763 lr=0.0002
[Epoch 2] train_loss=0.1518 val_loss=0.1329 psnr=25.02 ssim=0.834 dice=0.781 lr=0.0002"""
    r = parser.parse_text(text)
    assert r.parsed_line_count == 2
    d = _metrics_dict(r)
    assert "train_loss" in d
    assert "lr" in d
    assert r.epoch_min == 1 and r.epoch_max == 2


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Step 格式
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_step_format():
    text = """Step: 100 | loss: 0.123 | acc: 0.91
[Step 200] loss=0.101 acc=0.93"""
    r = parser.parse_text(text)
    d = _metrics_dict(r)
    assert "loss" in d
    assert "acc" in d
    assert r.step_min == 100
    assert r.step_max == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. tqdm 进度条格式
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_tqdm_progress_bar():
    text = '100%|██████████| 100/100 [01:23<00:00,  1.20it/s, loss=0.123, lr=2e-4, psnr=28.31]'
    r = parser.parse_text(text)
    d = _metrics_dict(r)
    assert "loss" in d
    assert abs(d["loss"][0] - 0.123) < 1e-5
    assert "lr" in d
    assert abs(d["lr"][0] - 2e-4) < 1e-8
    assert "psnr" in d


def test_tqdm_with_epoch():
    text = 'Epoch 1/100:  50%|█████     | 500/1000 [00:30<00:30, loss=0.231, acc=0.88]'
    r = parser.parse_text(text)
    d = _metrics_dict(r)
    assert "loss" in d
    assert r.epoch_min == 1


def test_tqdm_train_prefix():
    text = 'train: 100%|██████████| 200/200 [02:11<00:00, loss=0.0987, psnr=30.12, ssim=0.912]'
    r = parser.parse_text(text)
    d = _metrics_dict(r)
    assert "loss" in d
    assert "psnr" in d
    assert "ssim" in d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. JSON Lines 格式
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_json_lines():
    text = """{"epoch": 1, "train_loss": 0.1823, "val_loss": 0.1542, "psnr": 24.31, "ssim": 0.812}
{"epoch": 2, "train_loss": 0.1518, "val_loss": 0.1329, "psnr": 25.02, "ssim": 0.834}"""
    r = parser.parse_text(text)
    d = _metrics_dict(r)
    assert len(d["train_loss"]) == 2
    assert r.epoch_min == 1
    assert r.epoch_max == 2
    # epoch 不应作为普通指标
    assert "epoch" not in d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. CSV 风格格式
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_csv_format():
    text = """epoch,train_loss,val_loss,psnr,ssim,dice,lr
1,0.1823,0.1542,24.31,0.812,0.763,0.0002
2,0.1518,0.1329,25.02,0.834,0.781,0.0002"""
    r = parser.parse_text(text)
    d = _metrics_dict(r)
    assert len(d["train_loss"]) == 2
    assert abs(d["psnr"][1] - 25.02) < 1e-5
    assert r.epoch_min == 1 and r.epoch_max == 2
    assert "epoch" not in d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. 表格型日志（空格分隔）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_space_table():
    text = """epoch train_loss val_loss psnr ssim dice lr
1 0.1823 0.1542 24.31 0.812 0.763 0.0002
2 0.1518 0.1329 25.02 0.834 0.781 0.0002"""
    r = parser.parse_text(text)
    d = _metrics_dict(r)
    assert "train_loss" in d
    assert len(d["train_loss"]) == 2
    assert r.epoch_min == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. YOLO 风格日志
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_yolo_format():
    text = """Epoch    GPU_mem   box_loss   cls_loss   dfl_loss  Instances       Size
1/100      3.21G     0.9234     0.8123     1.1234        128        640
2/100      3.22G     0.8121     0.7012     1.0123        130        640"""
    r = parser.parse_text(text)
    d = _metrics_dict(r)
    assert "box_loss" in d
    assert "cls_loss" in d
    assert "dfl_loss" in d
    # GPU_mem 3.21G → 3.21
    assert "gpu_mem" in d
    assert abs(d["gpu_mem"][0] - 3.21) < 1e-5
    # Epoch 1/100 → epoch=1
    assert r.epoch_min == 1 and r.epoch_max == 2


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. 科学计数法
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_scientific_notation():
    text = "Epoch: 1 | lr: 1e-4 | loss: 2E-5"
    r = parser.parse_text(text)
    d = _metrics_dict(r)
    assert abs(d["lr"][0] - 1e-4) < 1e-10
    assert abs(d["loss"][0] - 2e-5) < 1e-10


def test_parse_number_variants():
    assert parse_number("0.123") == 0.123
    assert parse_number(".123") == 0.123
    assert parse_number("1") == 1.0
    assert parse_number("-1") == -1.0
    assert parse_number("-0.123") == -0.123
    assert parse_number("1e-4") == 1e-4
    assert parse_number("2E-5") == 2e-5
    assert parse_number("+3.14") == 3.14
    assert abs(parse_number("3.21G") - 3.21) < 1e-5
    assert parse_number("88%") == 88.0
    assert parse_number("nan") is None
    assert parse_number("NaN") is None
    assert parse_number("inf") is None
    assert parse_number("Infinity") is None
    assert parse_number("hello") is None
    assert parse_number("") is None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10. 带时间戳日志
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_timestamped_log():
    text = """2026-05-03 12:30:01 - Epoch: 1 - train_loss: 0.1823 - val_loss: 0.1542 - psnr: 24.31
[2026-05-03 12:30:01] epoch=1 step=100 loss=0.123 acc=0.91"""
    r = parser.parse_text(text)
    d = _metrics_dict(r)
    assert "train_loss" in d or "loss" in d
    assert r.epoch_min == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 11. 多行上下文日志
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_multiline_context():
    text = """Epoch: 1
train_loss: 0.1823
val_loss: 0.1542
psnr: 24.31
Epoch: 2
train_loss: 0.1518
val_loss: 0.1329
psnr: 25.02"""
    r = parser.parse_text(text)
    d = _metrics_dict(r)
    assert "train_loss" in d
    assert len(d["train_loss"]) == 2
    # first three metrics should have epoch=1, next three epoch=2
    ep1 = [rec for rec in r.records if rec.epoch == 1]
    ep2 = [rec for rec in r.records if rec.epoch == 2]
    assert len(ep1) == 3
    assert len(ep2) == 3


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 12. 非数值字段跳过
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_non_numeric_skipped():
    text = """model: ResNet50
status: running
loss: 0.123"""
    r = parser.parse_text(text)
    d = _metrics_dict(r)
    # 'ResNet50' and 'running' are not numbers, should be skipped
    assert "model" not in d
    assert "status" not in d
    assert "loss" in d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 13. nan / inf 跳过
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_nan_inf_skipped():
    text = """loss: nan
psnr: inf
ssim: 0.812
lr: NaN
dice: Infinity"""
    r = parser.parse_text(text)
    d = _metrics_dict(r)
    assert "loss" not in d
    assert "psnr" not in d
    assert "lr" not in d
    assert "dice" not in d
    assert "ssim" in d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 14. metric_name 归一化
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_name_normalization():
    assert normalize_name("train/loss") == "train_loss"
    assert normalize_name("val/loss") == "val_loss"
    assert normalize_name("train.loss") == "train_loss"
    assert normalize_name("GPU_mem") == "gpu_mem"
    assert normalize_name("learning_rate") == "lr"
    assert normalize_name("validation_loss") == "val_loss"
    assert normalize_name("  Loss  ") == "loss"
    assert normalize_name("box-loss") == "box_loss"
    assert normalize_name("a//b") == "a_b"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 额外：Epoch+Iter 混合格式
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_epoch_iter_mixed():
    text = "Epoch [1/100] Iter [50/1000] loss: 0.2134 lr: 2e-4"
    r = parser.parse_text(text)
    assert r.epoch_min == 1
    assert r.step_min == 50
    d = _metrics_dict(r)
    assert "loss" in d


def test_epoch_iter_comma():
    text = "Epoch: 3/100, Iter: 500/1000, train_loss: 0.123, psnr: 28.91"
    r = parser.parse_text(text)
    assert r.epoch_min == 3
    assert r.step_min == 500
    d = _metrics_dict(r)
    assert "train_loss" in d
    assert "psnr" in d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Iter / iteration 日志
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_iter_format():
    text = """Iter: 100 | loss: 0.231 | lr: 1e-4
Iteration 200: loss=0.198, psnr=25.12, ssim=0.843"""
    r = parser.parse_text(text)
    assert r.step_min == 100
    assert r.step_max == 200
    d = _metrics_dict(r)
    assert "loss" in d


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PyTorch Lightning 风格
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_pytorch_lightning():
    text = "Epoch 3: 100%|██████████| 500/500 [02:30<00:00, train_loss=0.123, val_loss=0.101, val_acc=0.93]"
    r = parser.parse_text(text)
    d = _metrics_dict(r)
    assert "train_loss" in d
    assert "val_loss" in d
    assert "val_acc" in d
    assert r.epoch_min == 3


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 普通实验记录
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_generic_experiment():
    text = """time: 0 | temperature: 25.1 | pressure: 101.3 | voltage: 3.7 | current: 0.12
time=10 temperature=26.2 pressure=101.1 voltage=3.6 current=0.13"""
    r = parser.parse_text(text)
    d = _metrics_dict(r)
    assert "temperature" in d
    assert "pressure" in d
    assert "voltage" in d
    assert len(d["temperature"]) == 2


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ParseResult 汇总
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_parse_result_summary():
    text = """Epoch: 1 | loss: 0.5
Epoch: 2 | loss: 0.3
This line has nothing useful
"""
    r = parser.parse_text(text)
    assert r.line_count == 3
    assert r.parsed_line_count == 2
    assert r.skipped_line_count >= 1
    assert "loss" in r.metric_names


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 自定义规则（预留接口）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_custom_rules():
    rules = CustomParseRule(
        epoch_pattern=r"Round\s+(\d+)",
        metric_pattern=r"([a-zA-Z_]+)\s*=\s*([0-9.]+)",
    )
    p = LogParser(custom_rules=rules)
    text = "Round 5 score=0.95 error=0.05"
    r = p.parse_text(text)
    d = _metrics_dict(r)
    assert "score" in d
    assert abs(d["score"][0] - 0.95) < 1e-5
    assert r.epoch_min == 5


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 空输入
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_empty_input():
    r = parser.parse_text("")
    assert r.line_count == 0  # splitlines on "" gives []
    assert len(r.records) == 0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
