"""ApiStrategy — API 直连采集策略。

通过 HTTP 直接调用已知 API 端点获取数据。
explore 阶段无法自动发现 API，仅在有已知配置时可用。
execute 阶段按脚本中的 extraction.config 发起 HTTP 请求。
"""

from __future__ import annotations

from typing import Any

import httpx

from .base import BaseStrategy

# HTTP 请求超时（秒）
_REQUEST_TIMEOUT = 30.0


class ApiStrategy(BaseStrategy):
    """API 直连策略：直接调用已知 HTTP API 获取数据。"""

    strategy_name = "api"

    async def explore(
        self,
        device_id: str,
        app: str,
        data_type: str,
        query: str,
    ) -> dict[str, Any]:
        """API 策略无法自动探索，始终返回失败。

        API 端点需要人工配置或通过抓包获取，不支持自动发现。
        """
        return self._fail("API 策略不支持自动探索，需要已知 API 配置")

    async def execute(
        self,
        device_id: str,
        script: dict,
    ) -> dict[str, Any]:
        """按脚本中的 API 配置发起 HTTP 请求并提取数据。"""
        extraction = script.get("extraction", {})
        config = extraction.get("config", {})

        method = config.get("method", "GET")
        url = config.get("url", "")
        if not url:
            return self._fail("脚本缺少 API URL 配置")

        headers = config.get("headers", {})
        params = config.get("params")
        body = config.get("body")
        data_path = config.get("dataPath", "")

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            ) as client:
                resp = await client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=body if body else None,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            return self._fail(f"API 请求超时 ({_REQUEST_TIMEOUT}s): {url}")
        except httpx.HTTPStatusError as exc:
            return self._fail(
                f"API 返回错误 {exc.response.status_code}: {url}"
            )
        except Exception as exc:
            return self._fail(f"API 请求失败: {exc}")

        items = _extract_by_path(data, data_path)
        return self._ok(items)


def _extract_by_path(data: Any, path: str) -> list:
    """按点分隔路径从 JSON 数据中提取列表。

    例如 path="data.list" 会依次取 data["data"]["list"]。
    如果路径为空，直接返回顶层数据（包装为列表）。
    """
    if not path:
        return data if isinstance(data, list) else [data]

    current = data
    for key in path.split("."):
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and key.isdigit():
            idx = int(key)
            current = current[idx] if idx < len(current) else None
        else:
            return []
        if current is None:
            return []

    return current if isinstance(current, list) else [current]
