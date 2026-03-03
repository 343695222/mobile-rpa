"""DataMapper — 数据标准化与对接。

将从不同平台采集的原始数据，通过配置式字段映射转换为统一格式，
然后推送到目标系统 API。

每个平台维护独立的映射配置文件（JSON）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DataMapper:
    """数据标准化与对接。

    Usage::

        mapper = DataMapper(config_dir="platform_configs")
        mapper.load_config("聚宝猪")

        # 转换数据
        raw = [{"auction_id": "123", "price": "1500.00", ...}]
        mapped = mapper.transform(raw)

        # 推送到目标系统
        result = await mapper.push(mapped, "https://my-system.com/api/import")
    """

    def __init__(self, config_dir: str = "platform_configs") -> None:
        self._config_dir = Path(config_dir)
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._config: dict[str, Any] = {}
        self._platform: str = ""

    @property
    def platform(self) -> str:
        return self._platform

    @property
    def config(self) -> dict[str, Any]:
        return dict(self._config)

    def load_config(self, platform_name: str) -> dict[str, Any]:
        """加载平台映射配置。"""
        self._platform = platform_name
        config_path = self._config_dir / f"{platform_name}.json"
        if config_path.exists():
            self._config = json.loads(config_path.read_text(encoding="utf-8"))
        else:
            self._config = self._default_config(platform_name)
            self.save_config()
        return dict(self._config)

    def save_config(self) -> str:
        """保存当前配置到文件。"""
        config_path = self._config_dir / f"{self._platform}.json"
        config_path.write_text(
            json.dumps(self._config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(config_path)

    def transform(self, raw_items: list[dict]) -> list[dict]:
        """按映射规则转换数据。"""
        field_map = self._config.get("field_mapping", {})
        type_map = self._config.get("type_conversions", {})
        result: list[dict] = []

        for item in raw_items:
            mapped: dict[str, Any] = {}
            for src_field, dst_field in field_map.items():
                value = self._get_nested(item, src_field)
                if value is not None:
                    value = self._convert_type(value, type_map.get(dst_field, "string"))
                    mapped[dst_field] = value
            # 添加元数据
            mapped["_source_platform"] = self._platform
            mapped["_mapped_at"] = datetime.now().isoformat()
            result.append(mapped)

        return result

    async def push(self, items: list[dict], target_url: str, headers: dict[str, str] | None = None) -> dict:
        """推送标准化数据到目标系统 API。"""
        import httpx

        push_headers = {"Content-Type": "application/json"}
        if headers:
            push_headers.update(headers)

        payload = {
            "platform": self._platform,
            "items": items,
            "count": len(items),
            "timestamp": datetime.now().isoformat(),
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(target_url, headers=push_headers, json=payload)
            return {
                "success": resp.status_code < 400,
                "status_code": resp.status_code,
                "response": resp.text[:1000],
            }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _get_nested(obj: dict, path: str) -> Any:
        """获取嵌套字段值，支持点号路径如 'data.auction.price'。"""
        keys = path.split(".")
        current = obj
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    @staticmethod
    def _convert_type(value: Any, target_type: str) -> Any:
        """类型转换。"""
        if value is None:
            return None
        try:
            if target_type == "int":
                return int(float(str(value)))
            elif target_type == "float":
                return float(str(value))
            elif target_type == "bool":
                return str(value).lower() in ("true", "1", "yes")
            elif target_type == "string":
                return str(value)
            elif target_type == "date":
                # 尝试常见日期格式
                for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y%m%d"):
                    try:
                        return datetime.strptime(str(value), fmt).strftime("%Y-%m-%d")
                    except ValueError:
                        continue
                return str(value)
        except (ValueError, TypeError):
            return str(value)
        return value

    @staticmethod
    def _default_config(platform_name: str) -> dict[str, Any]:
        """生成默认配置模板。"""
        return {
            "platform": platform_name,
            "description": f"{platform_name} 数据映射配置",
            "field_mapping": {
                # "源字段": "目标字段"
                # 示例：
                # "auction_id": "id",
                # "pig_count": "quantity",
                # "start_price": "price",
            },
            "type_conversions": {
                # "目标字段": "类型"
                # 支持: string, int, float, bool, date
            },
            "target_api": {
                "url": "",
                "headers": {},
            },
        }
