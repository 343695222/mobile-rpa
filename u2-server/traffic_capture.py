"""TrafficCapture — 流量捕获管理器。

两种工作模式：
1. 内嵌模式：作为 mitmproxy addon 运行（需要 mitmproxy 进程）
2. 日志模式：读取 mitmproxy 导出的 HAR 文件（推荐先用这个）

捕获的流量保存为 JSON 格式，每个平台一个目录。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class TrafficRecord:
    """单条 HTTP 流量记录"""

    url: str
    method: str
    request_headers: dict
    request_body: str | None
    response_status: int
    response_headers: dict
    response_body: str | None  # 截断到 50KB
    content_type: str
    timestamp: str
    duration_ms: float

    @property
    def is_api(self) -> bool:
        ct = self.content_type.lower()
        return "json" in ct or (
            "text/plain" in ct
            and self.response_body is not None
            and self.response_body.strip().startswith("{")
        )

    @property
    def is_static(self) -> bool:
        ct = self.content_type.lower()
        return any(t in ct for t in ["image/", "css", "javascript", "font", "woff", "svg"])


class TrafficCapture:
    """流量捕获管理器。

    Usage::

        cap = TrafficCapture()
        cap.start_recording("聚宝猪", ["jubaozhu.com"])
        # ... mitmproxy addon 调用 cap.add_record(...)
        records = cap.stop_recording()
        cap.save_to_file()

    或者离线模式::

        cap = TrafficCapture()
        records = cap.load_from_har("traffic.har")
    """

    def __init__(self, data_dir: str | None = None) -> None:
        self._dir = Path(data_dir or "traffic_data")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._records: list[TrafficRecord] = []
        self._recording = False
        self._domain_filter: list[str] = []
        self._platform_name: str = ""

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def platform_name(self) -> str:
        return self._platform_name

    def start_recording(self, platform_name: str, domain_filter: list[str]) -> None:
        """开始录制流量。"""
        self._platform_name = platform_name
        self._domain_filter = [d.lower() for d in domain_filter]
        self._records = []
        self._recording = True
        logger.info("Traffic recording started for %s (filter: %s)", platform_name, domain_filter)

    def stop_recording(self) -> list[TrafficRecord]:
        """停止录制并返回所有记录。"""
        self._recording = False
        logger.info("Traffic recording stopped, %d records captured", len(self._records))
        return list(self._records)

    def add_record(self, record: TrafficRecord) -> bool:
        """添加一条流量记录（由 mitmproxy addon 或外部调用）。

        Returns True if the record was accepted (passed domain filter).
        """
        if not self._recording:
            return False
        if self._domain_filter:
            hostname = urlparse(record.url).hostname or ""
            if not any(f in hostname.lower() for f in self._domain_filter):
                return False
        self._records.append(record)
        return True

    def load_from_har(self, har_path: str) -> list[TrafficRecord]:
        """从 HAR 文件加载流量记录（离线分析模式）。"""
        path = Path(har_path)
        if not path.exists():
            raise FileNotFoundError(f"HAR file not found: {har_path}")

        with open(path, encoding="utf-8") as f:
            har = json.load(f)

        records: list[TrafficRecord] = []
        for entry in har.get("log", {}).get("entries", []):
            req = entry.get("request", {})
            resp = entry.get("response", {})
            content = resp.get("content", {})
            record = TrafficRecord(
                url=req.get("url", ""),
                method=req.get("method", "GET"),
                request_headers={h["name"]: h["value"] for h in req.get("headers", [])},
                request_body=req.get("postData", {}).get("text"),
                response_status=resp.get("status", 0),
                response_headers={h["name"]: h["value"] for h in resp.get("headers", [])},
                response_body=(content.get("text", "") or "")[:50000],
                content_type=content.get("mimeType", ""),
                timestamp=entry.get("startedDateTime", ""),
                duration_ms=entry.get("time", 0),
            )
            records.append(record)

        self._records = records
        self._platform_name = Path(har_path).stem
        logger.info("Loaded %d records from HAR file: %s", len(records), har_path)
        return records

    def save_to_file(self) -> str:
        """保存当前记录到 JSON 文件，返回文件路径。"""
        name = self._platform_name or "unknown"
        platform_dir = self._dir / name
        platform_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = platform_dir / f"traffic_{ts}.json"
        data = [asdict(r) for r in self._records]
        filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Saved %d records to %s", len(self._records), filepath)
        return str(filepath)

    def get_records(self) -> list[TrafficRecord]:
        """获取当前所有记录。"""
        return list(self._records)

    def get_stats(self) -> dict:
        """获取录制统计信息。"""
        return {
            "recording": self._recording,
            "platform": self._platform_name,
            "record_count": len(self._records),
            "domain_filter": self._domain_filter,
        }

    def clear(self) -> None:
        """清空所有记录。"""
        self._records = []
        self._recording = False
