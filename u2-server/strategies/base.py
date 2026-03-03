"""BaseStrategy — 采集策略抽象基类。

所有采集策略（API 直连、RPA 剪贴板、RPA OCR）都继承此基类，
实现 explore（首次探索采集）和 execute（按已有脚本执行）两个方法。

返回格式统一为:
    {
        "success": bool,
        "items": [...],
        "strategy": "api" | "rpa_copy" | "rpa_ocr",
        "script_config": {...},   # explore 成功时提供，用于保存为脚本
        "error": str | None,
    }
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseStrategy(ABC):
    """采集策略抽象基类。"""

    # 子类必须设置策略名称
    strategy_name: str = ""

    @abstractmethod
    async def explore(
        self,
        device_id: str,
        app: str,
        data_type: str,
        query: str,
    ) -> dict[str, Any]:
        """首次探索采集：导航到目标页面，尝试采集数据。

        成功时返回 items 和 script_config（供保存为脚本）。
        """
        ...

    @abstractmethod
    async def execute(
        self,
        device_id: str,
        script: dict,
    ) -> dict[str, Any]:
        """按已保存脚本执行采集。"""
        ...

    # ── 辅助方法 ─────────────────────────────────────────────

    def _ok(
        self,
        items: list,
        script_config: dict | None = None,
    ) -> dict[str, Any]:
        """构造成功结果。"""
        result: dict[str, Any] = {
            "success": True,
            "items": items,
            "strategy": self.strategy_name,
        }
        if script_config is not None:
            result["script_config"] = script_config
        return result

    def _fail(self, error: str) -> dict[str, Any]:
        """构造失败结果。"""
        return {
            "success": False,
            "items": [],
            "strategy": self.strategy_name,
            "error": error,
        }
