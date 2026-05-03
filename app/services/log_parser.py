"""
智能日志解析模块 — 多策略、可扩展的实验日志解析器。

支持格式：
  - key: value / key=value（冒号竖线、等号空格等）
  - JSON Lines
  - CSV / TSV / 空格分隔表格
  - tqdm 进度条
  - YOLO / Ultralytics 表头 + 数据行
  - 带时间戳日志
  - Epoch/Step/Iter 上下文

设计要点：
  - 每种格式由独立策略函数处理，互不干扰
  - 解析不到的行安静跳过
  - 名称归一化、数值清洗统一处理
  - 预留 CustomParseRule 接口供后续扩展
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


# ═══════════════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class MetricRecord:
    """单条解析出的指标记录。"""
    epoch: Optional[int] = None
    step: Optional[int] = None
    metric_name: str = ""
    metric_value: float = 0.0
    raw_line: Optional[str] = None
    source_type: str = ""          # json / kv / tqdm / table / csv / custom


@dataclass
class ParseResult:
    """整个文件的解析结果。"""
    records: List[MetricRecord] = field(default_factory=list)
    metric_names: List[str] = field(default_factory=list)
    epoch_min: Optional[int] = None
    epoch_max: Optional[int] = None
    step_min: Optional[int] = None
    step_max: Optional[int] = None
    line_count: int = 0
    parsed_line_count: int = 0
    skipped_line_count: int = 0
    warnings: List[str] = field(default_factory=list)


@dataclass
class _Context:
    """行间上下文，维护当前 epoch / step / iter。"""
    epoch: Optional[int] = None
    step: Optional[int] = None


# ═══════════════════════════════════════════════════════════════════════════
# 自定义解析规则接口（预留）
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class CustomParseRule:
    """
    用户自定义解析规则（第一版预留接口，暂不在页面暴露）。

    Attributes:
        epoch_pattern:  用于提取 epoch 的正则，group(1) 为数值
        step_pattern:   用于提取 step 的正则，group(1) 为数值
        metric_pattern: 用于提取指标的正则，group(1)=name, group(2)=value
    """
    epoch_pattern: Optional[str] = None
    step_pattern: Optional[str] = None
    metric_pattern: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# 横轴字段集合 — 这些字段作为行索引而非普通指标
# ═══════════════════════════════════════════════════════════════════════════

AXIS_KEYS = {"epoch", "step", "iter", "iteration", "batch", "time"}


# ═══════════════════════════════════════════════════════════════════════════
# 名称归一化
# ═══════════════════════════════════════════════════════════════════════════

_NAME_ALIAS: Dict[str, str] = {
    "learning_rate": "lr",
    "validation_loss": "val_loss",
}

# 匹配非字母、数字、下划线的字符（用于清洗指标名）
_RE_NON_IDENT = re.compile(r"[^a-zA-Z0-9_]+")
_RE_MULTI_UNDERSCORE = re.compile(r"_{2,}")


def normalize_name(raw: str) -> str:
    """
    指标名称归一化：
    1. 转小写  2. 去首尾空格  3. / . - → _
    4. 去特殊符号  5. 多 _ 合一  6. 别名替换
    """
    s = raw.strip().lower()
    s = s.replace("/", "_").replace(".", "_").replace("-", "_")
    s = _RE_NON_IDENT.sub("", s)
    s = _RE_MULTI_UNDERSCORE.sub("_", s).strip("_")
    return _NAME_ALIAS.get(s, s)


# ═══════════════════════════════════════════════════════════════════════════
# 数值解析
# ═══════════════════════════════════════════════════════════════════════════

# 匹配浮点 / 整数 / 科学计数法，可带尾缀（G, M, K, %）
_RE_NUMBER = re.compile(
    r"^([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|[+-]?\.\d+(?:[eE][+-]?\d+)?)"
    r"([GMK%]?)$",
    re.IGNORECASE,
)


def parse_number(raw: str) -> Optional[float]:
    """
    解析数值字符串。

    - 科学计数法：1e-4, 2E-5
    - 带后缀：3.21G → 3.21, 88% → 88（保存原始百分比数值）
    - nan / inf → 返回 None（不保存）
    """
    s = raw.strip()
    low = s.lower()
    if low in ("nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity", "none", "n/a", "null", ""):
        return None

    m = _RE_NUMBER.match(s)
    if m is None:
        return None

    val = float(m.group(1))
    # nan / inf 可能从 float() 产生
    if math.isnan(val) or math.isinf(val):
        return None
    return val


# ═══════════════════════════════════════════════════════════════════════════
# Epoch / Step / Iter 提取（上下文）
# ═══════════════════════════════════════════════════════════════════════════

# Epoch: 1, Epoch 1, epoch=1, epoch: 1, [Epoch 1], Epoch [1/100], Epoch: 1/100
_RE_EPOCH = re.compile(
    r"(?:^|[\[\s])epoch[\s:=\[]*(\d+)(?:\s*/\s*\d+)?",
    re.IGNORECASE,
)
# Step: 100, Step 100, step=100, [Step 100]
_RE_STEP = re.compile(
    r"(?:^|[\[\s])step[\s:=\[]*(\d+)(?:\s*/\s*\d+)?",
    re.IGNORECASE,
)
# Iter: 200, Iteration 200, iter=200, Iter [50/1000]
_RE_ITER = re.compile(
    r"(?:^|[\[\s])(?:iter(?:ation)?)[\s:=\[]*(\d+)(?:\s*/\s*\d+)?",
    re.IGNORECASE,
)
# batch=50
_RE_BATCH = re.compile(
    r"(?:^|[\[\s])batch[\s:=]*(\d+)",
    re.IGNORECASE,
)


def _extract_axis(line: str) -> Tuple[Optional[int], Optional[int]]:
    """从一行中提取 (epoch, step)。step 优先级：step > iter > batch。"""
    epoch = None
    step = None

    m = _RE_EPOCH.search(line)
    if m:
        epoch = int(m.group(1))

    m = _RE_STEP.search(line)
    if m:
        step = int(m.group(1))
    else:
        m = _RE_ITER.search(line)
        if m:
            step = int(m.group(1))
        else:
            m = _RE_BATCH.search(line)
            if m:
                step = int(m.group(1))

    return epoch, step


# ═══════════════════════════════════════════════════════════════════════════
# 策略 1：JSON Line
# ═══════════════════════════════════════════════════════════════════════════

def _parse_json_line(line: str) -> Optional[List[Tuple[str, float, Optional[int], Optional[int]]]]:
    """
    尝试将一行解析为 JSON 对象。
    返回 [(name, value, epoch, step), ...] 或 None。
    """
    stripped = line.strip()
    if not stripped.startswith("{"):
        return None
    try:
        obj = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None

    epoch = None
    step = None
    metrics: List[Tuple[str, float, Optional[int], Optional[int]]] = []

    # 先提取横轴
    for k, v in obj.items():
        nk = normalize_name(k)
        if nk in AXIS_KEYS:
            try:
                iv = int(v)
            except (ValueError, TypeError):
                continue
            if nk == "epoch":
                epoch = iv
            elif nk in ("step", "iter", "iteration", "batch"):
                step = iv
            # time 暂存为 step 如果没有 step
            elif nk == "time" and step is None:
                step = iv

    # 提取指标
    for k, v in obj.items():
        nk = normalize_name(k)
        if not nk or nk in AXIS_KEYS:
            continue
        val = parse_number(str(v))
        if val is not None:
            metrics.append((nk, val, epoch, step))

    return metrics if metrics else None


# ═══════════════════════════════════════════════════════════════════════════
# 策略 2：key=value / key: value
# ═══════════════════════════════════════════════════════════════════════════

# 匹配 key=value 或 key: value，支持 train/loss、val.loss 等
_RE_KV = re.compile(
    r"([a-zA-Z_][a-zA-Z0-9_./-]*)"         # key
    r"\s*[:=]\s*"                           # separator
    r"([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?" # number part
    r"(?:[GMK%])?)"                         # optional suffix
)


def _parse_kv_pairs(line: str) -> List[Tuple[str, float]]:
    """从一行提取所有 key=value / key: value 对。"""
    results = []
    for m in _RE_KV.finditer(line):
        raw_name = m.group(1)
        raw_val = m.group(2)
        name = normalize_name(raw_name)
        if not name:
            continue
        val = parse_number(raw_val)
        if val is not None:
            results.append((name, val))
    return results


# ═══════════════════════════════════════════════════════════════════════════
# 策略 3：tqdm 进度条
# ═══════════════════════════════════════════════════════════════════════════

# 进度条特征：包含 |███ 或 nn%| 或 [nn:nn<nn:nn]
_RE_TQDM_DETECT = re.compile(r"\d+%\|.*\||\|[█▉▊▋▌▍▎▏\s]+\|")
# postfix 区域在最后一个 ], 之后或 , 分隔的 key=value
_RE_TQDM_POSTFIX = re.compile(
    r"([a-zA-Z_][a-zA-Z0-9_./-]*)\s*=\s*"
    r"([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?(?:[GMK%])?)"
)
# 进度 500/1000 形式
_RE_TQDM_PROGRESS = re.compile(r"(\d+)/(\d+)")


def _parse_tqdm_line(line: str) -> Optional[List[Tuple[str, float]]]:
    """解析 tqdm 进度条行的 postfix 指标。"""
    if not _RE_TQDM_DETECT.search(line):
        return None

    results = []
    for m in _RE_TQDM_POSTFIX.finditer(line):
        name = normalize_name(m.group(1))
        if not name:
            continue
        val = parse_number(m.group(2))
        if val is not None:
            results.append((name, val))

    return results if results else None


# ═══════════════════════════════════════════════════════════════════════════
# 策略 4 & 5：表格 / CSV 块解析
# ═══════════════════════════════════════════════════════════════════════════

def _looks_like_header(tokens: List[str]) -> bool:
    """判断一行分词后是否像表头（大多数 token 是标识符且不含 : =）。"""
    if len(tokens) < 2:
        return False
    # 表头 token 应该是标识符风格（字母开头），且不含 : 或 =
    _re_ident = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_./%-]*$')
    ident_count = sum(
        1 for t in tokens
        if _re_ident.match(t) and ':' not in t and '=' not in t
    )
    # 要求严格多数（> 50%）且第一个 token 也是标识符
    first_ok = bool(_re_ident.match(tokens[0])) and ':' not in tokens[0] and '=' not in tokens[0]
    return first_ok and ident_count > len(tokens) * 0.5


def _detect_table_blocks(lines: List[str]) -> List[Tuple[List[str], List[List[str]], str, int]]:
    """
    扫描所有行，检测 CSV 或空格 / tab 分隔的表格块。

    返回 [(header_tokens, data_rows_tokens, source_type, header_line_idx), ...]
    """
    blocks: List[Tuple[List[str], List[List[str]], str, int]] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # CSV 检测：包含逗号且分割后像表头
        if "," in line:
            tokens = [t.strip() for t in line.split(",")]
            if _looks_like_header(tokens):
                header = tokens
                data_rows: List[List[str]] = []
                j = i + 1
                while j < n:
                    dl = lines[j].strip()
                    if not dl:
                        break
                    dt = [t.strip() for t in dl.split(",")]
                    if len(dt) != len(header):
                        break
                    # 至少有一个数值
                    if any(parse_number(t) is not None for t in dt):
                        data_rows.append(dt)
                        j += 1
                    else:
                        break
                if data_rows:
                    blocks.append((header, data_rows, "csv", i))
                    i = j
                    continue

        # 空格 / tab 分隔（跳过包含 | 或多 : 分隔符的行，那些由 KV 策略处理）
        if "|" not in line and line.count(":") <= 1:
            tokens = line.split()
            if _looks_like_header(tokens) and len(tokens) >= 2:
                header = tokens
                data_rows = []
                j = i + 1
                while j < n:
                    dl = lines[j].strip()
                    if not dl or "|" in dl:
                        break
                    dt = dl.split()
                    if len(dt) != len(header):
                        break
                    if any(parse_number(t) is not None for t in dt):
                        data_rows.append(dt)
                        j += 1
                    else:
                        break
                if data_rows:
                    blocks.append((header, data_rows, "table", i))
                    i = j
                    continue

        i += 1
    return blocks


# ═══════════════════════════════════════════════════════════════════════════
# 策略 6：自定义规则解析（预留接口）
# ═══════════════════════════════════════════════════════════════════════════

def _apply_custom_rules(
    line: str,
    rules: Optional[CustomParseRule],
) -> Tuple[Optional[int], Optional[int], List[Tuple[str, float]]]:
    """应用用户自定义正则提取。返回 (epoch, step, [(name, value)])。"""
    if rules is None:
        return None, None, []

    epoch = None
    step = None
    metrics: List[Tuple[str, float]] = []

    if rules.epoch_pattern:
        m = re.search(rules.epoch_pattern, line)
        if m:
            try:
                epoch = int(m.group(1))
            except (ValueError, IndexError):
                pass

    if rules.step_pattern:
        m = re.search(rules.step_pattern, line)
        if m:
            try:
                step = int(m.group(1))
            except (ValueError, IndexError):
                pass

    if rules.metric_pattern:
        for m in re.finditer(rules.metric_pattern, line):
            try:
                name = normalize_name(m.group(1))
                val = parse_number(m.group(2))
                if name and val is not None:
                    metrics.append((name, val))
            except (IndexError, ValueError):
                pass

    return epoch, step, metrics


# ═══════════════════════════════════════════════════════════════════════════
# 时间戳剥离
# ═══════════════════════════════════════════════════════════════════════════

# 匹配行首时间戳，如 2026-05-03 12:30:01 或 [2026-05-03 12:30:01]
_RE_TIMESTAMP_PREFIX = re.compile(
    r"^\[?\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}\]?\s*[-–—]?\s*"
)


def _strip_timestamp(line: str) -> str:
    """去掉行首时间戳。"""
    return _RE_TIMESTAMP_PREFIX.sub("", line)


# ═══════════════════════════════════════════════════════════════════════════
# 主解析器
# ═══════════════════════════════════════════════════════════════════════════

class LogParser:
    """
    多策略日志解析器。

    使用方法：
        parser = LogParser()
        result = parser.parse_file("train.log")
        result = parser.parse_text(log_string)

    可通过 custom_rules 注入自定义正则（预留接口）。
    """

    def __init__(self, custom_rules: Optional[CustomParseRule] = None):
        self.custom_rules = custom_rules

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def parse_file(self, file_path: str) -> ParseResult:
        """解析日志文件。"""
        path = Path(file_path)
        text = path.read_text(encoding="utf-8", errors="replace")
        return self.parse_text(text)

    def parse_text(self, text: str) -> ParseResult:
        """解析日志文本。"""
        lines = text.splitlines() if text else []
        result = ParseResult(line_count=len(lines))
        ctx = _Context()

        # ── 阶段 1：检测表格 / CSV 块 ────────────────────────────
        table_blocks = _detect_table_blocks(lines)
        table_line_set: set[int] = set()  # 标记已由表格策略处理的行号
        for header, data_rows, src_type, header_idx in table_blocks:
            table_line_set.add(header_idx)
            norm_header = [normalize_name(h) for h in header]
            for row_offset, row in enumerate(data_rows):
                line_idx = header_idx + 1 + row_offset
                table_line_set.add(line_idx)

                # 从行中提取 epoch / step
                row_epoch: Optional[int] = None
                row_step: Optional[int] = None
                for col_i, (col_name, cell) in enumerate(zip(norm_header, row)):
                    if col_name == "epoch":
                        # 支持 1/100 格式
                        val_str = cell.split("/")[0]
                        try:
                            row_epoch = int(val_str)
                        except ValueError:
                            pass
                    elif col_name in ("step", "iter", "iteration", "batch", "time"):
                        val_str = cell.split("/")[0]
                        try:
                            row_step = int(val_str)
                        except ValueError:
                            pass

                if row_epoch is not None:
                    ctx.epoch = row_epoch
                if row_step is not None:
                    ctx.step = row_step

                for col_i, (col_name, cell) in enumerate(zip(norm_header, row)):
                    if not col_name or col_name in AXIS_KEYS:
                        continue
                    val = parse_number(cell)
                    if val is not None:
                        result.records.append(MetricRecord(
                            epoch=row_epoch if row_epoch is not None else ctx.epoch,
                            step=row_step if row_step is not None else ctx.step,
                            metric_name=col_name,
                            metric_value=val,
                            raw_line=lines[line_idx] if line_idx < len(lines) else None,
                            source_type=src_type,
                        ))

                result.parsed_line_count += 1

        # ── 阶段 2：逐行解析（跳过已处理的表格行）──────────────
        for i, raw_line in enumerate(lines):
            if i in table_line_set:
                continue

            line = raw_line.strip()
            if not line:
                result.skipped_line_count += 1
                continue

            parsed = False

            # 去时间戳
            clean_line = _strip_timestamp(line)

            # 提取本行 epoch / step（更新上下文）
            line_epoch, line_step = _extract_axis(clean_line)
            if line_epoch is not None:
                ctx.epoch = line_epoch
            if line_step is not None:
                ctx.step = line_step

            # ── 自定义规则（优先）──
            if self.custom_rules:
                c_epoch, c_step, c_metrics = _apply_custom_rules(clean_line, self.custom_rules)
                if c_epoch is not None:
                    ctx.epoch = c_epoch
                    line_epoch = c_epoch
                if c_step is not None:
                    ctx.step = c_step
                    line_step = c_step
                if c_metrics:
                    for name, val in c_metrics:
                        if name not in AXIS_KEYS:
                            result.records.append(MetricRecord(
                                epoch=line_epoch if line_epoch is not None else ctx.epoch,
                                step=line_step if line_step is not None else ctx.step,
                                metric_name=name,
                                metric_value=val,
                                raw_line=raw_line,
                                source_type="custom",
                            ))
                    parsed = True

            # ── JSON Line ──
            if not parsed:
                json_metrics = _parse_json_line(clean_line)
                if json_metrics:
                    for name, val, j_epoch, j_step in json_metrics:
                        e = j_epoch if j_epoch is not None else (line_epoch if line_epoch is not None else ctx.epoch)
                        s = j_step if j_step is not None else (line_step if line_step is not None else ctx.step)
                        if j_epoch is not None:
                            ctx.epoch = j_epoch
                        if j_step is not None:
                            ctx.step = j_step
                        result.records.append(MetricRecord(
                            epoch=e, step=s,
                            metric_name=name, metric_value=val,
                            raw_line=raw_line, source_type="json",
                        ))
                    parsed = True

            # ── tqdm 进度条 ──
            if not parsed:
                tqdm_metrics = _parse_tqdm_line(clean_line)
                if tqdm_metrics:
                    for name, val in tqdm_metrics:
                        if name not in AXIS_KEYS:
                            result.records.append(MetricRecord(
                                epoch=line_epoch if line_epoch is not None else ctx.epoch,
                                step=line_step if line_step is not None else ctx.step,
                                metric_name=name, metric_value=val,
                                raw_line=raw_line, source_type="tqdm",
                            ))
                    parsed = True

            # ── key=value / key: value ──
            if not parsed:
                kv_pairs = _parse_kv_pairs(clean_line)
                # 过滤掉横轴
                metric_pairs = [(n, v) for n, v in kv_pairs if n not in AXIS_KEYS]
                if metric_pairs:
                    for name, val in metric_pairs:
                        result.records.append(MetricRecord(
                            epoch=line_epoch if line_epoch is not None else ctx.epoch,
                            step=line_step if line_step is not None else ctx.step,
                            metric_name=name, metric_value=val,
                            raw_line=raw_line, source_type="kv",
                        ))
                    parsed = True

            if parsed:
                result.parsed_line_count += 1
            else:
                result.skipped_line_count += 1

        # ── 汇总 ──────────────────────────────────────────────────
        self._finalize(result)
        return result

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _finalize(result: ParseResult) -> None:
        """计算汇总信息。"""
        names_seen: set[str] = set()
        epochs: List[int] = []
        steps: List[int] = []

        for r in result.records:
            names_seen.add(r.metric_name)
            if r.epoch is not None:
                epochs.append(r.epoch)
            if r.step is not None:
                steps.append(r.step)

        result.metric_names = sorted(names_seen)
        if epochs:
            result.epoch_min = min(epochs)
            result.epoch_max = max(epochs)
        if steps:
            result.step_min = min(steps)
            result.step_max = max(steps)
