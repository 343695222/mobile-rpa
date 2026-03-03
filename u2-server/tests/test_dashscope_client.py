"""
GuiPlusClient 单元测试

测试 smart_size 坐标映射、_build_messages 消息构建、
_parse_response 响应解析、decide 方法的错误处理等。
"""

import json
import os

import httpx
import pytest

from dashscope_client import GUI_PLUS_SYSTEM_PROMPT, GuiPlusClient


# ---------------------------------------------------------------------------
# Construction & config
# ---------------------------------------------------------------------------


class TestGuiPlusClientInit:
    def test_default_values(self):
        client = GuiPlusClient(api_key="test-key")
        assert client.api_key == "test-key"
        assert client.model == "gui-plus"
        assert client.high_resolution is True

    def test_custom_model(self):
        client = GuiPlusClient(api_key="k", model="gui-plus-v2")
        assert client.model == "gui-plus-v2"

    def test_high_resolution_disabled(self):
        client = GuiPlusClient(api_key="k", high_resolution=False)
        assert client.high_resolution is False

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("DASHSCOPE_API_KEY", "env-key-123")
        client = GuiPlusClient()
        assert client.api_key == "env-key-123"

    def test_api_key_param_overrides_env(self, monkeypatch):
        monkeypatch.setenv("DASHSCOPE_API_KEY", "env-key")
        client = GuiPlusClient(api_key="param-key")
        assert client.api_key == "param-key"


# ---------------------------------------------------------------------------
# GUI_PLUS_SYSTEM_PROMPT
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    def test_prompt_is_string(self):
        assert isinstance(GUI_PLUS_SYSTEM_PROMPT, str)
        assert len(GUI_PLUS_SYSTEM_PROMPT) > 100

    def test_prompt_contains_action_types(self):
        for action in ["CLICK", "TYPE", "SCROLL", "KEY_PRESS", "FINISH", "FAIL"]:
            assert action in GUI_PLUS_SYSTEM_PROMPT

    def test_prompt_contains_json_format(self):
        assert '"thought"' in GUI_PLUS_SYSTEM_PROMPT
        assert '"action"' in GUI_PLUS_SYSTEM_PROMPT
        assert '"parameters"' in GUI_PLUS_SYSTEM_PROMPT

    def test_prompt_contains_mobile_guidance(self):
        assert "状态栏" in GUI_PLUS_SYSTEM_PROMPT
        assert "导航栏" in GUI_PLUS_SYSTEM_PROMPT
        assert "虚拟键盘" in GUI_PLUS_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# smart_size
# ---------------------------------------------------------------------------


class TestSmartSize:
    def test_landscape_larger_than_max(self):
        # 1920x1080, max_pixels=1344 → scale = 1920/1344 ≈ 1.4286
        x, y = GuiPlusClient.smart_size(1920, 1080, 672, 540)
        assert x == round(672 * (1920 / 1344))
        assert y == round(540 * (1920 / 1344))

    def test_portrait_larger_than_max(self):
        # 1080x1920, max_pixels=1344 → scale = 1920/1344
        x, y = GuiPlusClient.smart_size(1080, 1920, 540, 672)
        assert x == round(540 * (1920 / 1344))
        assert y == round(672 * (1920 / 1344))

    def test_small_image_no_scale(self):
        # 800x600, both < 1344 → scale = 1
        x, y = GuiPlusClient.smart_size(800, 600, 400, 300)
        assert x == 400
        assert y == 300

    def test_clamp_to_bounds(self):
        # Coordinates that would exceed screen bounds after mapping
        x, y = GuiPlusClient.smart_size(1920, 1080, 2000, 2000)
        assert x == 1919  # clamped to width - 1
        assert y == 1079  # clamped to height - 1

    def test_zero_coordinates(self):
        x, y = GuiPlusClient.smart_size(1920, 1080, 0, 0)
        assert x == 0
        assert y == 0

    def test_custom_max_pixels(self):
        x, y = GuiPlusClient.smart_size(2000, 1000, 500, 250, max_pixels=1000)
        # scale = 2000/1000 = 2.0
        assert x == 1000
        assert y == 500


# ---------------------------------------------------------------------------
# _build_messages
# ---------------------------------------------------------------------------


class TestBuildMessages:
    def setup_method(self):
        self.client = GuiPlusClient(api_key="test")

    def test_basic_structure(self):
        msgs = self.client._build_messages("aGVsbG8=", "click the button", None)
        assert len(msgs) == 2  # system + user
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == GUI_PLUS_SYSTEM_PROMPT
        assert msgs[1]["role"] == "user"

    def test_user_message_content(self):
        msgs = self.client._build_messages("aGVsbG8=", "open settings", None)
        user_content = msgs[1]["content"]
        assert isinstance(user_content, list)
        assert len(user_content) == 2
        assert user_content[0]["type"] == "image_url"
        assert user_content[1]["type"] == "text"
        assert user_content[1]["text"] == "open settings"

    def test_adds_data_uri_prefix(self):
        msgs = self.client._build_messages("aGVsbG8=", "task", None)
        image_url = msgs[1]["content"][0]["image_url"]["url"]
        assert image_url.startswith("data:image/png;base64,")

    def test_preserves_existing_data_uri(self):
        data_uri = "data:image/jpeg;base64,/9j/4AAQ"
        msgs = self.client._build_messages(data_uri, "task", None)
        image_url = msgs[1]["content"][0]["image_url"]["url"]
        assert image_url == data_uri

    def test_with_history(self):
        history = [
            {"role": "user", "content": "previous screenshot"},
            {"role": "assistant", "content": '{"thought":"...", "action":"CLICK", "parameters":{"x":1,"y":2}}'},
        ]
        msgs = self.client._build_messages("aGVsbG8=", "next step", history)
        assert len(msgs) == 4  # system + 2 history + user
        assert msgs[1] == history[0]
        assert msgs[2] == history[1]
        assert msgs[3]["role"] == "user"


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------


class TestParseResponse:
    def setup_method(self):
        self.client = GuiPlusClient(api_key="test")

    def test_valid_click(self):
        raw = json.dumps({"thought": "点击按钮", "action": "CLICK", "parameters": {"x": 100, "y": 200}})
        result = self.client._parse_response(raw)
        assert result["success"] is True
        assert result["thought"] == "点击按钮"
        assert result["action"] == "CLICK"
        assert result["parameters"] == {"x": 100, "y": 200}
        assert result["error"] is None

    def test_valid_type(self):
        raw = json.dumps({"thought": "输入文本", "action": "TYPE", "parameters": {"text": "hello"}})
        result = self.client._parse_response(raw)
        assert result["success"] is True
        assert result["action"] == "TYPE"

    def test_valid_finish(self):
        raw = json.dumps({"thought": "任务完成", "action": "FINISH", "parameters": {}})
        result = self.client._parse_response(raw)
        assert result["success"] is True
        assert result["action"] == "FINISH"

    def test_action_case_insensitive(self):
        raw = json.dumps({"thought": "...", "action": "click", "parameters": {"x": 1, "y": 2}})
        result = self.client._parse_response(raw)
        assert result["action"] == "CLICK"

    def test_json_in_markdown_code_block(self):
        raw = '```json\n{"thought": "思考", "action": "SCROLL", "parameters": {"x": 540, "y": 960, "direction": "up"}}\n```'
        result = self.client._parse_response(raw)
        assert result["success"] is True
        assert result["action"] == "SCROLL"

    def test_json_with_surrounding_text(self):
        raw = 'Here is my response: {"thought": "ok", "action": "FINISH", "parameters": {}} end'
        result = self.client._parse_response(raw)
        assert result["success"] is True
        assert result["action"] == "FINISH"

    def test_empty_response(self):
        result = self.client._parse_response("")
        assert result["success"] is False
        assert "Empty response" in result["error"]

    def test_non_json_response(self):
        result = self.client._parse_response("I cannot help with that.")
        assert result["success"] is False
        assert "not valid JSON" in result["error"]

    def test_missing_action_field(self):
        raw = json.dumps({"thought": "thinking", "parameters": {"x": 1}})
        result = self.client._parse_response(raw)
        assert result["success"] is False
        assert "missing 'action'" in result["error"]

    def test_missing_thought_defaults_empty(self):
        raw = json.dumps({"action": "FINISH", "parameters": {}})
        result = self.client._parse_response(raw)
        assert result["success"] is True
        assert result["thought"] == ""

    def test_missing_parameters_defaults_empty(self):
        raw = json.dumps({"thought": "done", "action": "FINISH"})
        result = self.client._parse_response(raw)
        assert result["success"] is True
        assert result["parameters"] == {}

    def test_raw_response_preserved(self):
        raw = json.dumps({"thought": "t", "action": "CLICK", "parameters": {"x": 0, "y": 0}})
        result = self.client._parse_response(raw)
        assert result["raw_response"] == raw


# ---------------------------------------------------------------------------
# decide - error handling (mocked network)
# ---------------------------------------------------------------------------


class TestDecideErrors:
    """Test decide() error paths without real network calls."""

    @pytest.mark.asyncio
    async def test_timeout_error(self, monkeypatch):
        client = GuiPlusClient(api_key="test-key")

        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            original_init(self_client, *args, **kwargs)

            async def _raise_timeout(*a, **kw):
                raise httpx.TimeoutException("timed out")

            self_client.send = _raise_timeout

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        result = await client.decide("aGVsbG8=", "do something")
        assert result["success"] is False
        assert "timeout" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_connection_error(self, monkeypatch):
        client = GuiPlusClient(api_key="test-key")

        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            original_init(self_client, *args, **kwargs)

            async def _raise_connect(*a, **kw):
                raise httpx.ConnectError("connection refused")

            self_client.send = _raise_connect

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        result = await client.decide("aGVsbG8=", "do something")
        assert result["success"] is False
        assert "Cannot connect" in result["error"]
        assert client.BASE_URL in result["error"]


# ---------------------------------------------------------------------------
# DashScopeVLClient tests
# ---------------------------------------------------------------------------

from dashscope_client import DashScopeVLClient


class TestDashScopeVLClientInit:
    def test_default_values(self):
        client = DashScopeVLClient(api_key="test-key")
        assert client.api_key == "test-key"
        assert client.model == "qwen-vl-max"

    def test_custom_model(self):
        client = DashScopeVLClient(api_key="k", model="qwen-vl-plus")
        assert client.model == "qwen-vl-plus"

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("DASHSCOPE_API_KEY", "env-vl-key")
        client = DashScopeVLClient()
        assert client.api_key == "env-vl-key"

    def test_api_key_param_overrides_env(self, monkeypatch):
        monkeypatch.setenv("DASHSCOPE_API_KEY", "env-key")
        client = DashScopeVLClient(api_key="param-key")
        assert client.api_key == "param-key"

    def test_base_url(self):
        assert DashScopeVLClient.BASE_URL == "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def test_timeout(self):
        assert DashScopeVLClient.TIMEOUT == 120.0


class TestDashScopeVLClientAnalyze:
    """Test analyze() return format and error handling."""

    @pytest.mark.asyncio
    async def test_timeout_error(self, monkeypatch):
        client = DashScopeVLClient(api_key="test-key")

        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            original_init(self_client, *args, **kwargs)

            async def _raise_timeout(*a, **kw):
                raise httpx.TimeoutException("timed out")

            self_client.send = _raise_timeout

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        result = await client.analyze("aGVsbG8=", "describe the screen")
        assert result["success"] is False
        assert result["description"] == ""
        assert result["model"] == "qwen-vl-max"
        assert "timeout" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_connection_error(self, monkeypatch):
        client = DashScopeVLClient(api_key="test-key")

        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            original_init(self_client, *args, **kwargs)

            async def _raise_connect(*a, **kw):
                raise httpx.ConnectError("connection refused")

            self_client.send = _raise_connect

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        result = await client.analyze("aGVsbG8=", "describe the screen")
        assert result["success"] is False
        assert result["description"] == ""
        assert "Cannot connect" in result["error"]
        assert client.BASE_URL in result["error"]

    @pytest.mark.asyncio
    async def test_generic_exception(self, monkeypatch):
        client = DashScopeVLClient(api_key="test-key")

        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            original_init(self_client, *args, **kwargs)

            async def _raise_generic(*a, **kw):
                raise RuntimeError("something broke")

            self_client.send = _raise_generic

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        result = await client.analyze("aGVsbG8=", "describe the screen")
        assert result["success"] is False
        assert result["description"] == ""
        assert "RuntimeError" in result["error"]

    @pytest.mark.asyncio
    async def test_return_format_matches_glm(self, monkeypatch):
        """Verify the return dict has the same keys as GlmVisionClient.analyze."""
        client = DashScopeVLClient(api_key="test-key")

        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            original_init(self_client, *args, **kwargs)

            async def _raise(*a, **kw):
                raise httpx.TimeoutException("t")

            self_client.send = _raise

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        result = await client.analyze("aGVsbG8=", "test")
        # Must have these keys (same as GlmVisionClient)
        assert "success" in result
        assert "description" in result
        assert "model" in result
        assert isinstance(result["success"], bool)
        assert isinstance(result["description"], str)
        assert isinstance(result["model"], str)


# ---------------------------------------------------------------------------
# DashScopeTextClient tests
# ---------------------------------------------------------------------------

from dashscope_client import DashScopeTextClient


class TestDashScopeTextClientInit:
    def test_default_values(self):
        client = DashScopeTextClient(api_key="test-key")
        assert client.api_key == "test-key"
        assert client.model == "qwen-turbo"

    def test_custom_model(self):
        client = DashScopeTextClient(api_key="k", model="qwen-plus")
        assert client.model == "qwen-plus"

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("DASHSCOPE_API_KEY", "env-text-key")
        client = DashScopeTextClient()
        assert client.api_key == "env-text-key"

    def test_api_key_param_overrides_env(self, monkeypatch):
        monkeypatch.setenv("DASHSCOPE_API_KEY", "env-key")
        client = DashScopeTextClient(api_key="param-key")
        assert client.api_key == "param-key"

    def test_base_url(self):
        assert DashScopeTextClient.BASE_URL == "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def test_timeout_is_30(self):
        assert DashScopeTextClient.TIMEOUT == 30.0


class TestDashScopeTextClientChat:
    """Test chat() return value and error handling."""

    @pytest.mark.asyncio
    async def test_timeout_returns_empty_string(self, monkeypatch):
        client = DashScopeTextClient(api_key="test-key")

        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            original_init(self_client, *args, **kwargs)

            async def _raise_timeout(*a, **kw):
                raise httpx.TimeoutException("timed out")

            self_client.send = _raise_timeout

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        result = await client.chat([{"role": "user", "content": "hello"}])
        assert result == ""

    @pytest.mark.asyncio
    async def test_connection_error_returns_empty_string(self, monkeypatch):
        client = DashScopeTextClient(api_key="test-key")

        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            original_init(self_client, *args, **kwargs)

            async def _raise_connect(*a, **kw):
                raise httpx.ConnectError("connection refused")

            self_client.send = _raise_connect

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        result = await client.chat([{"role": "user", "content": "hello"}])
        assert result == ""

    @pytest.mark.asyncio
    async def test_generic_exception_returns_empty_string(self, monkeypatch):
        client = DashScopeTextClient(api_key="test-key")

        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            original_init(self_client, *args, **kwargs)

            async def _raise_generic(*a, **kw):
                raise RuntimeError("something broke")

            self_client.send = _raise_generic

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        result = await client.chat([{"role": "user", "content": "hello"}])
        assert result == ""

    @pytest.mark.asyncio
    async def test_successful_response(self, monkeypatch):
        client = DashScopeTextClient(api_key="test-key")

        mock_response_data = {
            "choices": [
                {"message": {"role": "assistant", "content": "你好！有什么可以帮你的？"}}
            ]
        }

        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            original_init(self_client, *args, **kwargs)

            async def _mock_send(request, **kw):
                return httpx.Response(
                    status_code=200,
                    json=mock_response_data,
                    request=request,
                )

            self_client.send = _mock_send

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        result = await client.chat([{"role": "user", "content": "你好"}])
        assert result == "你好！有什么可以帮你的？"

    @pytest.mark.asyncio
    async def test_http_error_returns_empty_string(self, monkeypatch):
        client = DashScopeTextClient(api_key="test-key")

        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            original_init(self_client, *args, **kwargs)

            async def _mock_send(request, **kw):
                return httpx.Response(
                    status_code=429,
                    text="rate limited",
                    request=request,
                )

            self_client.send = _mock_send

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        result = await client.chat([{"role": "user", "content": "hello"}])
        assert result == ""

    @pytest.mark.asyncio
    async def test_empty_choices_returns_empty_string(self, monkeypatch):
        client = DashScopeTextClient(api_key="test-key")

        mock_response_data = {"choices": []}

        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            original_init(self_client, *args, **kwargs)

            async def _mock_send(request, **kw):
                return httpx.Response(
                    status_code=200,
                    json=mock_response_data,
                    request=request,
                )

            self_client.send = _mock_send

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        result = await client.chat([{"role": "user", "content": "hello"}])
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_string_type(self, monkeypatch):
        client = DashScopeTextClient(api_key="test-key")

        mock_response_data = {
            "choices": [{"message": {"role": "assistant", "content": "response"}}]
        }

        original_init = httpx.AsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            original_init(self_client, *args, **kwargs)

            async def _mock_send(request, **kw):
                return httpx.Response(
                    status_code=200,
                    json=mock_response_data,
                    request=request,
                )

            self_client.send = _mock_send

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        result = await client.chat([{"role": "user", "content": "test"}])
        assert isinstance(result, str)
