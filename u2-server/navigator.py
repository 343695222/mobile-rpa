"""Navigator — 导航管理器，负责到达目标 App 的目标页面。

优先使用 ScriptStore 中已保存的导航脚本，无脚本时通过 VisionAgent 探索。
探索成功后自动保存导航脚本供后续复用。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from device import DeviceManager
from safety_guard import SafetyGuard
from script_store import ScriptStore
from vision_agent import VisionAgent

logger = logging.getLogger(__name__)

# Delay between navigation steps (seconds)
STEP_DELAY = 0.5


class Navigator:
    """导航管理器：脚本优先，探索回退，自动学习。"""

    def __init__(
        self,
        device_manager: DeviceManager,
        vision_agent: VisionAgent,
        script_store: ScriptStore,
        safety_guard: SafetyGuard | None = None,
    ) -> None:
        self.device_manager = device_manager
        self.vision_agent = vision_agent
        self.script_store = script_store
        self.safety_guard = safety_guard or SafetyGuard()

    async def navigate_to(
        self, device_id: str, app: str, target_page: str
    ) -> dict[str, Any]:
        """导航到目标页面。优先用已有脚本，无脚本则探索。

        Returns:
            {"success": bool, "steps": [...], "error"?: str}
        """
        # 1. 查找已有导航脚本
        script = self.script_store.find_navigation(app, target_page)

        if script is not None:
            logger.info("Found existing navigation script %s for %s/%s", script["id"], app, target_page)
            result = await self.execute_script(device_id, script)
            if result["success"]:
                self.script_store.update_usage(script["id"])
                return result
            # 脚本执行失败，标记无效，回退到探索
            logger.warning("Script %s failed, marking invalid and falling back to explore", script["id"])
            self.script_store.mark_invalid(script["id"])

        # 2. 无可用脚本（或脚本失败），通过 VisionAgent 探索
        explore_result = await self.explore(device_id, app, target_page)

        if explore_result["success"]:
            # 3. 探索成功，保存导航脚本
            nav_steps = self._extract_navigation_steps(explore_result.get("steps", []))
            self.script_store.save(
                app=app,
                data_type=target_page,
                strategy="navigation",
                config={"navigation": nav_steps, "extraction": {}},
            )
            logger.info("Saved new navigation script for %s/%s", app, target_page)

        return explore_result

    async def explore(
        self, device_id: str, app: str, target: str
    ) -> dict[str, Any]:
        """通过 VisionAgent 自主探索到达目标页面。

        Returns:
            {"success": bool, "steps": [...], "error"?: str}
        """
        try:
            # 先启动目标 App
            self.device_manager.app_start(device_id, app)
            await asyncio.sleep(1.0)  # 等待 App 启动

            # 用 VisionAgent 探索
            goal = f"到达{app}的{target}页面"
            result = await self.vision_agent.run_task(device_id, goal)

            return {
                "success": result.get("success", False),
                "steps": result.get("steps", []),
                "error": result.get("message") if not result.get("success") else None,
            }
        except Exception as exc:
            logger.error("Explore failed for %s/%s: %s", app, target, exc)
            return {
                "success": False,
                "steps": [],
                "error": str(exc),
            }

    async def execute_script(
        self, device_id: str, script: dict
    ) -> dict[str, Any]:
        """按已保存脚本的导航步骤顺序执行。

        支持的步骤类型: click, click_element, swipe, input_text, wait

        Returns:
            {"success": bool, "steps": [...], "error"?: str}
        """
        navigation = script.get("navigation", [])
        if not navigation:
            return {"success": True, "steps": [], "error": None}

        # 按 order 排序
        sorted_steps = sorted(navigation, key=lambda s: s.get("order", 0))
        executed: list[dict[str, Any]] = []

        for step in sorted_steps:
            action = step.get("action", {})
            action_type = action.get("type", "")
            description = step.get("description", "")

            try:
                await self._execute_step(device_id, action)
                executed.append({
                    "order": step.get("order", 0),
                    "action": action,
                    "description": description,
                    "success": True,
                })
            except Exception as exc:
                executed.append({
                    "order": step.get("order", 0),
                    "action": action,
                    "description": description,
                    "success": False,
                    "error": str(exc),
                })
                return {
                    "success": False,
                    "steps": executed,
                    "error": f"Step {step.get('order', '?')} failed: {exc}",
                }

            await asyncio.sleep(STEP_DELAY)

        return {"success": True, "steps": executed}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _execute_step(self, device_id: str, action: dict[str, Any]) -> None:
        """Execute a single navigation step action (with safety check)."""
        # ── Safety Guard 检查 ──
        description = action.get("description", "")
        safety_result = self.safety_guard.check_action(action, reasoning=description)
        if not safety_result.allowed:
            raise RuntimeError(f"Safety blocked: {safety_result.reason}")

        action_type = action.get("type", "")

        if action_type == "click":
            self.device_manager.click(device_id, int(action["x"]), int(action["y"]))

        elif action_type == "click_element":
            selector = action.get("selector", {})
            clicked = self.device_manager.click_element(
                device_id, selector["by"], selector["value"]
            )
            if not clicked:
                raise RuntimeError(
                    f"Element not found: {selector.get('by')}={selector.get('value')}"
                )

        elif action_type == "swipe":
            duration = action.get("duration", 0.5)
            self.device_manager.swipe(
                device_id,
                int(action["x1"]),
                int(action["y1"]),
                int(action["x2"]),
                int(action["y2"]),
                duration=float(duration),
            )

        elif action_type == "input_text":
            self.device_manager.input_text(device_id, action["text"])

        elif action_type == "wait":
            ms = action.get("duration", action.get("ms", 1000))
            await asyncio.sleep(float(ms) / 1000.0 if ms > 10 else float(ms))

        else:
            raise ValueError(f"Unknown navigation step type: {action_type}")

    @staticmethod
    def _extract_navigation_steps(vision_steps: list[dict]) -> list[dict]:
        """Convert VisionAgent step records into NavigationStep format."""
        nav_steps: list[dict] = []
        order = 1

        for step in vision_steps:
            action = step.get("action")
            if action is None or step.get("done"):
                continue

            action_type = action.get("type", "")
            nav_action: dict[str, Any] = {}

            if action_type == "tap":
                nav_action = {
                    "type": "click",
                    "x": action.get("x"),
                    "y": action.get("y"),
                }
            elif action_type == "input_text":
                nav_action = {
                    "type": "input_text",
                    "text": action.get("text", ""),
                }
            elif action_type == "swipe":
                nav_action = {
                    "type": "swipe",
                    "x1": action.get("x1"),
                    "y1": action.get("y1"),
                    "x2": action.get("x2"),
                    "y2": action.get("y2"),
                    "duration": action.get("duration", 500) / 1000.0,
                }
            elif action_type == "wait":
                nav_action = {
                    "type": "wait",
                    "duration": action.get("ms", 1000),
                }
            elif action_type == "key_event":
                # key_event 不保存为导航步骤（通常是辅助操作）
                continue
            else:
                continue

            nav_steps.append({
                "order": order,
                "action": nav_action,
                "description": step.get("reasoning", ""),
            })
            order += 1

        return nav_steps
