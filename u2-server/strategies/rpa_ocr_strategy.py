"""RpaOcrStrategy — RPA + 截图 OCR 采集策略。

流程：导航到目标页面 → 截图 → GLM-4.6V OCR 提取 → 翻页 → 重复 → 合并。
兜底策略，适用于任何可视内容，但速度较慢（依赖 GLM API）。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol


class NavigatorLike(Protocol):
    """Navigator 接口协议（Task 6.2 实现）。"""

    async def navigate_to(
        self, device_id: str, app: str, target_page: str
    ) -> dict: ...


# 默认翻页滑动参数
_DEFAULT_SWIPE = {
    "x1": 540,
    "y1": 1600,
    "x2": 540,
    "y2": 400,
    "duration": 0.5,
}

# 默认最大翻页数
_DEFAULT_MAX_PAGES = 3

# 翻页后等待时间（秒）
_WAIT_AFTER_SWIPE = 1.0


class RpaOcrStrategy:
    """RPA + OCR 策略：导航 → 截图 → GLM OCR → 翻页 → 合并。"""

    strategy_name = "rpa_ocr"

    def __init__(
        self,
        device_manager: Any,
        navigator: NavigatorLike,
        vision_client: Any,
    ) -> None:
        self.device_mgr = device_manager
        self.navigator = navigator
        self.vision = vision_client

    async def explore(
        self,
        device_id: str,
        app: str,
        data_type: str,
        query: str,
    ) -> dict[str, Any]:
        """探索采集：导航到页面，截图 OCR 提取数据，翻页重复。"""
        # 1. 导航到目标页面
        nav_result = await self.navigator.navigate_to(device_id, app, data_type)
        if not nav_result.get("success"):
            return self._fail(
                f"导航失败: {nav_result.get('error', '未知错误')}"
            )

        # 2. 多页截图 + OCR
        prompt = self._build_extract_prompt(data_type, query)
        all_items = await self._ocr_pages(
            device_id,
            prompt=prompt,
            max_pages=_DEFAULT_MAX_PAGES,
            swipe_params=_DEFAULT_SWIPE,
        )

        if not all_items:
            return self._fail("OCR 未能提取到任何数据")

        # 3. 构造脚本配置
        script_config = {
            "navigation": nav_result.get("steps", []),
            "extraction": {
                "type": "ocr",
                "config": {
                    "maxPages": _DEFAULT_MAX_PAGES,
                    "swipeParams": _DEFAULT_SWIPE,
                    "extractPrompt": prompt,
                },
            },
        }

        return self._ok(all_items, script_config)

    async def execute(
        self,
        device_id: str,
        script: dict,
    ) -> dict[str, Any]:
        """按已保存脚本执行：先导航，再按配置 OCR 提取。"""
        # 1. 执行导航步骤
        nav_steps = script.get("navigation", [])
        if nav_steps:
            await self._execute_nav_steps(device_id, nav_steps)

        # 2. 按脚本配置执行 OCR
        extraction = script.get("extraction", {})
        config = extraction.get("config", {})

        max_pages = config.get("maxPages", _DEFAULT_MAX_PAGES)
        swipe_params = config.get("swipeParams", _DEFAULT_SWIPE)
        prompt = config.get("extractPrompt", "")

        if not prompt:
            prompt = "请提取屏幕上所有数据，以 JSON 数组格式返回"

        all_items = await self._ocr_pages(
            device_id,
            prompt=prompt,
            max_pages=max_pages,
            swipe_params=swipe_params,
        )

        if not all_items:
            return self._fail("OCR 脚本执行未能提取到数据")

        return self._ok(all_items)

    # ── 内部方法 ─────────────────────────────────────────────

    async def _ocr_pages(
        self,
        device_id: str,
        prompt: str,
        max_pages: int,
        swipe_params: dict,
    ) -> list:
        """多页截图 + OCR 提取，返回合并后的数据列表。"""
        all_items: list = []

        for page in range(max_pages):
            # 截图
            screenshot_b64 = self.device_mgr.screenshot_base64(device_id)

            # GLM OCR 分析
            result = await self.vision.analyze(screenshot_b64, prompt)
            if result.get("success"):
                items = _parse_items_from_text(result.get("description", ""))
                all_items.extend(items)

            # 非最后一页时翻页
            if page < max_pages - 1:
                self.device_mgr.swipe(
                    device_id,
                    swipe_params.get("x1", 540),
                    swipe_params.get("y1", 1600),
                    swipe_params.get("x2", 540),
                    swipe_params.get("y2", 400),
                    swipe_params.get("duration", 0.5),
                )
                await asyncio.sleep(_WAIT_AFTER_SWIPE)

        return all_items

    async def _execute_nav_steps(
        self, device_id: str, steps: list[dict]
    ) -> None:
        """按顺序执行导航步骤。"""
        for step in sorted(steps, key=lambda s: s.get("order", 0)):
            action = step.get("action", {})
            action_type = action.get("type", "")

            if action_type == "click":
                self.device_mgr.click(
                    device_id, action.get("x", 0), action.get("y", 0)
                )
            elif action_type == "click_element":
                selector = action.get("selector", {})
                self.device_mgr.click_element(
                    device_id, selector.get("by", "text"), selector.get("value", "")
                )
            elif action_type == "swipe":
                self.device_mgr.swipe(
                    device_id,
                    action.get("x1", 0),
                    action.get("y1", 0),
                    action.get("x2", 0),
                    action.get("y2", 0),
                    action.get("duration", 0.5),
                )
            elif action_type == "input_text":
                self.device_mgr.input_text(device_id, action.get("text", ""))
            elif action_type == "wait":
                await asyncio.sleep(action.get("duration", 1.0))

            await asyncio.sleep(0.5)

    @staticmethod
    def _build_extract_prompt(data_type: str, query: str) -> str:
        """构造 GLM OCR 提取 prompt。"""
        base = f"请提取屏幕上所有与'{data_type}'相关的数据，以 JSON 数组格式返回"
        if query:
            base += f"，筛选条件：{query}"
        return base

    # ── 结果构造 ─────────────────────────────────────────────

    def _ok(
        self,
        items: list,
        script_config: dict | None = None,
    ) -> dict[str, Any]:
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


def _parse_items_from_text(text: str) -> list:
    """尝试从 GLM 返回的文本中解析 JSON 数组。

    GLM 可能返回纯 JSON，也可能包裹在 markdown 代码块中。
    """
    text = text.strip()

    # 尝试提取 markdown 代码块中的 JSON
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                parsed = json.loads(part)
                if isinstance(parsed, list):
                    return parsed
                return [parsed]
            except (json.JSONDecodeError, ValueError):
                continue

    # 直接尝试解析
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        return [parsed]
    except (json.JSONDecodeError, ValueError):
        pass

    # 无法解析为 JSON，作为纯文本返回
    if text:
        return [{"text": text}]
    return []
