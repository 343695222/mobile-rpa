"""ApiScriptGenerator — 根据接口分析结果自动生成采集脚本。

根据难度等级选择不同的生成策略：
- Level 1: API 直连脚本（无鉴权）
- Level 2: API 直连脚本（需人工提供 Token/Cookie）
- Level 3-4: RPA 采集脚本（截图 OCR）

生成的脚本格式与 ScriptStore 完全兼容。
"""

from __future__ import annotations

import logging
from typing import Any

from script_store import ScriptStore
from traffic_analyzer import ApiEndpoint

logger = logging.getLogger(__name__)


class ApiScriptGenerator:
    """采集脚本生成器。"""

    def __init__(self, script_store: ScriptStore) -> None:
        self.store = script_store

    def generate(self, endpoint: ApiEndpoint, analysis: dict[str, Any]) -> dict:
        """根据难度等级选择生成方式。"""
        level = analysis.get("difficulty_level", 4)
        strategy = analysis.get("recommended_strategy", "rpa_ocr")

        if level == 1 and strategy == "api":
            return self.generate_api_script(endpoint, analysis)
        elif level <= 2:
            return self.generate_api_script_with_auth(endpoint, analysis)
        else:
            return self.generate_rpa_script(endpoint, analysis)

    def generate_api_script(self, endpoint: ApiEndpoint, analysis: dict[str, Any]) -> dict:
        """生成 API 直连脚本（Level 1，无鉴权）。"""
        return {
            "app": analysis.get("platform_name", "unknown"),
            "dataType": analysis.get("purpose", endpoint.url_pattern),
            "strategy": "api",
            "navigation": [],
            "extraction": {
                "type": "api",
                "config": {
                    "method": endpoint.method,
                    "url": f"{endpoint.base_url}{endpoint.url_pattern}",
                    "headers": {},
                    "params": endpoint.request_params,
                    "dataPath": self._guess_data_path(endpoint.response_schema),
                },
            },
        }

    def generate_api_script_with_auth(self, endpoint: ApiEndpoint, analysis: dict[str, Any]) -> dict:
        """生成需要鉴权的 API 脚本（Level 2）。"""
        script = self.generate_api_script(endpoint, analysis)
        script["extraction"]["config"]["headers"] = {
            h: "{{" + h + "}}" for h in endpoint.auth_headers
        }
        script["extraction"]["config"]["_auth_note"] = (
            f"需要人工提供以下 header 的值: {', '.join(endpoint.auth_headers)}"
        )
        script["extraction"]["config"]["_auth_type"] = endpoint.auth_type
        return script

    def generate_rpa_script(self, endpoint: ApiEndpoint, analysis: dict[str, Any]) -> dict:
        """生成 RPA 采集脚本（Level 3-4）。"""
        purpose = analysis.get("purpose", "数据")
        return {
            "app": analysis.get("platform_name", "unknown"),
            "dataType": analysis.get("purpose", endpoint.url_pattern),
            "strategy": "rpa_ocr",
            "navigation": [],  # 需要 Navigator 探索后填充
            "extraction": {
                "type": "ocr",
                "config": {
                    "maxPages": 3,
                    "swipeParams": {
                        "x1": 540, "y1": 1600,
                        "x2": 540, "y2": 400,
                        "duration": 0.5,
                    },
                    "extractPrompt": (
                        f"提取屏幕上所有与'{purpose}'相关的信息，"
                        f"以 JSON 数组格式返回"
                    ),
                },
            },
        }

    def save_to_store(self, script: dict) -> str:
        """保存脚本到 ScriptStore，返回 script_id。"""
        return self.store.save(
            app=script["app"],
            data_type=script["dataType"],
            strategy=script["strategy"],
            config=script,
        )

    @staticmethod
    def _guess_data_path(schema: dict) -> str:
        """猜测数据在响应 JSON 中的路径。"""
        if not schema:
            return ""
        # 常见模式：data.list, data.items, result.data, body.records
        for key in ("data", "result", "body"):
            if key in schema:
                sub = schema[key]
                if isinstance(sub, dict):
                    for sub_key in ("list", "items", "records", "rows"):
                        if sub_key in sub:
                            return f"{key}.{sub_key}"
                    if sub.get("_type") == "array":
                        return key
        return ""
