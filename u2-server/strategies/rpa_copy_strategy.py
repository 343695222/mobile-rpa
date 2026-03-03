"""RpaCopyStrategy — RPA + 剪贴板复制采集策略。

流程：导航到目标页面 → 长按 → 全选 → 复制 → 读取剪贴板。
适用于文本内容较多的页面（如联系人列表、聊天记录等）。
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol


class NavigatorLike(Protocol):
    """Navigator 接口协议（Task 6.2 实现）。"""

    async def navigate_to(
        self, device_id: str, app: str, target_page: str
    ) -> dict: ...


class RpaCopyStrategy:
    """RPA + 剪贴板策略：导航 → 长按全选复制 → 读剪贴板。"""

    strategy_name = "rpa_copy"

    # 默认长按坐标（屏幕中心偏上）
    _DEFAULT_LONG_PRESS_X = 540
    _DEFAULT_LONG_PRESS_Y = 960

    # 文本按钮匹配
    _SELECT_ALL_TEXT = "全选"
    _COPY_TEXT = "复制"

    # 等待时间（秒）
    _WAIT_AFTER_LONG_PRESS = 0.5
    _WAIT_AFTER_CLICK = 0.3

    def __init__(self, device_manager: Any, navigator: NavigatorLike) -> None:
        self.device_mgr = device_manager
        self.navigator = navigator

    async def explore(
        self,
        device_id: str,
        app: str,
        data_type: str,
        query: str,
    ) -> dict[str, Any]:
        """探索采集：导航到页面，尝试长按→全选→复制→读剪贴板。"""
        # 1. 导航到目标页面
        nav_result = await self.navigator.navigate_to(device_id, app, data_type)
        if not nav_result.get("success"):
            return self._fail(
                f"导航失败: {nav_result.get('error', '未知错误')}"
            )

        # 2. 尝试复制
        text = await self._try_copy(device_id)
        if not text:
            return self._fail("长按复制失败：未能获取剪贴板内容")

        # 3. 构造脚本配置供保存
        script_config = {
            "navigation": nav_result.get("steps", []),
            "extraction": {
                "type": "clipboard",
                "config": {
                    "longPressX": self._DEFAULT_LONG_PRESS_X,
                    "longPressY": self._DEFAULT_LONG_PRESS_Y,
                    "selectAllText": self._SELECT_ALL_TEXT,
                    "copyText": self._COPY_TEXT,
                },
            },
        }

        return self._ok([{"text": text}], script_config)

    async def execute(
        self,
        device_id: str,
        script: dict,
    ) -> dict[str, Any]:
        """按已保存脚本执行：先执行导航步骤，再按配置复制。"""
        # 1. 执行导航步骤
        nav_steps = script.get("navigation", [])
        if nav_steps:
            await self._execute_nav_steps(device_id, nav_steps)

        # 2. 按脚本配置执行复制
        extraction = script.get("extraction", {})
        config = extraction.get("config", {})

        lp_x = config.get("longPressX", self._DEFAULT_LONG_PRESS_X)
        lp_y = config.get("longPressY", self._DEFAULT_LONG_PRESS_Y)
        select_all = config.get("selectAllText", self._SELECT_ALL_TEXT)
        copy_text = config.get("copyText", self._COPY_TEXT)

        text = await self._try_copy(
            device_id,
            long_press_x=lp_x,
            long_press_y=lp_y,
            select_all_text=select_all,
            copy_text=copy_text,
        )
        if not text:
            return self._fail("脚本执行复制失败：未能获取剪贴板内容")

        return self._ok([{"text": text}])

    # ── 内部方法 ─────────────────────────────────────────────

    async def _try_copy(
        self,
        device_id: str,
        long_press_x: int | None = None,
        long_press_y: int | None = None,
        select_all_text: str | None = None,
        copy_text: str | None = None,
    ) -> str:
        """执行长按→全选→复制→读剪贴板流程，返回剪贴板文本。"""
        lp_x = long_press_x or self._DEFAULT_LONG_PRESS_X
        lp_y = long_press_y or self._DEFAULT_LONG_PRESS_Y
        sa_text = select_all_text or self._SELECT_ALL_TEXT
        cp_text = copy_text or self._COPY_TEXT

        dev = self.device_mgr.get_device(device_id)

        # 长按
        dev.long_click(lp_x, lp_y)
        await asyncio.sleep(self._WAIT_AFTER_LONG_PRESS)

        # 尝试点击"全选"
        select_el = dev(text=sa_text)
        if select_el.exists(timeout=2):
            select_el.click()
            await asyncio.sleep(self._WAIT_AFTER_CLICK)

        # 尝试点击"复制"
        copy_el = dev(text=cp_text)
        if copy_el.exists(timeout=2):
            copy_el.click()
            await asyncio.sleep(self._WAIT_AFTER_CLICK)

        # 读取剪贴板
        return self.device_mgr.get_clipboard(device_id)

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

            # 步骤间短暂等待
            await asyncio.sleep(0.5)

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
