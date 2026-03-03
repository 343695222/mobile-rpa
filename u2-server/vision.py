"""
GlmVisionClient - GLM-4.6V 视觉模型 Python 客户端
使用 httpx 流式调用，从 TypeScript vision-client.ts 迁移
"""

import os

import httpx


class GlmVisionClient:
    """GLM-4.6V 视觉模型客户端，使用 httpx 流式调用 SSE 接口。"""

    API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    TIMEOUT = 120.0  # seconds

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "glm-4.6v",
    ):
        self.api_key = api_key or os.environ.get("GLM_API_KEY", "")
        self.model = model

    async def analyze(self, base64_image: str, prompt: str) -> dict:
        """
        发送图片和 prompt 给 GLM-4.6V，流式接收并拼接结果。

        Returns:
            {"success": bool, "description": str, "model": str, "error"?: str}
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": 500,
            "stream": True,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": base64_image}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.TIMEOUT)) as client:
                async with client.stream("POST", self.API_URL, headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        return {
                            "success": False,
                            "description": "",
                            "model": self.model,
                            "error": f"API error {resp.status_code}: {body.decode(errors='replace')[:500]}",
                        }

                    content = await self._read_sse_stream(resp)

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
                "error": "API request timeout (120s)",
            }
        except Exception as exc:
            return {
                "success": False,
                "description": "",
                "model": self.model,
                "error": str(exc),
            }

    @staticmethod
    async def _read_sse_stream(resp: httpx.Response) -> str:
        """Parse SSE stream, extract choices[0].delta.content and concatenate."""
        import json

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
                delta = parsed.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if delta:
                    content += delta
            except (json.JSONDecodeError, IndexError, KeyError):
                pass  # skip malformed lines
        return content
