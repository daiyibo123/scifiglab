"""
SciFigLab — 自动解析服务

上传文件后自动检测格式、提取指标，并返回解析预览。
支持：CSV/TSV 列检测、日志模式识别、JSON 结构解析、配置文件提取。
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.database.models import Metric, UploadedFile
from app.services.log_parser import LogParser, normalize_name, parse_number, AXIS_KEYS
from app.services.metric_service import parse_csv_text, import_metrics_from_csv
from app.services.config_parser import parse_config_text, flatten_dict


# ═══════════════════════════════════════════════════════════════════════════
# Parse result structures
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ColumnInfo:
    """Single column detected in a tabular file."""
    name: str
    normalized: str
    dtype: str = "numeric"        # numeric | text | axis
    sample_values: list = field(default_factory=list)
    is_axis: bool = False
    is_metric: bool = False


@dataclass
class ParsePreview:
    """Preview of an auto-parsed file."""
    file_id: int = 0
    file_type: str = ""           # csv | tsv | log | json | config | unknown
    detected_format: str = ""     # human-readable format description
    columns: List[ColumnInfo] = field(default_factory=list)
    row_count: int = 0
    metric_names: List[str] = field(default_factory=list)
    axis_columns: List[str] = field(default_factory=list)
    sample_rows: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    auto_importable: bool = False  # can we auto-import metrics?
    config_keys: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ═══════════════════════════════════════════════════════════════════════════
# CSV / TSV preview
# ═══════════════════════════════════════════════════════════════════════════

def _preview_csv(text: str, ext: str = ".csv") -> ParsePreview:
    """Detect columns, axis, and metric candidates in CSV/TSV content."""
    preview = ParsePreview(file_type="csv" if ext == ".csv" else "tsv")

    delimiter = "\t" if ext == ".tsv" else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)

    if not rows:
        preview.warnings.append("文件为空")
        return preview

    raw_header = rows[0]
    data_rows = rows[1:]
    preview.row_count = len(data_rows)
    preview.detected_format = f"{'CSV' if ext == '.csv' else 'TSV'} 表格 ({len(raw_header)} 列, {len(data_rows)} 行)"

    for col_i, col_name in enumerate(raw_header):
        norm = normalize_name(col_name)
        is_axis = norm in AXIS_KEYS

        # Sample values (up to 5)
        samples = []
        numeric_count = 0
        for row in data_rows[:10]:
            if col_i < len(row):
                val = row[col_i].strip()
                if len(samples) < 5:
                    samples.append(val)
                if parse_number(val) is not None:
                    numeric_count += 1

        dtype = "axis" if is_axis else ("numeric" if numeric_count > len(data_rows[:10]) * 0.5 else "text")
        is_metric = dtype == "numeric" and not is_axis

        col = ColumnInfo(
            name=col_name.strip(),
            normalized=norm,
            dtype=dtype,
            sample_values=samples,
            is_axis=is_axis,
            is_metric=is_metric,
        )
        preview.columns.append(col)

        if is_axis:
            preview.axis_columns.append(norm)
        if is_metric and norm:
            preview.metric_names.append(norm)

    # Sample rows (up to 5)
    for row in data_rows[:5]:
        row_dict = {}
        for col_i, col_name in enumerate(raw_header):
            if col_i < len(row):
                row_dict[col_name.strip()] = row[col_i].strip()
        preview.sample_rows.append(row_dict)

    preview.auto_importable = bool(preview.metric_names)
    return preview


# ═══════════════════════════════════════════════════════════════════════════
# Log preview
# ═══════════════════════════════════════════════════════════════════════════

def _preview_log(text: str) -> ParsePreview:
    """Parse a log/txt file and preview detected metrics."""
    preview = ParsePreview(file_type="log")

    parser = LogParser()
    result = parser.parse_text(text)

    preview.row_count = result.line_count
    preview.metric_names = result.metric_names
    preview.detected_format = (
        f"日志文件 ({result.line_count} 行, "
        f"解析 {result.parsed_line_count} 行, "
        f"检测到 {len(result.metric_names)} 个指标)"
    )
    preview.warnings = result.warnings

    if result.epoch_min is not None:
        preview.axis_columns.append("epoch")
    if result.step_min is not None:
        preview.axis_columns.append("step")

    # Sample records as rows
    seen = set()
    for rec in result.records[:50]:
        key = rec.metric_name
        if key in seen:
            continue
        seen.add(key)
        preview.sample_rows.append({
            "metric": rec.metric_name,
            "value": rec.metric_value,
            "epoch": rec.epoch,
            "step": rec.step,
            "source": rec.source_type,
        })
        if len(preview.sample_rows) >= 10:
            break

    preview.auto_importable = bool(result.records)
    return preview


# ═══════════════════════════════════════════════════════════════════════════
# JSON preview
# ═══════════════════════════════════════════════════════════════════════════

def _preview_json(text: str) -> ParsePreview:
    """Preview JSON file structure."""
    preview = ParsePreview(file_type="json")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        preview.warnings.append(f"JSON 解析失败: {e}")
        return preview

    if isinstance(data, dict):
        flat = flatten_dict(data)
        preview.detected_format = f"JSON 对象 ({len(flat)} 个键)"
        preview.config_keys = list(flat.keys())[:30]

        # Check if it looks like metric data
        for k, v in flat.items():
            norm = normalize_name(k)
            if norm in AXIS_KEYS:
                preview.axis_columns.append(norm)
            elif parse_number(str(v)) is not None:
                preview.metric_names.append(norm)

        preview.sample_rows = [{k: v for k, v in list(flat.items())[:10]}]
        preview.auto_importable = False  # JSON configs aren't auto-imported as metrics

    elif isinstance(data, list):
        preview.detected_format = f"JSON 数组 ({len(data)} 条记录)"
        preview.row_count = len(data)

        # Check if it's an array of metric objects
        if data and isinstance(data[0], dict):
            sample_keys = list(data[0].keys())
            for k in sample_keys:
                norm = normalize_name(k)
                if norm in AXIS_KEYS:
                    preview.axis_columns.append(norm)
                else:
                    # Check first item
                    v = data[0].get(k)
                    if parse_number(str(v)) is not None:
                        preview.metric_names.append(norm)

            for item in data[:5]:
                preview.sample_rows.append(item)

            preview.auto_importable = bool(preview.metric_names)

    return preview


# ═══════════════════════════════════════════════════════════════════════════
# Config preview (YAML/YML)
# ═══════════════════════════════════════════════════════════════════════════

def _preview_config(text: str, ext: str) -> ParsePreview:
    """Preview config file (YAML/JSON)."""
    preview = ParsePreview(file_type="config")

    parsed, fmt = parse_config_text(text, ext.lstrip("."))
    if parsed is None:
        preview.warnings.append(f"无法解析 {ext} 配置文件")
        preview.detected_format = f"配置文件 ({ext})"
        return preview

    flat = flatten_dict(parsed)
    preview.detected_format = f"{fmt.upper()} 配置 ({len(flat)} 个参数)"
    preview.config_keys = sorted(flat.keys())[:50]
    preview.sample_rows = [{k: v for k, v in list(flat.items())[:15]}]
    preview.auto_importable = False
    return preview


# ═══════════════════════════════════════════════════════════════════════════
# Main dispatcher
# ═══════════════════════════════════════════════════════════════════════════

def detect_and_preview(content: bytes, ext: str, file_id: int = 0) -> ParsePreview:
    """
    Auto-detect file format and return a parse preview.

    Args:
        content: Raw file bytes (decrypted).
        ext: File extension (with dot, e.g. ".csv").
        file_id: Optional file ID for reference.

    Returns:
        ParsePreview with detected columns, metrics, and sample data.
    """
    # Decode text
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("gbk")
        except Exception:
            return ParsePreview(
                file_id=file_id,
                file_type="unknown",
                detected_format="无法解码",
                warnings=["文件无法解码为文本"],
            )

    ext = ext.lower()

    if ext in (".csv", ".tsv"):
        preview = _preview_csv(text, ext)
    elif ext in (".log", ".txt"):
        preview = _preview_log(text)
    elif ext == ".json":
        # Could be metrics array or config — check structure
        try:
            data = json.loads(text)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                preview = _preview_json(text)
            else:
                preview = _preview_config(text, ext)
        except json.JSONDecodeError:
            preview = _preview_config(text, ext)
    elif ext in (".yaml", ".yml"):
        preview = _preview_config(text, ext)
    else:
        preview = ParsePreview(
            file_type="binary",
            detected_format=f"二进制/不可解析 ({ext})",
            warnings=["该文件类型不支持自动解析预览"],
        )

    preview.file_id = file_id
    return preview


# ═══════════════════════════════════════════════════════════════════════════
# Auto-import after upload
# ═══════════════════════════════════════════════════════════════════════════

def auto_import_after_upload(
    db: Session,
    content: bytes,
    ext: str,
    user_id: int,
    project_id: int,
    experiment_id: int,
    source_file_id: int,
) -> Optional[Dict[str, Any]]:
    """
    Automatically import metrics from uploaded file if the format is recognized.

    Called right after a file is saved. Returns import summary dict or None.
    """
    # Decode
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("gbk")
        except Exception:
            return None

    ext = ext.lower()
    summary: Optional[Dict[str, Any]] = None

    # CSV / TSV — direct metric import
    if ext in (".csv", ".tsv"):
        if ext == ".tsv":
            # Convert TSV to CSV for the existing parser
            reader = csv.reader(io.StringIO(text), delimiter="\t")
            buf = io.StringIO()
            writer = csv.writer(buf)
            for row in reader:
                writer.writerow(row)
            text = buf.getvalue()

        result = import_metrics_from_csv(
            db=db,
            file_text=text,
            user_id=user_id,
            project_id=project_id,
            experiment_id=experiment_id,
            source_file_id=source_file_id,
            overwrite=False,
        )
        if result.imported_records_count > 0:
            summary = {
                "type": "metrics",
                "imported": result.imported_records_count,
                "metric_names": result.metric_names,
                "warnings": result.warnings,
            }

    # Log / TXT — parse and import
    elif ext in (".log", ".txt"):
        parser = LogParser()
        parse_result = parser.parse_text(text)
        if parse_result.records:
            existing = set()
            try:
                rows = db.query(Metric.metric_name, Metric.epoch, Metric.step).filter(
                    Metric.experiment_id == experiment_id,
                    Metric.source_file_id == source_file_id,
                ).all()
                existing = {(r.metric_name, r.epoch, r.step) for r in rows}
            except Exception:
                pass
            inserted = 0
            for rec in parse_result.records:
                key = (rec.metric_name, rec.epoch, rec.step)
                if key in existing:
                    continue
                existing.add(key)
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
            if inserted > 0:
                summary = {
                    "type": "log_metrics",
                    "imported": inserted,
                    "metric_names": parse_result.metric_names,
                    "warnings": parse_result.warnings,
                }

    # JSON / JSON Lines — parse and import
    elif ext == ".json":
        parser = LogParser()
        parse_result = parser.parse_text(text)
        if parse_result.records:
            existing = set()
            try:
                rows = db.query(Metric.metric_name, Metric.epoch, Metric.step).filter(
                    Metric.experiment_id == experiment_id,
                    Metric.source_file_id == source_file_id,
                ).all()
                existing = {(r.metric_name, r.epoch, r.step) for r in rows}
            except Exception:
                pass
            inserted = 0
            for rec in parse_result.records:
                key = (rec.metric_name, rec.epoch, rec.step)
                if key in existing:
                    continue
                existing.add(key)
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
            if inserted > 0:
                summary = {
                    "type": "json_metrics",
                    "imported": inserted,
                    "metric_names": parse_result.metric_names,
                    "warnings": parse_result.warnings,
                }

    return summary
