"""MidsceneStrategy — 基于 Midscene aiQuery 的数据采集策略。

利用 Midscene 的 aiQuery 能力直接从屏幕提取结构化数据，
替代 rpa_ocr_strategy 中手动截图 + GLM OCR + JSON 解析的流程。

优势：
- aiQuery 直接返回结构化 JSON，无需手动解析
- Midscene 内置翻页/滚动支持
- 更准确的视觉理解（Qwen3-VL）
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from midscene_bridge import MidsceneBridge

logger = logging.getLogger(__name__)


class NavigatorLike(Protocol):
    async def navigate_to(
        self, device_id: str, app: str, target_page: str
    ) -> dict: ...


class MidsceneStrategy:
    """Midscene aiQuery 采集策略。"""

    strategy_name = "midscene"

    def __init__(
        self,
        navigator: NavigatorLike,
        midscene: MidsceneBridge | None = None,
    ) -> None:
        self.navigator = navigator
        self.midscene = midscene or MidsceneBridge()

    async def explore(
        self,
        device_id: str,
        app: str,
        data_type: str,
        query: str,
    ) -> dict[str, Any]:
        """探索采集：导航 → Midscene aiQuery 提取数据。"""
        # 1. 导航到目标页面
        nav_result = await self.navigator.navigate_to(device_id, app, data_type)
        if not nav_result.get("success"):
            return self._fail(f"导航失败: {nav_result.get('error', '未知错误')}")

        # 2. 用 Midscene aiQuery 提取数据
        demand = self._build_data_demand(data_type, query)
        result = await self.midscene.ai_query(demand)

        if not result.get("success"):
            return self._fail(f"Midscene aiQuery 失败: {result.get('error', '')}")

        data = result.get("data")
        items = data if isinstance(data, list) else [data] if data else []

        if not items:
            return self._fail("Midscene aiQuery 未提取到数据")

        # 3. 构造脚本配置
        script_config = {
            "navigation": nav_result.get("steps", []),
            "extraction": {
                "type": "midscene",
                "config": {
                    "dataDemand": demand,
                },
            },
        }

        return self._ok(items, script_config)

    async def execute(
        self,
        device_id: str,
        script: dict,
    ) -> dict[str, Any]:
        """按已保存脚本执行：导航 → aiQuery。"""
        # 导航步骤由上层 collector 处理，这里直接提取
        extraction = script.get("extraction", {})
        config = extraction.get("config", {})
        demand = config.get("dataDemand", "")

        if not demand:
            return self._fail("脚本缺少 dataDemand 配置")

        result = await self.midscene.ai_query(demand)

        if not result.get("success"):
            return self._fail(f"Midscene aiQuery 失败: {result.get('error', '')}")

        data = result.get("data")
        items = data if isinstance(data, list) else [data] if data else []

        if not items:
            return self._fail("Midscene aiQuery 未提取到数据")

        return self._ok(items)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_data_demand(data_type: str, query: str) -> str:
        """构造 aiQuery 的 dataDemand 描述。"""
        base = f"提取屏幕上所有与'{data_type}'相关的数据，返回 JSON 数组，每个元素包含关键字段"
        if query:
            base += f"，筛选条件：{query}"
        return base

    def _ok(self, items: list, script_config: dict | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": True,
            "items": items,
            "strategy": self.strategy_name,
        }
        if script_config is not None:
            result["script_config"] = script_config
        return result

    def _fail(self, error: str) -> dict[str, Any]:
        return {
            "success": False,
            "items": [],
            "strategy": self.strategy_name,
            "error": error,
        }
