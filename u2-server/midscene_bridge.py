"""
MidsceneBridge — Python 端调用 Midscene TypeScript 服务的桥接层。

通过 HTTP 调用 src/midscene-client.ts 暴露的 REST API，
提供 aiAct / aiQuery / aiAssert 三大能力。
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:9401"
DEFAULT_TIMEOUT = 180.0  # Midscene 操作可能较慢


class MidsceneBridge:
    """Midscene TypeScript 服务的 Python 客户端。"""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url or os.environ.get(
            "MIDSCENE_BRIDGE_URL", DEFAULT_BASE_URL
        )
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Health & connection
    # ------------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        """检查 Midscene 服务是否运行。"""
        return await self._get("/health")

    async def connect(self) -> dict[str, Any]:
        """连接 Android 设备。"""
        return await self._post("/connect")

    async def disconnect(self) -> dict[str, Any]:
        """断开设备连接。"""
        return await self._post("/disconnect")

    # ------------------------------------------------------------------
    # Core AI operations
    # ------------------------------------------------------------------

    async def ai_act(self, instruction: str) -> dict[str, Any]:
        """执行自然语言 GUI 操作指令。

        Examples:
            await bridge.ai_act("点击微信")
            await bridge.ai_act("在搜索框输入'张三'然后点击搜索")
        """
        return await self._post("/ai/act", {"instruction": instruction})

    async def ai_query(self, data_demand: str) -> dict[str, Any]:
        """结构化数据提取。

        data_demand 可以是自然语言描述，Midscene 会返回结构化 JSON。

        Examples:
            await bridge.ai_query("当前聊天列表中所有联系人的名字和最后一条消息")
            await bridge.ai_query("屏幕上所有商品的名称和价格")
        """
        return await self._post("/ai/query", {"dataDemand": data_demand})

    async def ai_assert(self, assertion: str) -> dict[str, Any]:
        """屏幕状态断言。

        Examples:
            await bridge.ai_assert("当前页面是微信聊天列表")
            await bridge.ai_assert("搜索结果中包含'张三'")
        """
        return await self._post("/ai/assert", {"assertion": assertion})

    async def screenshot(self) -> dict[str, Any]:
        """获取当前屏幕截图（base64）。"""
        return await self._get("/screenshot")

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _get(self, path: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}{path}")
                return resp.json()
        except httpx.ConnectError:
            return {"success": False, "error": f"无法连接 Midscene 服务 ({self.base_url})"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _post(self, path: str, body: dict | None = None) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}{path}",
                    json=body or {},
                )
                return resp.json()
        except httpx.ConnectError:
            return {"success": False, "error": f"无法连接 Midscene 服务 ({self.base_url})"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
