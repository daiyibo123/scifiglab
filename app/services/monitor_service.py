"""Server monitoring service — CPU, memory, disk usage + alert checking."""

import psutil
import shutil
from pathlib import Path
from typing import Dict, List, Any

from app.core.config import DATA_DIR


def get_server_status() -> Dict[str, Any]:
    """Return current server resource usage."""
    # CPU
    cpu_percent = psutil.cpu_percent(interval=0.5)
    cpu_count = psutil.cpu_count()

    # Memory
    mem = psutil.virtual_memory()

    # Disk (partition containing DATA_DIR)
    disk = shutil.disk_usage(str(DATA_DIR))

    # Data directory size
    data_size = sum(f.stat().st_size for f in Path(DATA_DIR).rglob("*") if f.is_file())

    return {
        "cpu_percent": cpu_percent,
        "cpu_count": cpu_count,
        "memory_total_gb": round(mem.total / (1024 ** 3), 2),
        "memory_used_gb": round(mem.used / (1024 ** 3), 2),
        "memory_percent": mem.percent,
        "disk_total_gb": round(disk.total / (1024 ** 3), 2),
        "disk_used_gb": round(disk.used / (1024 ** 3), 2),
        "disk_free_gb": round(disk.free / (1024 ** 3), 2),
        "disk_percent": round(disk.used / disk.total * 100, 1),
        "data_dir_size_mb": round(data_size / (1024 ** 2), 2),
    }


# ── Alert level definitions ──

ALERT_LEVELS = {
    "info": "信息",
    "warning": "警告",
    "critical": "严重",
}


def check_alerts(status: Dict[str, Any], thresholds: Dict[str, float]) -> List[Dict[str, str]]:
    """Check server status against thresholds, return list of alert dicts.

    thresholds keys: cpu_warning, cpu_critical, mem_warning, mem_critical,
                     disk_warning, disk_critical
    """
    alerts = []

    cpu = status["cpu_percent"]
    mem = status["memory_percent"]
    disk = status["disk_percent"]

    cpu_crit = thresholds.get("cpu_critical", 95)
    cpu_warn = thresholds.get("cpu_warning", 80)
    mem_crit = thresholds.get("mem_critical", 95)
    mem_warn = thresholds.get("mem_warning", 80)
    disk_crit = thresholds.get("disk_critical", 95)
    disk_warn = thresholds.get("disk_warning", 80)

    if cpu >= cpu_crit:
        alerts.append({"level": "critical", "metric": "CPU", "message": f"CPU 使用率 {cpu}% 超过严重阈值 {cpu_crit}%"})
    elif cpu >= cpu_warn:
        alerts.append({"level": "warning", "metric": "CPU", "message": f"CPU 使用率 {cpu}% 超过警告阈值 {cpu_warn}%"})

    if mem >= mem_crit:
        alerts.append({"level": "critical", "metric": "内存", "message": f"内存使用率 {mem}% 超过严重阈值 {mem_crit}%"})
    elif mem >= mem_warn:
        alerts.append({"level": "warning", "metric": "内存", "message": f"内存使用率 {mem}% 超过警告阈值 {mem_warn}%"})

    if disk >= disk_crit:
        alerts.append({"level": "critical", "metric": "磁盘", "message": f"磁盘使用率 {disk}% 超过严重阈值 {disk_crit}%"})
    elif disk >= disk_warn:
        alerts.append({"level": "warning", "metric": "磁盘", "message": f"磁盘使用率 {disk}% 超过警告阈值 {disk_warn}%"})

    return alerts
