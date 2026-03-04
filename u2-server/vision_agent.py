"""VisionAgent — 视觉驱动的智能决策循环（Midscene 风格优化版）。

核心优化（借鉴 Midscene.js 思路）：
1. OCR 预处理：截图后先用 OCR 模型识别屏幕文字，注入 task_prompt
2. 疑问句过滤：如果模型返回的 thought 包含疑问句，自动重试
3. 强化提示词：系统提示词强调"先读文字再行动"

截图 → OCR预识别 → 调用 GuiPlusClient.decide(带OCR上下文) → 过滤 → 执行。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from action_mapper import ActionMapper
from dashscope_client import DashScopeVLClient, GuiPlusClient
from device import DeviceManager
from safety_guard import SafetyGuard

logger = logging.getLogger(__name__)

# Delay between steps (seconds)
STEP_DELAY = 0.8

# Maximum history entries sent to the model
MAX_HISTORY = 5

# OCR prompt for screen text pre-extraction
OCR_PROMPT = (
    "逐行列出这张手机截图上所有可见的文字，每行一个，格式：\n"
    "- 文字内容\n"
    "只输出文字列表，不要其他解释。"
)

# Patterns that indicate the model is "asking" instead of "acting"
QUESTION_PATTERNS = re.compile(
    r"[？?]|请问|请告诉|能否|是否可以|你能|在哪里|在哪|"
    r"能不能|可以吗|是不是|有没有.{0,4}[？?]"
)


class VisionAgent:
    """Vision-driven intelligent task execution agent using GUI-Plus."""

    def __init__(
        self,
        device_manager: DeviceManager,
        gui_plus_client: GuiPlusClient,
        safety_guard: SafetyGuard | None = None,
        ocr_client: DashScopeVLClient | None = None,
    ) -> None:
        self.device_manager = device_manager
        self.gui_plus_client = gui_plus_client
        self.safety_guard = safety_guard or SafetyGuard()
        self.ocr_client = ocr_client  # 可选，用于 OCR 预处理

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_task(
        self,
        device_id: str,
        goal: str,
        max_steps: int = 20,
    ) -> dict[str, Any]:
        """Execute a goal-driven task loop."""
        steps: list[dict[str, Any]] = []
        history: list[dict] = []

        for step_num in range(1, max_steps + 1):
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
            if decision.get("ocr_text"):
                step_record["ocr_text"] = decision["ocr_text"]
            steps.append(step_record)

            # Decision failed
            if not decision.get("success"):
                return {
                    "success": False,
                    "stepsCompleted": step_num,
                    "steps": steps,
                    "message": f"Decision failed at step {step_num}: {decision.get('error', 'unknown')}",
                }

            # FINISH / FAIL
            if decision.get("done"):
                is_fail = decision.get("is_fail", False)
                return {
                    "success": not is_fail,
                    "stepsCompleted": step_num,
                    "steps": steps,
                    "message": decision.get("reasoning", "Task failed" if is_fail else "Task completed"),
                }

            # Execute the action (with safety check)
            action = decision.get("action")
            if action:
                if "error" in action:
                    step_record["error"] = action["error"]
                    return {
                        "success": False,
                        "stepsCompleted": step_num,
                        "steps": steps,
                        "message": f"Action mapping error: {action['error']}",
                    }

                reasoning = decision.get("reasoning", "")
                safety_result = self.safety_guard.check_action(
                    action, reasoning=reasoning,
                )

                if not safety_result.allowed:
                    step_record["safety_blocked"] = True
                    step_record["safety_reason"] = safety_result.reason
                    if safety_result.requires_confirmation:
                        confirm_id = self.safety_guard.request_confirmation(safety_result)
                        return {
                            "success": False, "stepsCompleted": step_num,
                            "steps": steps, "message": safety_result.reason,
                            "safety_paused": True, "confirm_id": confirm_id,
                            "confirmation_prompt": safety_result.confirmation_prompt,
                        }
                    else:
                        return {
                            "success": False, "stepsCompleted": step_num,
                            "steps": steps,
                            "message": f"\U0001f6ab 操作被安全守卫拦截: {safety_result.reason}",
                            "safety_blocked": True,
                        }

                try:
                    await self._execute_action(device_id, action)
                    history.append({
                        "role": "assistant",
                        "content": json.dumps({
                            "thought": decision.get("reasoning", ""),
                            "action": decision.get("raw_action", ""),
                            "parameters": decision.get("raw_parameters", {}),
                        }, ensure_ascii=False),
                    })
                except Exception as exc:
                    step_record["error"] = str(exc)
                    return {
                        "success": False, "stepsCompleted": step_num,
                        "steps": steps,
                        "message": f"Action execution failed at step {step_num}: {exc}",
                    }

            await asyncio.sleep(STEP_DELAY)

        return {
            "success": False,
            "stepsCompleted": max_steps,
            "steps": steps,
            "message": f"Reached maximum steps ({max_steps}) without completing the task",
        }

    # ------------------------------------------------------------------
    # Core decision method (with OCR pre-processing + question filter)
    # ------------------------------------------------------------------

    async def decide_next_action(
        self,
        device_id: str,
        goal: str,
        history: list[dict],
    ) -> dict[str, Any]:
        """截图 → OCR预识别 → GUI-Plus决策 → 疑问句过滤。

        Midscene 风格优化：
        1. 先用 OCR 模型识别屏幕文字（如果 ocr_client 可用）
        2. 把 OCR 结果拼到 task_prompt 里，帮助 GUI-Plus "看清"文字
        3. 如果 GUI-Plus 返回疑问句，自动重试（最多1次）
        """
        try:
            # 1. Screenshot
            base64_img = self.device_manager.screenshot_base64(device_id)

            # 2. OCR pre-processing (optional but recommended)
            ocr_text = ""
            if self.ocr_client:
                ocr_text = await self._ocr_screen(base64_img)

            # 3. Build enhanced task prompt with OCR context
            enhanced_prompt = self._build_enhanced_prompt(goal, ocr_text)

            # 4. Call GUI-Plus
            result = await self.gui_plus_client.decide(
                base64_img, enhanced_prompt, history
            )

            # 5. Parse response
            decision = self._parse_gui_plus_response(result)

            # 6. Question filter: if thought contains questions, retry once
            if (
                decision.get("success")
                and not decision.get("done")
                and self._contains_question(decision.get("reasoning", ""))
            ):
                logger.warning(
                    "GUI-Plus returned a question instead of action: %s — retrying",
                    decision.get("reasoning", "")[:100],
                )
                # Retry with stronger hint
                retry_prompt = enhanced_prompt + "\n\n【重要提醒】不要提问，直接执行操作。如果目标在屏幕上就点击，不在就滑动查找。"
                result = await self.gui_plus_client.decide(
                    base64_img, retry_prompt, history
                )
                decision = self._parse_gui_plus_response(result)

            # Attach OCR text to decision for debugging
            if ocr_text:
                decision["ocr_text"] = ocr_text

            return decision

        except Exception as exc:
            return {
                "success": False,
                "action": None,
                "reasoning": "",
                "done": False,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # OCR pre-processing
    # ------------------------------------------------------------------

    async def _ocr_screen(self, base64_img: str) -> str:
        """用 OCR 模型预识别屏幕文字。失败时返回空字符串（不阻塞主流程）。"""
        try:
            result = await self.ocr_client.analyze(base64_img, OCR_PROMPT)
            if result.get("success"):
                text = result.get("description", "").strip()
                if text:
                    logger.info("OCR pre-scan found %d chars", len(text))
                    return text
            else:
                logger.warning("OCR pre-scan failed: %s", result.get("error", ""))
        except Exception as exc:
            logger.warning("OCR pre-scan exception: %s", exc)
        return ""

    @staticmethod
    def _build_enhanced_prompt(goal: str, ocr_text: str) -> str:
        """构建增强版 task prompt，注入 OCR 识别结果。"""
        if not ocr_text:
            return goal

        return (
            f"任务目标：{goal}\n\n"
            f"【OCR识别结果】以下是屏幕上识别到的文字：\n{ocr_text}\n\n"
            f"请根据以上文字和截图，判断目标是否在屏幕上，然后立即执行操作。"
        )

    @staticmethod
    def _contains_question(thought: str) -> bool:
        """检测 thought 是否包含疑问句（模型在"提问"而不是"行动"）。"""
        if not thought:
            return False
        return bool(QUESTION_PATTERNS.search(thought))

    # ------------------------------------------------------------------
    # Parse GUI-Plus response
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_gui_plus_response(result: dict) -> dict[str, Any]:
        """Parse GuiPlusClient.decide() result into VisionAgent decision format."""
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

        if action_type == "FINISH":
            return {
                "success": True, "action": None, "reasoning": thought,
                "done": True, "is_fail": False,
                "raw_action": action_type, "raw_parameters": parameters,
            }

        if action_type == "FAIL":
            return {
                "success": True, "action": None, "reasoning": thought,
                "done": True, "is_fail": True,
                "raw_action": action_type, "raw_parameters": parameters,
            }

        mapped = ActionMapper.map_action(action_type, parameters)
        return {
            "success": True, "action": mapped, "reasoning": thought,
            "done": False,
            "raw_action": action_type, "raw_parameters": parameters,
        }

    # ------------------------------------------------------------------
    # Execute action
    # ------------------------------------------------------------------

    async def _execute_action(
        self, device_id: str, action: dict[str, Any]
    ) -> None:
        """Dispatch an action dict to the appropriate DeviceManager method."""
        action_type = action.get("type", "")

        if action_type == "tap":
            self.device_manager.click(device_id, int(action["x"]), int(action["y"]))
        elif action_type == "input_text":
            self.device_manager.input_text(device_id, action["text"])
        elif action_type == "swipe":
            duration = action.get("duration", 500)
            self.device_manager.swipe(
                device_id,
                int(action["x1"]), int(action["y1"]),
                int(action["x2"]), int(action["y2"]),
                duration=duration / 1000.0,
            )
        elif action_type == "key_event":
            self.device_manager.key_event(device_id, int(action["keyCode"]))
        elif action_type == "wait":
            await asyncio.sleep(action.get("ms", 1000) / 1000.0)
        else:
            raise ValueError(f"Unknown action type: {action_type}")
