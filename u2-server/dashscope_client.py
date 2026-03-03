"""
DashScope 百炼平台模型客户端模块

GuiPlusClient - GUI-Plus 模型客户端，专用于 GUI 操作决策
DashScopeVLClient / DashScopeTextClient 将在后续任务中添加
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GUI-Plus 手机场景系统提示词
# ---------------------------------------------------------------------------

GUI_PLUS_SYSTEM_PROMPT = """你是一个手机自动化操作助手。你会收到一张 Android 手机的屏幕截图和一个任务目标，你需要分析当前屏幕内容并决定下一步操作。

## 操作类型

你可以执行以下操作：

1. **CLICK** - 点击屏幕上的某个位置
   参数: {"x": <int>, "y": <int>}

2. **TYPE** - 输入文本（在当前焦点输入框中输入）
   参数: {"text": "<要输入的文本>"}

3. **SCROLL** - 滑动屏幕
   参数: {"x": <int>, "y": <int>, "direction": "<up|down|left|right>"}
   - up: 向上滑动（查看下方内容）
   - down: 向下滑动（查看上方内容）
   - left: 向左滑动
   - right: 向右滑动

4. **KEY_PRESS** - 按下物理/虚拟按键
   参数: {"key": "<按键名>"}
   支持的按键: enter, back, home, recents, volume_up, volume_down, power, delete, tab, space, escape

5. **FINISH** - 任务已完成
   参数: {}

6. **FAIL** - 任务无法完成
   参数: {}

## 输出格式

你必须严格按照以下 JSON 格式输出，不要输出其他内容：

```json
{"thought": "你的思考过程，描述当前屏幕状态和决策理由", "action": "操作类型", "parameters": {操作参数}}
```

## 手机 UI 操作指南

- **状态栏**: 屏幕顶部的状态栏显示时间、信号、电量等信息，通常不需要操作
- **导航栏**: 屏幕底部可能有虚拟导航栏（返回、主页、最近任务），可通过 KEY_PRESS 操作
- **虚拟键盘**: 当需要输入文本时，先 CLICK 输入框使其获得焦点，然后使用 TYPE 输入文本
- **弹窗/对话框**: 注意识别权限请求、确认对话框等弹窗，优先处理弹窗
- **加载状态**: 如果页面正在加载，可能需要等待（通过再次截图观察）

## 决策框架

1. 仔细观察当前屏幕截图
2. 理解任务目标和当前进度
3. 确定当前屏幕上需要操作的元素
4. 选择最合适的操作类型
5. 精确定位操作坐标（对于 CLICK 和 SCROLL）
6. 如果任务已完成，使用 FINISH；如果确定无法完成，使用 FAIL
"""


# ---------------------------------------------------------------------------
# GuiPlusClient
# ---------------------------------------------------------------------------


class GuiPlusClient:
    """GUI-Plus 模型客户端，专用于 GUI 操作决策。

    通过阿里云百炼平台 OpenAI 兼容 API 调用 gui-plus 模型，
    获取结构化的 GUI 操作指令（CLICK/TYPE/SCROLL/KEY_PRESS/FINISH/FAIL）。
    """

    BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    TIMEOUT = 120.0

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gui-plus",
        high_resolution: bool = True,
    ):
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        self.model = model
        self.high_resolution = high_resolution

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    async def decide(
        self,
        base64_image: str,
        task_prompt: str,
        history: list[dict] | None = None,
    ) -> dict:
        """发送截图和任务描述给 GUI-Plus，获取操作决策。

        Args:
            base64_image: base64 编码的截图（PNG/JPEG），可带 data URI 前缀
            task_prompt: 当前任务目标描述
            history: 之前的对话历史（多轮对话）

        Returns:
            {
                "success": bool,
                "thought": str,
                "action": str,         # CLICK/TYPE/SCROLL/KEY_PRESS/FINISH/FAIL
                "parameters": dict,    # 操作参数（坐标已经过 smart_size 映射）
                "raw_response": str,
                "error": str | None,
            }
        """
        messages = self._build_messages(base64_image, task_prompt, history)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict = {
            "model": self.model,
            "stream": True,
            "messages": messages,
        }
        if self.high_resolution:
            payload["vl_high_resolution_images"] = True

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.TIMEOUT),
            ) as client:
                async with client.stream(
                    "POST",
                    f"{self.BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        return self._error_result(
                            f"API error {resp.status_code}: "
                            f"{body.decode(errors='replace')[:500]}"
                        )

                    raw_text = await self._read_sse_stream(resp)

            return self._parse_response(raw_text)

        except httpx.TimeoutException:
            return self._error_result(
                f"API request timeout ({self.TIMEOUT}s)"
            )
        except httpx.ConnectError as exc:
            return self._error_result(
                f"Cannot connect to {self.BASE_URL}: {type(exc).__name__}"
            )
        except Exception as exc:
            return self._error_result(
                f"Request failed: {type(exc).__name__}: {exc}"
            )

    # ------------------------------------------------------------------
    # smart_size coordinate mapping
    # ------------------------------------------------------------------

    @staticmethod
    def smart_size(
        original_width: int,
        original_height: int,
        model_x: int,
        model_y: int,
        max_pixels: int = 1344,
    ) -> tuple[int, int]:
        """将 GUI-Plus 返回的坐标映射回原始屏幕分辨率。

        GUI-Plus 内部将图片最长边缩放到 *max_pixels*，等比缩放。
        此函数根据原始尺寸和缩放规则，反算出实际屏幕坐标。

        Algorithm:
            1. scale = max(original_width, original_height) / max_pixels
               if scale < 1: scale = 1
            2. actual_x = round(model_x * scale)
               actual_y = round(model_y * scale)
            3. clamp to [0, original_width-1] / [0, original_height-1]
        """
        if original_width >= original_height:
            scale = original_width / max_pixels
        else:
            scale = original_height / max_pixels

        if scale < 1:
            scale = 1.0

        actual_x = round(model_x * scale)
        actual_y = round(model_y * scale)

        actual_x = max(0, min(actual_x, original_width - 1))
        actual_y = max(0, min(actual_y, original_height - 1))

        return actual_x, actual_y

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        base64_image: str,
        task_prompt: str,
        history: list[dict] | None,
    ) -> list[dict]:
        """构建 OpenAI 兼容的消息列表。"""
        messages: list[dict] = [
            {"role": "system", "content": GUI_PLUS_SYSTEM_PROMPT},
        ]

        # 追加历史对话
        if history:
            messages.extend(history)

        # 确保 base64 图片带 data URI 前缀
        image_url = base64_image
        if not base64_image.startswith("data:"):
            image_url = f"data:image/png;base64,{base64_image}"

        # 当前轮：截图 + 任务描述
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url},
                    },
                    {
                        "type": "text",
                        "text": task_prompt,
                    },
                ],
            }
        )

        return messages

    def _parse_response(self, raw_text: str) -> dict:
        """解析 GUI-Plus 的 JSON 响应。

        尝试从模型输出中提取 JSON 对象，解析 thought/action/parameters 字段。
        对 CLICK 和 SCROLL 操作自动应用 smart_size 坐标映射（需要调用方
        在外部提供原始尺寸，此处仅做 JSON 解析）。
        """
        if not raw_text.strip():
            logger.warning("GUI-Plus returned empty response")
            return self._error_result("Empty response from model", raw=raw_text)

        # 尝试提取 JSON（模型可能在 JSON 前后输出额外文本或 markdown 代码块）
        json_obj = self._extract_json(raw_text)
        if json_obj is None:
            logger.warning("GUI-Plus response is not valid JSON: %s", raw_text[:200])
            return self._error_result(
                "Response is not valid JSON format",
                raw=raw_text,
            )

        action = json_obj.get("action")
        if not action:
            logger.warning(
                "GUI-Plus response missing 'action' field. Got keys: %s",
                list(json_obj.keys()),
            )
            return self._error_result(
                f"Response missing 'action' field, got keys: {list(json_obj.keys())}",
                raw=raw_text,
            )

        return {
            "success": True,
            "thought": json_obj.get("thought", ""),
            "action": str(action).upper(),
            "parameters": json_obj.get("parameters", {}),
            "raw_response": raw_text,
            "error": None,
        }

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """从文本中提取第一个 JSON 对象。"""
        # 1. 尝试直接解析
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # 2. 尝试从 markdown 代码块中提取
        code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 3. 尝试匹配第一个 { ... } 块
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    async def _read_sse_stream(resp: httpx.Response) -> str:
        """解析 SSE 流，拼接 choices[0].delta.content。"""
        content = ""
        async for line in resp.aiter_lines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            json_str = line[5:].strip()
            if json_str == "[DONE]":
                continue
            try:
                parsed = json.loads(json_str)
                delta = (
                    parsed.get("choices", [{}])[0]
                    .get("delta", {})
                    .get("content", "")
                )
                if delta:
                    content += delta
            except (json.JSONDecodeError, IndexError, KeyError):
                pass
        return content

    @staticmethod
    def _error_result(error: str, *, raw: str = "") -> dict:
        """构造统一的错误返回结构。"""
        return {
            "success": False,
            "thought": "",
            "action": "",
            "parameters": {},
            "raw_response": raw,
            "error": error,
        }

# ---------------------------------------------------------------------------
# DashScopeVLClient
# ---------------------------------------------------------------------------


class DashScopeVLClient:
    """通义千问 VL 模型客户端，用于通用屏幕内容分析。

    提供与 GlmVisionClient 相同的 analyze 接口，作为直接替换。
    """

    BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    TIMEOUT = 120.0

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "qwen-vl-max",
    ):
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        self.model = model

    async def analyze(self, base64_image: str, prompt: str) -> dict:
        """与 GlmVisionClient.analyze 接口完全兼容。

        Args:
            base64_image: base64 编码的截图，可带 data URI 前缀
            prompt: 分析提示词

        Returns:
            {"success": bool, "description": str, "model": str, "error"?: str}
        """
        # 确保 base64 图片带 data URI 前缀
        image_url = base64_image
        if not base64_image.startswith("data:"):
            image_url = f"data:image/png;base64,{base64_image}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "stream": True,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.TIMEOUT),
            ) as client:
                async with client.stream(
                    "POST",
                    f"{self.BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        return {
                            "success": False,
                            "description": "",
                            "model": self.model,
                            "error": (
                                f"API error {resp.status_code}: "
                                f"{body.decode(errors='replace')[:500]}"
                            ),
                        }

                    content = await GuiPlusClient._read_sse_stream(resp)

            return {
                "success": True,
                "description": content,
                "model": self.model,
            }

        except httpx.TimeoutException:
            return {
                "success": False,
                "description": "",
                "model": self.model,
                "error": f"API request timeout ({self.TIMEOUT}s)",
            }
        except httpx.ConnectError as exc:
            return {
                "success": False,
                "description": "",
                "model": self.model,
                "error": (
                    f"Cannot connect to {self.BASE_URL}: "
                    f"{type(exc).__name__}"
                ),
            }
        except Exception as exc:
            return {
                "success": False,
                "description": "",
                "model": self.model,
                "error": f"Request failed: {type(exc).__name__}: {exc}",
            }


# ---------------------------------------------------------------------------
# DashScopeTextClient
# ---------------------------------------------------------------------------


class DashScopeTextClient:
    """通义千问文本模型客户端，用于意图理解和结果摘要。"""

    BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    TIMEOUT = 30.0

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "qwen-turbo",
    ):
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        self.model = model

    async def chat(self, messages: list[dict]) -> str:
        """发送对话消息，返回模型文本响应。

        Args:
            messages: OpenAI 格式的消息列表 [{"role": "...", "content": "..."}]

        Returns:
            模型响应文本字符串。失败时返回空字符串并记录日志。
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.TIMEOUT),
            ) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )

                if resp.status_code != 200:
                    logger.error(
                        "DashScopeTextClient API error %d: %s",
                        resp.status_code,
                        resp.text[:500],
                    )
                    return ""

                data = resp.json()
                return (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )

        except httpx.TimeoutException:
            logger.error(
                "DashScopeTextClient request timeout (%ss)", self.TIMEOUT
            )
            return ""
        except httpx.ConnectError as exc:
            logger.error(
                "DashScopeTextClient cannot connect to %s: %s",
                self.BASE_URL,
                exc,
            )
            return ""
        except Exception as exc:
            logger.error(
                "DashScopeTextClient request failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            return ""
