"""
Metric service — 指标记录、查询、CSV 导入。

CSV 导入逻辑：
  - 自动识别 epoch / step / iter / iteration / batch / time 横轴列
  - 其余数值列作为 metric
  - 名称归一化、数值解析（科学计数法 / 百分号 / 单位后缀 / nan·inf 跳过）
  - 无横轴时按行号作为 step
  - 支持 overwrite / 追加去重
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.database.models import Metric
from app.services.log_parser import AXIS_KEYS, normalize_name, parse_number


# ═══════════════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class CsvImportResult:
    """CSV 导入结果摘要。"""
    imported_records_count: int = 0
    metric_names: List[str] = field(default_factory=list)
    epoch_min: Optional[int] = None
    epoch_max: Optional[int] = None
    step_min: Optional[int] = None
    step_max: Optional[int] = None
    time_min: Optional[float] = None
    time_max: Optional[float] = None
    skipped_columns: List[str] = field(default_factory=list)
    skipped_rows: int = 0
    warnings: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# CSV 解析（纯逻辑，不依赖 DB）
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class _CsvRecord:
    epoch: Optional[int] = None
    step: Optional[int] = None
    metric_name: str = ""
    metric_value: float = 0.0


def parse_csv_text(text: str) -> tuple[list[_CsvRecord], CsvImportResult]:
    """
    解析 CSV 文本，返回 (records, summary)。

    不涉及数据库操作，方便单元测试。
    """
    result = CsvImportResult()
    records: list[_CsvRecord] = []

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        result.warnings.append("CSV 为空")
        return records, result

    # ── 表头 ──
    raw_header = rows[0]
    norm_header = [normalize_name(h) for h in raw_header]

    # 分类列
    epoch_col: Optional[int] = None
    step_col: Optional[int] = None
    time_col: Optional[int] = None
    metric_cols: list[tuple[int, str]] = []   # (col_index, norm_name)

    for i, name in enumerate(norm_header):
        if not name:
            result.skipped_columns.append(raw_header[i] if i < len(raw_header) else "")
            continue
        if name == "epoch":
            epoch_col = i
        elif name in ("step", "iter", "iteration", "batch"):
            step_col = i
        elif name == "time":
            time_col = i
        elif name in AXIS_KEYS:
            # 其余 AXIS_KEYS 暂不专门处理
            pass
        else:
            metric_cols.append((i, name))

    if not metric_cols:
        result.warnings.append("未找到任何指标列")
        return records, result

    # 判断是否有横轴
    has_axis = epoch_col is not None or step_col is not None or time_col is not None

    # ── 数据行 ──
    epochs: list[int] = []
    steps: list[int] = []
    times: list[float] = []
    names_seen: set[str] = set()

    for row_idx, row in enumerate(rows[1:], start=1):
        if not any(cell.strip() for cell in row):
            result.skipped_rows += 1
            continue

        # 提取横轴
        row_epoch: Optional[int] = None
        row_step: Optional[int] = None
        row_time: Optional[float] = None

        if epoch_col is not None and epoch_col < len(row):
            v = parse_number(row[epoch_col].split("/")[0])
            if v is not None:
                row_epoch = int(v)

        if step_col is not None and step_col < len(row):
            v = parse_number(row[step_col].split("/")[0])
            if v is not None:
                row_step = int(v)

        if time_col is not None and time_col < len(row):
            v = parse_number(row[time_col])
            if v is not None:
                row_time = v

        # 无横轴时用行号作 step
        if not has_axis:
            row_step = row_idx

        # 如果只有 time，把 time 当 step
        if row_epoch is None and row_step is None and row_time is not None:
            row_step = int(row_time)

        row_has_metric = False
        for col_i, col_name in metric_cols:
            if col_i >= len(row):
                continue
            val = parse_number(row[col_i])
            if val is None:
                continue
            records.append(_CsvRecord(
                epoch=row_epoch,
                step=row_step,
                metric_name=col_name,
                metric_value=val,
            ))
            names_seen.add(col_name)
            row_has_metric = True

        if row_has_metric:
            if row_epoch is not None:
                epochs.append(row_epoch)
            if row_step is not None:
                steps.append(row_step)
            if row_time is not None:
                times.append(row_time)
        else:
            result.skipped_rows += 1

    # 跳过的列（表头中有但不是横轴也不是指标列的）
    metric_col_names = {name for _, name in metric_cols}
    for i, name in enumerate(norm_header):
        if name and name not in metric_col_names and name not in AXIS_KEYS:
            result.skipped_columns.append(raw_header[i])

    result.metric_names = sorted(names_seen)
    if epochs:
        result.epoch_min = min(epochs)
        result.epoch_max = max(epochs)
    if steps:
        result.step_min = min(steps)
        result.step_max = max(steps)
    if times:
        result.time_min = min(times)
        result.time_max = max(times)

    return records, result


# ═══════════════════════════════════════════════════════════════════════════
# DB 写入
# ═══════════════════════════════════════════════════════════════════════════

def import_metrics_from_csv(
    db: Session,
    file_text: str,
    user_id: int,
    project_id: int,
    experiment_id: int,
    source_file_id: int,
    overwrite: bool = False,
) -> CsvImportResult:
    """
    解析 CSV 文本并写入 Metric 表。

    Args:
        overwrite: True 先删除同 source_file_id 的旧指标再导入，
                   False 追加但跳过重复记录。
    """
    records, result = parse_csv_text(file_text)

    if not records:
        return result

    # overwrite：删旧
    if overwrite:
        db.query(Metric).filter(
            Metric.experiment_id == experiment_id,
            Metric.source_file_id == source_file_id,
            Metric.user_id == user_id,
        ).delete(synchronize_session=False)
        db.flush()

    # 追加去重
    existing: set[tuple] = set()
    if not overwrite:
        rows = (
            db.query(Metric.metric_name, Metric.epoch, Metric.step)
            .filter(
                Metric.experiment_id == experiment_id,
                Metric.source_file_id == source_file_id,
                Metric.user_id == user_id,
            )
            .all()
        )
        existing = {(r.metric_name, r.epoch, r.step) for r in rows}

    inserted = 0
    for rec in records:
        dup_key = (rec.metric_name, rec.epoch, rec.step)
        if dup_key in existing:
            continue
        existing.add(dup_key)
        db.add(Metric(
            user_id=user_id,
            project_id=project_id,
            experiment_id=experiment_id,
            metric_name=rec.metric_name,
            metric_value=rec.metric_value,
            epoch=rec.epoch,
            step=rec.step,
            source_file_id=source_file_id,
        ))
        inserted += 1

    db.commit()
    result.imported_records_count = inserted
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 基础 CRUD（保留原有接口）
# ═══════════════════════════════════════════════════════════════════════════

def record_metric(
    db: Session,
    user_id: int,
    project_id: int,
    experiment_id: int,
    metric_name: str,
    metric_value: float,
    step: Optional[int] = None,
    epoch: Optional[int] = None,
    source_file_id: Optional[int] = None,
) -> Metric:
    metric = Metric(
        user_id=user_id,
        project_id=project_id,
        experiment_id=experiment_id,
        metric_name=metric_name,
        metric_value=metric_value,
        step=step,
        epoch=epoch,
        source_file_id=source_file_id,
    )
    db.add(metric)
    db.commit()
    db.refresh(metric)
    return metric


def get_metrics_for_experiment(db: Session, experiment_id: int) -> List[Dict[str, Any]]:
    rows = (
        db.query(Metric)
        .filter(Metric.experiment_id == experiment_id)
        .order_by(Metric.step)
        .all()
    )
    return [
        {
            "metric_name": r.metric_name,
            "metric_value": r.metric_value,
            "step": r.step,
            "epoch": r.epoch,
        }
        for r in rows
    ]
