"""VisionAgent — 视觉驱动的智能决策循环。

从 TypeScript vision-agent.ts 迁移到 Python。
截图 → 发给 GLM-4.6V → 解析返回的操作指令 → 通过 DeviceManager 执行。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from device import DeviceManager
from safety_guard import SafetyBlockedError, SafetyGuard
from vision import GlmVisionClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是手机自动化助手。看截图，返回下一步操作的JSON。

格式：{"reasoning": "思考", "done": false, "action": {"type": "tap", "x": 540, "y": 960}}

操作类型：
- tap: {"type":"tap","x":数字,"y":数字}
- input_text: {"type":"input_text","text":"文字"}
- swipe: {"type":"swipe","x1":起,"y1":起,"x2":终,"y2":终,"duration":毫秒}
- key_event: {"type":"key_event","keyCode":数字} (3=Home,4=返回,66=回车)
- wait: {"type":"wait","ms":毫秒}

完成时：{"reasoning":"完成原因","done":true,"action":null}

规则：坐标基于截图像素位置，每次只返回一个JSON操作，输入文字前先点击输入框。"""

# Delay between steps (seconds)
STEP_DELAY = 0.8

# Maximum history entries sent to the model
MAX_HISTORY = 5


class VisionAgent:
    """Vision-driven intelligent task execution agent."""

    def __init__(
        self,
        device_manager: DeviceManager,
        vision_client: GlmVisionClient,
        safety_guard: SafetyGuard | None = None,
    ) -> None:
        self.device_manager = device_manager
        self.vision_client = vision_client
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
        history: list[str] = []

        for step_num in range(1, max_steps + 1):
            # Decide next action (with 1 retry on failure)
            decision = await self.decide_next_action(device_id, goal, history[-MAX_HISTORY:])
            if not decision.get("success"):
                # Retry once after a short delay
                await asyncio.sleep(1.5)
                decision = await self.decide_next_action(device_id, goal, history[-MAX_HISTORY:])

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

            # Task completed
            if decision.get("done"):
                return {
                    "success": True,
                    "stepsCompleted": step_num,
                    "steps": steps,
                    "message": decision.get("reasoning", "Task completed"),
                }

            # Execute the action (with safety check)
            action = decision.get("action")
            if action:
                # ── Safety Guard 检查 ──
                reasoning = decision.get("reasoning", "")
                safety_result = self.safety_guard.check_action(
                    action, reasoning=reasoning,
                )

                if not safety_result.allowed:
                    step_record["safety_blocked"] = True
                    step_record["safety_reason"] = safety_result.reason

                    if safety_result.requires_confirmation:
                        # 需要人工确认 → 暂停任务，返回待确认状态
                        confirm_id = self.safety_guard.request_confirmation(safety_result)
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
                        # 直接拒绝（BLOCKED 级别）
                        return {
                            "success": False,
                            "stepsCompleted": step_num,
                            "steps": steps,
                            "message": f"🚫 操作被安全守卫拦截: {safety_result.reason}",
                            "safety_blocked": True,
                        }

                try:
                    await self._execute_action(device_id, action)
                    history.append(f"{action.get('type', '?')}: {json.dumps(action, ensure_ascii=False)}")
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
        history: list[str],
    ) -> dict[str, Any]:
        """Take a screenshot, build prompt, call vision model, parse response.

        Returns a dict with keys: success, action, reasoning, done, error?.
        """
        try:
            # 1. Screenshot
            base64_img = self.device_manager.screenshot_base64(device_id)

            # 2. Build user prompt
            user_prompt = f"目标：{goal}\n\n"
            if history:
                numbered = "\n".join(f"{i + 1}. {h}" for i, h in enumerate(history))
                user_prompt += f"已执行的操作：\n{numbered}\n\n"
            user_prompt += "请根据当前屏幕截图，决定下一步操作。只返回 JSON。"

            full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

            # 3. Call vision model
            result = await self.vision_client.analyze(base64_img, full_prompt)

            if not result.get("success"):
                return {
                    "success": False,
                    "action": None,
                    "reasoning": "",
                    "done": False,
                    "error": f"Vision API error: {result.get('error', 'unknown')}",
                }

            # 4. Parse response
            return self.parse_vision_response(result.get("description", ""))

        except Exception as exc:
            return {
                "success": False,
                "action": None,
                "reasoning": "",
                "done": False,
                "error": str(exc),
            }

    def parse_vision_response(self, text: str) -> dict[str, Any]:
        """Extract JSON from model response text and parse the action.

        Returns a dict with keys: success, action, reasoning, done, error?.
        """
        if not text or not text.strip():
            return {
                "success": False,
                "action": None,
                "reasoning": "",
                "done": False,
                "error": "Empty response from vision model",
            }

        # Try to extract JSON object from text — use greedy match for nested braces
        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text)
        if not match:
            # Fallback: maybe the model returned plain text reasoning without JSON
            # Treat it as "not done, no action" and retry
            return {
                "success": False,
                "action": None,
                "reasoning": text[:200],
                "done": False,
                "error": f"No JSON found in response: {text[:200]}",
            }

        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            return {
                "success": False,
                "action": None,
                "reasoning": "",
                "done": False,
                "error": f"JSON parse error: {exc}",
            }

        reasoning: str = parsed.get("reasoning", "")
        done: bool = parsed.get("done") is True

        if done or parsed.get("action") is None:
            return {
                "success": True,
                "action": None,
                "reasoning": reasoning,
                "done": True,
            }

        action = parsed.get("action")
        if not isinstance(action, dict) or "type" not in action:
            return {
                "success": False,
                "action": None,
                "reasoning": reasoning,
                "done": False,
                "error": "Invalid action format",
            }

        return {
            "success": True,
            "action": action,
            "reasoning": reasoning,
            "done": False,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _execute_action(self, device_id: str, action: dict[str, Any]) -> None:
        """Dispatch an action dict to the appropriate DeviceManager method."""
        action_type = action.get("type", "")

        if action_type == "tap":
            self.device_manager.click(device_id, int(action["x"]), int(action["y"]))

        elif action_type == "input_text":
            self.device_manager.input_text(device_id, action["text"])

        elif action_type == "swipe":
            duration = action.get("duration", 500)
            # TS version sends duration in ms; DeviceManager expects seconds
            self.device_manager.swipe(
                device_id,
                int(action["x1"]),
                int(action["y1"]),
                int(action["x2"]),
                int(action["y2"]),
                duration=duration / 1000.0,
            )

        elif action_type == "key_event":
            self.device_manager.key_event(device_id, int(action["keyCode"]))

        elif action_type == "wait":
            ms = action.get("ms", 1000)
            await asyncio.sleep(ms / 1000.0)

        else:
            raise ValueError(f"Unknown action type: {action_type}")
