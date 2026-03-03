"""VisionAgent — 视觉驱动的智能决策循环。

使用 GuiPlusClient（GUI-Plus 模型）作为操作决策后端，
通过 ActionMapper 将 GUI-Plus 的结构化操作指令映射为 DeviceManager 可执行的操作。

截图 → 调用 GuiPlusClient.decide → 解析 thought/action/parameters → ActionMapper 映射 → 执行。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from action_mapper import ActionMapper
from dashscope_client import GuiPlusClient
from device import DeviceManager
from safety_guard import SafetyGuard

logger = logging.getLogger(__name__)

# Delay between steps (seconds)
STEP_DELAY = 0.8

# Maximum history entries sent to the model
MAX_HISTORY = 5


class VisionAgent:
    """Vision-driven intelligent task execution agent using GUI-Plus."""

    def __init__(
        self,
        device_manager: DeviceManager,
        gui_plus_client: GuiPlusClient,
        safety_guard: SafetyGuard | None = None,
    ) -> None:
        self.device_manager = device_manager
        self.gui_plus_client = gui_plus_client
        self.safety_guard = safety_guard or SafetyGuard()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_task(
        self,
        device_id: str,
        goal: str,
        max_steps: int = 20,
    ) -> dict[str, Any]:
        """Execute a goal-driven task loop.

        Returns a dict with keys: success, stepsCompleted, steps, message.
        """
        steps: list[dict[str, Any]] = []
        history: list[dict] = []

        for step_num in range(1, max_steps + 1):
            # Decide next action (with 1 retry on failure)
            decision = await self.decide_next_action(
                device_id, goal, history[-MAX_HISTORY:]
            )
            if not decision.get("success"):
                await asyncio.sleep(1.5)
                decision = await self.decide_next_action(
                    device_id, goal, history[-MAX_HISTORY:]
                )

            step_record: dict[str, Any] = {
                "step": step_num,
                "reasoning": decision.get("reasoning", ""),
                "done": decision.get("done", False),
                "action": decision.get("action"),
                "error": decision.get("error"),
            }
            steps.append(step_record)

            # Decision failed
            if not decision.get("success"):
                return {
                    "success": False,
                    "stepsCompleted": step_num,
                    "steps": steps,
                    "message": f"Decision failed at step {step_num}: {decision.get('error', 'unknown')}",
                }

            # FINISH → task succeeded
            if decision.get("done"):
                is_fail = decision.get("is_fail", False)
                if is_fail:
                    return {
                        "success": False,
                        "stepsCompleted": step_num,
                        "steps": steps,
                        "message": decision.get("reasoning", "Task failed"),
                    }
                return {
                    "success": True,
                    "stepsCompleted": step_num,
                    "steps": steps,
                    "message": decision.get("reasoning", "Task completed"),
                }

            # Execute the action (with safety check)
            action = decision.get("action")
            if action:
                # Check for ActionMapper error
                if "error" in action:
                    step_record["error"] = action["error"]
                    return {
                        "success": False,
                        "stepsCompleted": step_num,
                        "steps": steps,
                        "message": f"Action mapping error: {action['error']}",
                    }

                # ── Safety Guard 检查 ──
                reasoning = decision.get("reasoning", "")
                safety_result = self.safety_guard.check_action(
                    action, reasoning=reasoning,
                )

                if not safety_result.allowed:
                    step_record["safety_blocked"] = True
                    step_record["safety_reason"] = safety_result.reason

                    if safety_result.requires_confirmation:
                        confirm_id = self.safety_guard.request_confirmation(
                            safety_result
                        )
                        return {
                            "success": False,
                            "stepsCompleted": step_num,
                            "steps": steps,
                            "message": safety_result.reason,
                            "safety_paused": True,
                            "confirm_id": confirm_id,
                            "confirmation_prompt": safety_result.confirmation_prompt,
                        }
                    else:
                        return {
                            "success": False,
                            "stepsCompleted": step_num,
                            "steps": steps,
                            "message": f"🚫 操作被安全守卫拦截: {safety_result.reason}",
                            "safety_blocked": True,
                        }

                try:
                    await self._execute_action(device_id, action)
                    # Append to conversation history for multi-turn
                    history.append(
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "thought": decision.get("reasoning", ""),
                                    "action": decision.get("raw_action", ""),
                                    "parameters": decision.get(
                                        "raw_parameters", {}
                                    ),
                                },
                                ensure_ascii=False,
                            ),
                        }
                    )
                except Exception as exc:
                    step_record["error"] = str(exc)
                    return {
                        "success": False,
                        "stepsCompleted": step_num,
                        "steps": steps,
                        "message": f"Action execution failed at step {step_num}: {exc}",
                    }

            # Wait between steps
            await asyncio.sleep(STEP_DELAY)

        # Reached max steps
        return {
            "success": False,
            "stepsCompleted": max_steps,
            "steps": steps,
            "message": f"Reached maximum steps ({max_steps}) without completing the task",
        }

    async def decide_next_action(
        self,
        device_id: str,
        goal: str,
        history: list[dict],
    ) -> dict[str, Any]:
        """Take screenshot → call GuiPlusClient.decide → parse and map action.

        Returns a dict with keys: success, action, reasoning, done, error?,
        is_fail?, raw_action?, raw_parameters?.
        """
        try:
            # 1. Screenshot
            base64_img = self.device_manager.screenshot_base64(device_id)

            # 2. Call GUI-Plus
            result = await self.gui_plus_client.decide(
                base64_img, goal, history
            )

            # 3. Parse GUI-Plus response
            return self._parse_gui_plus_response(result)

        except Exception as exc:
            return {
                "success": False,
                "action": None,
                "reasoning": "",
                "done": False,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_gui_plus_response(result: dict) -> dict[str, Any]:
        """Parse GuiPlusClient.decide() result into VisionAgent decision format.

        Handles thought/action/parameters from GUI-Plus and maps actions
        via ActionMapper.

        Returns:
            {
                "success": bool,
                "action": dict | None,   # ActionMapper-mapped action
                "reasoning": str,        # thought field
                "done": bool,
                "error": str | None,
                "is_fail": bool,         # True when action is FAIL
                "raw_action": str,       # original GUI-Plus action type
                "raw_parameters": dict,  # original GUI-Plus parameters
            }
        """
        if not result.get("success"):
            return {
                "success": False,
                "action": None,
                "reasoning": result.get("thought", ""),
                "done": False,
                "error": f"GUI-Plus API error: {result.get('error', 'unknown')}",
            }

        thought = result.get("thought", "")
        action_type = result.get("action", "")
        parameters = result.get("parameters", {})

        # FINISH → task completed successfully
        if action_type == "FINISH":
            return {
                "success": True,
                "action": None,
                "reasoning": thought,
                "done": True,
                "is_fail": False,
                "raw_action": action_type,
                "raw_parameters": parameters,
            }

        # FAIL → task failed
        if action_type == "FAIL":
            return {
                "success": True,
                "action": None,
                "reasoning": thought,
                "done": True,
                "is_fail": True,
                "raw_action": action_type,
                "raw_parameters": parameters,
            }

        # Map GUI-Plus action to DeviceManager action
        mapped = ActionMapper.map_action(action_type, parameters)

        return {
            "success": True,
            "action": mapped,
            "reasoning": thought,
            "done": False,
            "raw_action": action_type,
            "raw_parameters": parameters,
        }

    async def _execute_action(
        self, device_id: str, action: dict[str, Any]
    ) -> None:
        """Dispatch an action dict to the appropriate DeviceManager method."""
        action_type = action.get("type", "")

        if action_type == "tap":
            self.device_manager.click(
                device_id, int(action["x"]), int(action["y"])
            )

        elif action_type == "input_text":
            self.device_manager.input_text(device_id, action["text"])

        elif action_type == "swipe":
            duration = action.get("duration", 500)
            # DeviceManager expects seconds
            self.device_manager.swipe(
                device_id,
                int(action["x1"]),
                int(action["y1"]),
                int(action["x2"]),
                int(action["y2"]),
                duration=duration / 1000.0,
            )

        elif action_type == "key_event":
            self.device_manager.key_event(
                device_id, int(action["keyCode"])
            )

        elif action_type == "wait":
            ms = action.get("ms", 1000)
            await asyncio.sleep(ms / 1000.0)

        else:
            raise ValueError(f"Unknown action type: {action_type}")
