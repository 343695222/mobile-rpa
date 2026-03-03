"""AutoXDevice — 通过 AutoJS HTTP API 操作手机。

替代 uiautomator2，直接调用手机端 AutoJS 服务。
所有操作在手机本地执行，延迟极低。

AutoJS 服务通过 frp 隧道映射到 localhost:9501。
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# AutoJS 服务地址
# 方案 A/B: localhost:9501 (通过 SSH 隧道或 frp)
# 方案 C: 手机 IP:9500 (WiFi 直连)
# 可通过环境变量 AUTOX_URL 覆盖
import os
AUTOX_BASE_URL = os.environ.get("AUTOX_URL", "http://localhost:9501")
DEFAULT_TIMEOUT = 10.0


class AutoXDeviceError(Exception):
    """AutoJS 设备操作错误"""
    def __init__(self, message: str, detail: str = ""):
        self.message = message
        self.detail = detail
        super().__init__(f"{message}: {detail}" if detail else message)


class AutoXDevice:
    """AutoJS 设备操作封装。
    
    与 DeviceManager 接口兼容，可以直接替换。
    不需要 device_id 参数（AutoJS 只控制运行它的那台手机）。
    """
    
    def __init__(self, base_url: str = AUTOX_BASE_URL, timeout: float = DEFAULT_TIMEOUT):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))
        self._device_info: dict | None = None
    
    async def close(self) -> None:
        await self._client.aclose()
    
    async def _post(self, path: str, body: dict | None = None) -> dict:
        """发送 POST 请求到 AutoJS 服务"""
        url = f"{self._base_url}{path}"
        try:
            resp = await self._client.post(url, json=body or {})
            data = resp.json()
            if not data.get("success"):
                raise AutoXDeviceError(path, data.get("error", "Unknown error"))
            return data.get("data", {})
        except httpx.ConnectError as e:
            raise AutoXDeviceError("AutoJS 服务不可用", str(e)) from e
        except httpx.TimeoutException as e:
            raise AutoXDeviceError("AutoJS 请求超时", str(e)) from e
    
    # ------------------------------------------------------------------
    # 健康检查
    # ------------------------------------------------------------------
    
    async def health_check(self) -> bool:
        """检查 AutoJS 服务是否可用"""
        try:
            data = await self._post("/health")
            return data.get("status") == "running"
        except AutoXDeviceError:
            return False
    
    # ------------------------------------------------------------------
    # 设备信息
    # ------------------------------------------------------------------
    
    async def get_device_info(self) -> dict:
        """获取设备信息"""
        if self._device_info is None:
            self._device_info = await self._post("/device_info")
        return self._device_info
    
    @property
    async def info(self) -> dict:
        return await self.get_device_info()
    
    # ------------------------------------------------------------------
    # 截图
    # ------------------------------------------------------------------
    
    async def screenshot_base64(self) -> str:
        """截图并返回 base64 编码的 JPEG"""
        data = await self._post("/screenshot")
        return data.get("base64", "")
    
    async def screenshot_bytes(self) -> bytes:
        """截图并返回原始字节"""
        b64 = await self.screenshot_base64()
        return base64.b64decode(b64)
    
    # ------------------------------------------------------------------
    # 触摸操作
    # ------------------------------------------------------------------
    
    async def click(self, x: int, y: int) -> None:
        """点击指定坐标"""
        await self._post("/click", {"x": x, "y": y})
    
    async def long_click(self, x: int, y: int, duration: int = 500) -> None:
        """长按指定坐标"""
        await self._post("/long_click", {"x": x, "y": y, "duration": duration})
    
    async def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 500) -> None:
        """滑动"""
        await self._post("/swipe", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration": duration})
    
    async def scroll(self, direction: str = "down") -> None:
        """滚动屏幕 (up/down)"""
        await self._post("/scroll", {"direction": direction})
    
    # ------------------------------------------------------------------
    # 文本输入
    # ------------------------------------------------------------------
    
    async def input_text(self, text: str) -> None:
        """在当前焦点输入文本"""
        await self._post("/input", {"text": text})
    
    # ------------------------------------------------------------------
    # 按键
    # ------------------------------------------------------------------
    
    async def press_back(self) -> None:
        """按返回键"""
        await self._post("/key", {"key": "back"})
    
    async def press_home(self) -> None:
        """按 Home 键"""
        await self._post("/key", {"key": "home"})
    
    async def press_recents(self) -> None:
        """按最近任务键"""
        await self._post("/key", {"key": "recents"})
    
    async def key_event(self, key: str) -> None:
        """发送按键事件"""
        await self._post("/key", {"key": key})
    
    # ------------------------------------------------------------------
    # App 管理
    # ------------------------------------------------------------------
    
    async def app_start(self, package: str) -> None:
        """启动 App"""
        await self._post("/app/start", {"package": package})
    
    async def app_stop(self, package: str) -> None:
        """停止 App"""
        await self._post("/app/stop", {"package": package})
    
    async def current_app(self) -> dict:
        """获取当前前台 App"""
        return await self._post("/app/current")
    
    # ------------------------------------------------------------------
    # 元素操作
    # ------------------------------------------------------------------
    
    async def find_element(
        self, by: str, value: str, timeout: int = 3000
    ) -> dict | None:
        """查找元素
        
        Args:
            by: 选择器类型 (text/textContains/id/className/desc/descContains)
            value: 选择器值
            timeout: 超时毫秒数
        
        Returns:
            元素信息字典，未找到返回 None
        """
        data = await self._post("/find_element", {"by": by, "value": value, "timeout": timeout})
        if data.get("found"):
            return data.get("element")
        return None
    
    async def find_elements(self, by: str, value: str) -> list[dict]:
        """查找多个元素"""
        data = await self._post("/find_elements", {"by": by, "value": value})
        return data.get("elements", [])
    
    async def click_element(
        self, by: str, value: str, timeout: int = 3000
    ) -> bool:
        """查找并点击元素"""
        data = await self._post("/click_element", {"by": by, "value": value, "timeout": timeout})
        return data.get("clicked", False)
    
    async def wait_element(
        self, by: str, value: str, timeout: int = 10000
    ) -> dict | None:
        """等待元素出现"""
        data = await self._post("/wait_element", {"by": by, "value": value, "timeout": timeout})
        if data.get("found"):
            return data.get("element")
        return None
    
    # ------------------------------------------------------------------
    # UI 树
    # ------------------------------------------------------------------
    
    async def ui_tree(self, max_depth: int = 3) -> dict:
        """获取 UI 树"""
        return await self._post("/ui_tree", {"maxDepth": max_depth})
    
    # ------------------------------------------------------------------
    # OCR
    # ------------------------------------------------------------------
    
    async def ocr(self) -> list[dict]:
        """截图 + OCR 识别"""
        data = await self._post("/ocr")
        return data.get("texts", [])
    
    # ------------------------------------------------------------------
    # 剪贴板
    # ------------------------------------------------------------------
    
    async def get_clipboard(self) -> str:
        """读取剪贴板"""
        data = await self._post("/clipboard", {})
        return data.get("text", "")
    
    async def set_clipboard(self, text: str) -> None:
        """写入剪贴板"""
        await self._post("/clipboard", {"text": text})
    
    # ------------------------------------------------------------------
    # 自定义脚本
    # ------------------------------------------------------------------
    
    async def run_script(self, script: str) -> Any:
        """执行自定义 JavaScript 脚本"""
        data = await self._post("/run_script", {"script": script})
        return data.get("result")


# 单例，方便直接使用
_default_device: AutoXDevice | None = None


def get_autox_device(base_url: str = AUTOX_BASE_URL) -> AutoXDevice:
    """获取默认的 AutoXDevice 实例"""
    global _default_device
    if _default_device is None:
        _default_device = AutoXDevice(base_url)
    return _default_device
