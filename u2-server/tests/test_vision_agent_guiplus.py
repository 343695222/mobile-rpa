"""VisionAgent 适配 GuiPlusClient 后的集成测试。

测试 VisionAgent 使用 GuiPlusClient 作为操作决策后端时的行为，
包括 decide_next_action、run_task、SafetyGuard 集成、FINISH/FAIL 处理等。
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# Mock uiautomator2 before importing device module
sys.modules.setdefault("uiautomator2", MagicMock())

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from action_mapper import ActionMapper
from dashscope_client import GuiPlusClient
from device import DeviceManager
from safety_guard import SafetyCheckResult, SafetyGuard, SafetyLevel
from vision_agent import MAX_HISTORY, STEP_DELAY, VisionAgent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_device_manager():
    dm = MagicMock(spec=DeviceManager)
    dm.screenshot_base64.return_value = "base64_fake_screenshot"
    return dm


@pytest.fixture
def mock_gui_plus_client():
    client = MagicMock(spec=GuiPlusClient)
    client.decide = AsyncMock()
    return client


@pytest.fixture
def mock_safety_guard():
    guard = MagicMock(spec=SafetyGuard)
    guard.check_action.return_value = SafetyCheckResult(
        level=SafetyLevel.SAFE,
        allowed=True,
        reason="safe",
        action={},
    )
    return guard


@pytest.fixture
def agent(mock_device_manager, mock_gui_plus_client, mock_safety_guard):
    return VisionAgent(
        device_manager=mock_device_manager,
        gui_plus_client=mock_gui_plus_client,
        safety_guard=mock_safety_guard,
    )


# ---------------------------------------------------------------------------
# Constructor tests
# ---------------------------------------------------------------------------


class TestVisionAgentInit:
    def test_accepts_gui_plus_client(
        self, mock_device_manager, mock_gui_plus_client
    ):
        agent = VisionAgent(
            device_manager=mock_device_manager,
            gui_plus_client=mock_gui_plus_client,
        )
        assert agent.gui_plus_client is mock_gui_plus_client
        assert agent.device_manager is mock_device_manager

    def test_default_safety_guard(
        self, mock_device_manager, mock_gui_plus_client
    ):
        agent = VisionAgent(
            device_manager=mock_device_manager,
            gui_plus_client=mock_gui_plus_client,
        )
        assert isinstance(agent.safety_guard, SafetyGuard)

    def test_custom_safety_guard(
        self, mock_device_manager, mock_gui_plus_client, mock_safety_guard
    ):
        agent = VisionAgent(
            device_manager=mock_device_manager,
            gui_plus_client=mock_gui_plus_client,
            safety_guard=mock_safety_guard,
        )
        assert agent.safety_guard is mock_safety_guard


# ---------------------------------------------------------------------------
# _parse_gui_plus_response tests
# ---------------------------------------------------------------------------


class TestParseGuiPlusResponse:
    def test_click_action(self):
        result = VisionAgent._parse_gui_plus_response(
            {
                "success": True,
                "thought": "点击搜索按钮",
                "action": "CLICK",
                "parameters": {"x": 540, "y": 960},
                "raw_response": "",
                "error": None,
            }
        )
        assert result["success"] is True
        assert result["action"] == {"type": "tap", "x": 540, "y": 960}
        assert result["reasoning"] == "点击搜索按钮"
        assert result["done"] is False

    def test_type_action(self):
        result = VisionAgent._parse_gui_plus_response(
            {
                "success": True,
                "thought": "输入搜索词",
                "action": "TYPE",
                "parameters": {"text": "hello"},
                "raw_response": "",
                "error": None,
            }
        )
        assert result["action"] == {"type": "input_text", "text": "hello"}
        assert result["done"] is False

    def test_finish_action(self):
        result = VisionAgent._parse_gui_plus_response(
            {
                "success": True,
                "thought": "任务已完成",
                "action": "FINISH",
                "parameters": {},
                "raw_response": "",
                "error": None,
            }
        )
        assert result["success"] is True
        assert result["done"] is True
        assert result["is_fail"] is False
        assert result["action"] is None
        assert result["reasoning"] == "任务已完成"

    def test_fail_action(self):
        result = VisionAgent._parse_gui_plus_response(
            {
                "success": True,
                "thought": "无法找到目标元素",
                "action": "FAIL",
                "parameters": {},
                "raw_response": "",
                "error": None,
            }
        )
        assert result["success"] is True
        assert result["done"] is True
        assert result["is_fail"] is True
        assert result["action"] is None
        assert result["reasoning"] == "无法找到目标元素"

    def test_api_error(self):
        result = VisionAgent._parse_gui_plus_response(
            {
                "success": False,
                "thought": "",
                "action": "",
                "parameters": {},
                "raw_response": "",
                "error": "API timeout",
            }
        )
        assert result["success"] is False
        assert result["done"] is False
        assert "API timeout" in result["error"]

    def test_scroll_action(self):
        result = VisionAgent._parse_gui_plus_response(
            {
                "success": True,
                "thought": "向下滑动查看更多",
                "action": "SCROLL",
                "parameters": {"x": 540, "y": 960, "direction": "down"},
                "raw_response": "",
                "error": None,
            }
        )
        assert result["action"]["type"] == "swipe"
        assert result["done"] is False

    def test_key_press_action(self):
        result = VisionAgent._parse_gui_plus_response(
            {
                "success": True,
                "thought": "按返回键",
                "action": "KEY_PRESS",
                "parameters": {"key": "back"},
                "raw_response": "",
                "error": None,
            }
        )
        assert result["action"] == {"type": "key_event", "keyCode": 4}

    def test_unknown_action_returns_error_dict(self):
        result = VisionAgent._parse_gui_plus_response(
            {
                "success": True,
                "thought": "unknown",
                "action": "UNKNOWN_OP",
                "parameters": {},
                "raw_response": "",
                "error": None,
            }
        )
        assert result["success"] is True
        assert result["action"] is not None
        assert "error" in result["action"]

    def test_preserves_raw_action_and_parameters(self):
        result = VisionAgent._parse_gui_plus_response(
            {
                "success": True,
                "thought": "click",
                "action": "CLICK",
                "parameters": {"x": 100, "y": 200},
                "raw_response": "",
                "error": None,
            }
        )
        assert result["raw_action"] == "CLICK"
        assert result["raw_parameters"] == {"x": 100, "y": 200}


# ---------------------------------------------------------------------------
# decide_next_action tests
# ---------------------------------------------------------------------------


class TestDecideNextAction:
    @pytest.mark.asyncio
    async def test_calls_gui_plus_decide(self, agent, mock_gui_plus_client):
        mock_gui_plus_client.decide.return_value = {
            "success": True,
            "thought": "点击按钮",
            "action": "CLICK",
            "parameters": {"x": 100, "y": 200},
            "raw_response": "",
            "error": None,
        }

        result = await agent.decide_next_action("device1", "打开设置", [])

        mock_gui_plus_client.decide.assert_called_once_with(
            "base64_fake_screenshot", "打开设置", []
        )
        assert result["success"] is True
        assert result["action"] == {"type": "tap", "x": 100, "y": 200}

    @pytest.mark.asyncio
    async def test_passes_history(self, agent, mock_gui_plus_client):
        history = [
            {"role": "assistant", "content": '{"thought":"ok","action":"CLICK","parameters":{"x":1,"y":2}}'}
        ]
        mock_gui_plus_client.decide.return_value = {
            "success": True,
            "thought": "next",
            "action": "FINISH",
            "parameters": {},
            "raw_response": "",
            "error": None,
        }

        await agent.decide_next_action("device1", "goal", history)

        mock_gui_plus_client.decide.assert_called_once_with(
            "base64_fake_screenshot", "goal", history
        )

    @pytest.mark.asyncio
    async def test_handles_screenshot_error(self, agent, mock_device_manager):
        mock_device_manager.screenshot_base64.side_effect = RuntimeError(
            "device disconnected"
        )

        result = await agent.decide_next_action("device1", "goal", [])

        assert result["success"] is False
        assert "device disconnected" in result["error"]

    @pytest.mark.asyncio
    async def test_handles_decide_error(self, agent, mock_gui_plus_client):
        mock_gui_plus_client.decide.side_effect = RuntimeError("network error")

        result = await agent.decide_next_action("device1", "goal", [])

        assert result["success"] is False
        assert "network error" in result["error"]


# ---------------------------------------------------------------------------
# run_task tests
# ---------------------------------------------------------------------------


class TestRunTask:
    @pytest.mark.asyncio
    async def test_finish_returns_success(self, agent, mock_gui_plus_client):
        mock_gui_plus_client.decide.return_value = {
            "success": True,
            "thought": "任务完成",
            "action": "FINISH",
            "parameters": {},
            "raw_response": "",
            "error": None,
        }

        result = await agent.run_task("device1", "打开设置", max_steps=5)

        assert result["success"] is True
        assert result["stepsCompleted"] == 1
        assert result["message"] == "任务完成"
        assert isinstance(result["steps"], list)

    @pytest.mark.asyncio
    async def test_fail_returns_failure(self, agent, mock_gui_plus_client):
        mock_gui_plus_client.decide.return_value = {
            "success": True,
            "thought": "找不到目标",
            "action": "FAIL",
            "parameters": {},
            "raw_response": "",
            "error": None,
        }

        result = await agent.run_task("device1", "打开设置", max_steps=5)

        assert result["success"] is False
        assert result["stepsCompleted"] == 1
        assert result["message"] == "找不到目标"

    @pytest.mark.asyncio
    async def test_return_format_always_has_required_keys(
        self, agent, mock_gui_plus_client
    ):
        """Validates: Requirements 4.6 — return format consistency."""
        mock_gui_plus_client.decide.return_value = {
            "success": True,
            "thought": "done",
            "action": "FINISH",
            "parameters": {},
            "raw_response": "",
            "error": None,
        }

        result = await agent.run_task("device1", "goal", max_steps=3)

        assert "success" in result
        assert "stepsCompleted" in result
        assert "steps" in result
        assert "message" in result
        assert isinstance(result["success"], bool)
        assert isinstance(result["stepsCompleted"], int)
        assert isinstance(result["steps"], list)
        assert isinstance(result["message"], str)

    @pytest.mark.asyncio
    async def test_return_format_on_api_error(
        self, agent, mock_gui_plus_client
    ):
        """Return format must be consistent even on API errors."""
        mock_gui_plus_client.decide.return_value = {
            "success": False,
            "thought": "",
            "action": "",
            "parameters": {},
            "raw_response": "",
            "error": "timeout",
        }

        result = await agent.run_task("device1", "goal", max_steps=3)

        assert "success" in result
        assert "stepsCompleted" in result
        assert "steps" in result
        assert "message" in result

    @pytest.mark.asyncio
    async def test_executes_click_action(
        self, agent, mock_gui_plus_client, mock_device_manager
    ):
        call_count = 0

        async def decide_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "success": True,
                    "thought": "点击按钮",
                    "action": "CLICK",
                    "parameters": {"x": 100, "y": 200},
                    "raw_response": "",
                    "error": None,
                }
            return {
                "success": True,
                "thought": "完成",
                "action": "FINISH",
                "parameters": {},
                "raw_response": "",
                "error": None,
            }

        mock_gui_plus_client.decide.side_effect = decide_side_effect

        result = await agent.run_task("device1", "goal", max_steps=5)

        assert result["success"] is True
        mock_device_manager.click.assert_called_once_with("device1", 100, 200)

    @pytest.mark.asyncio
    async def test_max_steps_reached(self, agent, mock_gui_plus_client):
        mock_gui_plus_client.decide.return_value = {
            "success": True,
            "thought": "继续操作",
            "action": "CLICK",
            "parameters": {"x": 100, "y": 200},
            "raw_response": "",
            "error": None,
        }

        result = await agent.run_task("device1", "goal", max_steps=2)

        assert result["success"] is False
        assert result["stepsCompleted"] == 2
        assert "maximum steps" in result["message"]

    @pytest.mark.asyncio
    async def test_history_uses_conversation_format(
        self, agent, mock_gui_plus_client
    ):
        """History should be conversation-format dicts for GUI-Plus multi-turn."""
        call_count = 0

        async def decide_side_effect(base64_img, goal, history):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "success": True,
                    "thought": "step 1",
                    "action": "CLICK",
                    "parameters": {"x": 10, "y": 20},
                    "raw_response": "",
                    "error": None,
                }
            # On second call, verify history format
            if call_count == 2 and history:
                assert isinstance(history[0], dict)
                assert history[0]["role"] == "assistant"
                content = json.loads(history[0]["content"])
                assert "thought" in content
                assert "action" in content
            return {
                "success": True,
                "thought": "done",
                "action": "FINISH",
                "parameters": {},
                "raw_response": "",
                "error": None,
            }

        mock_gui_plus_client.decide.side_effect = decide_side_effect

        result = await agent.run_task("device1", "goal", max_steps=5)
        assert result["success"] is True
        assert call_count == 2


# ---------------------------------------------------------------------------
# SafetyGuard integration tests
# ---------------------------------------------------------------------------


class TestSafetyGuardIntegration:
    @pytest.mark.asyncio
    async def test_safety_check_called_with_mapped_action_and_thought(
        self, agent, mock_gui_plus_client, mock_safety_guard
    ):
        """Validates: Requirements 9.1 — SafetyGuard receives mapped action + thought."""
        call_count = 0

        async def decide_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "success": True,
                    "thought": "点击出价按钮",
                    "action": "CLICK",
                    "parameters": {"x": 300, "y": 400},
                    "raw_response": "",
                    "error": None,
                }
            return {
                "success": True,
                "thought": "done",
                "action": "FINISH",
                "parameters": {},
                "raw_response": "",
                "error": None,
            }

        mock_gui_plus_client.decide.side_effect = decide_side_effect

        await agent.run_task("device1", "goal", max_steps=5)

        # SafetyGuard should be called with the mapped action dict and thought
        mock_safety_guard.check_action.assert_called_with(
            {"type": "tap", "x": 300, "y": 400},
            reasoning="点击出价按钮",
        )

    @pytest.mark.asyncio
    async def test_safety_blocked_returns_error(
        self, agent, mock_gui_plus_client, mock_safety_guard
    ):
        """Validates: Requirements 9.2 — BLOCKED level rejects execution."""
        mock_gui_plus_client.decide.return_value = {
            "success": True,
            "thought": "点击支付",
            "action": "CLICK",
            "parameters": {"x": 100, "y": 200},
            "raw_response": "",
            "error": None,
        }
        mock_safety_guard.check_action.return_value = SafetyCheckResult(
            level=SafetyLevel.BLOCKED,
            allowed=False,
            reason="禁止支付操作",
            action={"type": "tap", "x": 100, "y": 200},
        )

        result = await agent.run_task("device1", "goal", max_steps=5)

        assert result["success"] is False
        assert result.get("safety_blocked") is True
        assert "安全守卫拦截" in result["message"]

    @pytest.mark.asyncio
    async def test_safety_danger_requires_confirmation(
        self, agent, mock_gui_plus_client, mock_safety_guard
    ):
        """Validates: Requirements 9.3 — DANGER level pauses for confirmation."""
        mock_gui_plus_client.decide.return_value = {
            "success": True,
            "thought": "确认出价",
            "action": "CLICK",
            "parameters": {"x": 100, "y": 200},
            "raw_response": "",
            "error": None,
        }
        mock_safety_guard.check_action.return_value = SafetyCheckResult(
            level=SafetyLevel.DANGER,
            allowed=False,
            reason="危险操作需要确认",
            action={"type": "tap", "x": 100, "y": 200},
            requires_confirmation=True,
            confirmation_prompt="确认执行出价？",
        )
        mock_safety_guard.request_confirmation.return_value = "confirm_123"

        result = await agent.run_task("device1", "goal", max_steps=5)

        assert result["success"] is False
        assert result.get("safety_paused") is True
        assert result.get("confirm_id") == "confirm_123"

    @pytest.mark.asyncio
    async def test_no_safety_check_for_finish(
        self, agent, mock_gui_plus_client, mock_safety_guard
    ):
        """FINISH/FAIL are terminal signals — no safety check needed."""
        mock_gui_plus_client.decide.return_value = {
            "success": True,
            "thought": "done",
            "action": "FINISH",
            "parameters": {},
            "raw_response": "",
            "error": None,
        }

        await agent.run_task("device1", "goal", max_steps=5)

        mock_safety_guard.check_action.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_safety_check_for_fail(
        self, agent, mock_gui_plus_client, mock_safety_guard
    ):
        mock_gui_plus_client.decide.return_value = {
            "success": True,
            "thought": "cannot proceed",
            "action": "FAIL",
            "parameters": {},
            "raw_response": "",
            "error": None,
        }

        await agent.run_task("device1", "goal", max_steps=5)

        mock_safety_guard.check_action.assert_not_called()


# ---------------------------------------------------------------------------
# Action mapping error handling
# ---------------------------------------------------------------------------


class TestActionMappingErrors:
    @pytest.mark.asyncio
    async def test_unknown_action_type_returns_error(
        self, agent, mock_gui_plus_client
    ):
        mock_gui_plus_client.decide.return_value = {
            "success": True,
            "thought": "unknown op",
            "action": "UNKNOWN_OP",
            "parameters": {},
            "raw_response": "",
            "error": None,
        }

        result = await agent.run_task("device1", "goal", max_steps=5)

        assert result["success"] is False
        assert "Action mapping error" in result["message"]


# ---------------------------------------------------------------------------
# No old SYSTEM_PROMPT constant
# ---------------------------------------------------------------------------


class TestNoOldSystemPrompt:
    def test_no_system_prompt_constant(self):
        """SYSTEM_PROMPT should be removed — managed by GuiPlusClient."""
        import vision_agent

        assert not hasattr(vision_agent, "SYSTEM_PROMPT")
