"""FastAPI server — AutoJS 模式。

直接调用手机端 AutoJS 服务，不依赖 ADB/uiautomator2。
更简单、更快、延迟更低。

端口: 9400
AutoJS 服务: localhost:9501 (frp 映射)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from action_mapper import KEY_MAP
from autox_device import AutoXDevice, AutoXDeviceError
from dashscope_client import DashScopeVLClient, GuiPlusClient
from safety_guard import SafetyGuard
from vision_agent import VisionAgent

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ClickRequest(BaseModel):
    x: int
    y: int


class LongClickRequest(BaseModel):
    x: int
    y: int
    duration: int = 500


class SwipeRequest(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    duration: int = 500


class ScrollRequest(BaseModel):
    direction: str = "down"


class InputTextRequest(BaseModel):
    text: str


class KeyRequest(BaseModel):
    key: str = "back"


class PackageRequest(BaseModel):
    package: str


class FindElementRequest(BaseModel):
    by: str
    value: str
    timeout: int = 3000


class ClipboardRequest(BaseModel):
    text: str | None = None


class RunScriptRequest(BaseModel):
    script: str


class VisionAnalyzeRequest(BaseModel):
    prompt: str = "请描述屏幕上的内容"


class SmartTaskRequest(BaseModel):
    goal: str
    max_steps: int = 20


class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Any = None


# ---------------------------------------------------------------------------
# App & shared state
# ---------------------------------------------------------------------------

app = FastAPI(title="AutoX Service", version="2.0.0")

# AutoJS 设备（单设备模式）
autox = AutoXDevice()

# Safety guard
safety_guard = SafetyGuard(mode="strict")

# Vision components (require DASHSCOPE_API_KEY)
_dashscope_api_key = os.environ.get("DASHSCOPE_API_KEY", "")
_gui_model = os.environ.get("DASHSCOPE_GUI_MODEL", "gui-plus")
_vl_model = os.environ.get("DASHSCOPE_VL_MODEL", "qwen-vl-max")

if not _dashscope_api_key:
    _logger.warning(
        "DASHSCOPE_API_KEY is not set — vision and smart task endpoints will not work"
    )

gui_plus_client = GuiPlusClient(api_key=_dashscope_api_key, model=_gui_model)
vl_client = DashScopeVLClient(api_key=_dashscope_api_key, model=_vl_model)


# ---------------------------------------------------------------------------
# AutoXVisionAgent — adapts VisionAgent for async AutoXDevice
# ---------------------------------------------------------------------------


class AutoXVisionAgent(VisionAgent):
    """VisionAgent subclass that works with AutoXDevice's async interface.

    Overrides screenshot and action execution to use AutoXDevice instead of
    the sync DeviceManager.
    """

    def __init__(
        self,
        autox_device: AutoXDevice,
        gui_plus_client: GuiPlusClient,
        safety_guard: SafetyGuard | None = None,
    ) -> None:
        # Pass None for device_manager — we override the methods that use it
        super().__init__(
            device_manager=None,  # type: ignore[arg-type]
            gui_plus_client=gui_plus_client,
            safety_guard=safety_guard,
        )
        self.autox = autox_device

    async def decide_next_action(
        self,
        device_id: str,
        goal: str,
        history: list[dict],
    ) -> dict[str, Any]:
        """Screenshot via AutoXDevice → GuiPlusClient.decide → parse."""
        try:
            base64_img = await self.autox.screenshot_base64()
            result = await self.gui_plus_client.decide(base64_img, goal, history)
            return self._parse_gui_plus_response(result)
        except Exception as exc:
            return {
                "success": False,
                "action": None,
                "reasoning": "",
                "done": False,
                "error": str(exc),
            }

    async def _execute_action(
        self, device_id: str, action: dict[str, Any]
    ) -> None:
        """Dispatch action dict to AutoXDevice async methods."""
        action_type = action.get("type", "")

        if action_type == "tap":
            await self.autox.click(int(action["x"]), int(action["y"]))

        elif action_type == "input_text":
            await self.autox.input_text(action["text"])

        elif action_type == "swipe":
            duration = action.get("duration", 500)
            await self.autox.swipe(
                int(action["x1"]),
                int(action["y1"]),
                int(action["x2"]),
                int(action["y2"]),
                int(duration),
            )

        elif action_type == "key_event":
            key_code = int(action["keyCode"])
            key_name = next(
                (k for k, v in KEY_MAP.items() if v == key_code), str(key_code)
            )
            await self.autox.key_event(key_name)

        elif action_type == "wait":
            await asyncio.sleep(action.get("ms", 1000) / 1000.0)

        else:
            raise ValueError(f"Unknown action type: {action_type}")


autox_vision_agent = AutoXVisionAgent(
    autox_device=autox,
    gui_plus_client=gui_plus_client,
    safety_guard=safety_guard,
)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@app.exception_handler(AutoXDeviceError)
async def autox_error_handler(request, exc: AutoXDeviceError):
    return JSONResponse(
        status_code=200,
        content={"success": False, "message": str(exc), "data": None},
    )


@app.exception_handler(Exception)
async def general_error_handler(request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": str(exc), "data": None},
    )


# ---------------------------------------------------------------------------
# Health & device info
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    autox_ok = await autox.health_check()
    return ApiResponse(
        success=True,
        message="AutoX Service running" + (" (AutoJS connected)" if autox_ok else " (AutoJS disconnected)"),
        data={"autox_connected": autox_ok},
    )


@app.get("/device/info")
async def device_info():
    info = await autox.get_device_info()
    return ApiResponse(success=True, message="OK", data=info)


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------


@app.post("/screenshot")
async def screenshot():
    b64 = await autox.screenshot_base64()
    return ApiResponse(success=True, message="OK", data={"base64": b64, "format": "jpeg"})


# ---------------------------------------------------------------------------
# Touch / gesture
# ---------------------------------------------------------------------------


@app.post("/click")
async def click(req: ClickRequest):
    # Safety check
    check = safety_guard.check_action({"type": "tap", "x": req.x, "y": req.y})
    if not check.allowed:
        return ApiResponse(success=False, message=check.reason)
    
    await autox.click(req.x, req.y)
    return ApiResponse(success=True, message=f"Clicked ({req.x}, {req.y})")


@app.post("/long_click")
async def long_click(req: LongClickRequest):
    await autox.long_click(req.x, req.y, req.duration)
    return ApiResponse(success=True, message=f"Long clicked ({req.x}, {req.y})")


@app.post("/swipe")
async def swipe(req: SwipeRequest):
    await autox.swipe(req.x1, req.y1, req.x2, req.y2, req.duration)
    return ApiResponse(success=True, message=f"Swiped ({req.x1},{req.y1}) -> ({req.x2},{req.y2})")


@app.post("/scroll")
async def scroll(req: ScrollRequest):
    await autox.scroll(req.direction)
    return ApiResponse(success=True, message=f"Scrolled {req.direction}")


# ---------------------------------------------------------------------------
# Text input
# ---------------------------------------------------------------------------


@app.post("/input")
async def input_text(req: InputTextRequest):
    # Safety check for text input
    check = safety_guard.check_text_input(req.text)
    if not check.allowed:
        return ApiResponse(success=False, message=check.reason)
    
    await autox.input_text(req.text)
    return ApiResponse(success=True, message="Text input sent")


# ---------------------------------------------------------------------------
# Key events
# ---------------------------------------------------------------------------


@app.post("/key")
async def key_event(req: KeyRequest):
    await autox.key_event(req.key)
    return ApiResponse(success=True, message=f"Key {req.key} pressed")


@app.post("/back")
async def go_back():
    await autox.press_back()
    return ApiResponse(success=True, message="Pressed back")


@app.post("/home")
async def go_home():
    await autox.press_home()
    return ApiResponse(success=True, message="Pressed home")


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------


@app.post("/app/start")
async def app_start(req: PackageRequest):
    await autox.app_start(req.package)
    return ApiResponse(success=True, message=f"Started {req.package}")


@app.post("/app/stop")
async def app_stop(req: PackageRequest):
    await autox.app_stop(req.package)
    return ApiResponse(success=True, message=f"Stopped {req.package}")


@app.get("/app/current")
async def app_current():
    info = await autox.current_app()
    return ApiResponse(success=True, message="OK", data=info)


# ---------------------------------------------------------------------------
# Element operations
# ---------------------------------------------------------------------------


@app.post("/find_element")
async def find_element(req: FindElementRequest):
    el = await autox.find_element(req.by, req.value, req.timeout)
    if el:
        return ApiResponse(success=True, message="Element found", data=el)
    return ApiResponse(success=True, message="Element not found", data=None)


@app.post("/find_elements")
async def find_elements(req: FindElementRequest):
    els = await autox.find_elements(req.by, req.value)
    return ApiResponse(success=True, message=f"Found {len(els)} elements", data=els)


@app.post("/click_element")
async def click_element(req: FindElementRequest):
    # Safety check - get element text first
    el = await autox.find_element(req.by, req.value, req.timeout)
    if el:
        text = el.get("text", "") or el.get("desc", "")
        check = safety_guard.check_action({"type": "tap"}, reasoning=f"点击元素: {text}")
        if not check.allowed:
            return ApiResponse(success=False, message=check.reason)
    
    clicked = await autox.click_element(req.by, req.value, req.timeout)
    if clicked:
        return ApiResponse(success=True, message="Element clicked")
    return ApiResponse(success=False, message="Element not found")


@app.post("/wait_element")
async def wait_element(req: FindElementRequest):
    el = await autox.wait_element(req.by, req.value, req.timeout)
    if el:
        return ApiResponse(success=True, message="Element found", data=el)
    return ApiResponse(success=True, message="Element not found (timeout)", data=None)


# ---------------------------------------------------------------------------
# UI tree
# ---------------------------------------------------------------------------


@app.get("/ui_tree")
async def ui_tree():
    tree = await autox.ui_tree(max_depth=3)
    return ApiResponse(success=True, message="OK", data=tree)


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------


@app.post("/ocr")
async def ocr():
    texts = await autox.ocr()
    return ApiResponse(success=True, message=f"Found {len(texts)} texts", data=texts)


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------


@app.get("/clipboard")
async def get_clipboard():
    text = await autox.get_clipboard()
    return ApiResponse(success=True, message="OK", data={"text": text})


@app.post("/clipboard")
async def set_clipboard(req: ClipboardRequest):
    if req.text is not None:
        await autox.set_clipboard(req.text)
        return ApiResponse(success=True, message="Clipboard set")
    text = await autox.get_clipboard()
    return ApiResponse(success=True, message="OK", data={"text": text})


# ---------------------------------------------------------------------------
# Custom script
# ---------------------------------------------------------------------------


@app.post("/run_script")
async def run_script(req: RunScriptRequest):
    result = await autox.run_script(req.script)
    return ApiResponse(success=True, message="Script executed", data=result)


# ---------------------------------------------------------------------------
# Vision analysis
# ---------------------------------------------------------------------------


@app.post("/vision/analyze")
async def vision_analyze(req: VisionAnalyzeRequest):
    if not _dashscope_api_key:
        return ApiResponse(success=False, message="DASHSCOPE_API_KEY is not set")
    b64 = await autox.screenshot_base64()
    result = await vl_client.analyze(b64, req.prompt)
    if not result.get("success"):
        return ApiResponse(success=False, message=result.get("error", "Vision analysis failed"))
    return ApiResponse(success=True, message="OK", data=result)


@app.post("/vision/smart_task")
async def vision_smart_task(req: SmartTaskRequest):
    """AI 驱动的智能任务循环（通过 AutoXVisionAgent + GuiPlusClient）"""
    if not _dashscope_api_key:
        return ApiResponse(success=False, message="DASHSCOPE_API_KEY is not set")
    result = await autox_vision_agent.run_task("autox", req.goal, req.max_steps)
    if not result.get("success"):
        return ApiResponse(
            success=False,
            message=result.get("message", "Smart task failed"),
            data=result,
        )
    return ApiResponse(
        success=True,
        message=result.get("message", "Task completed"),
        data=result,
    )


# ---------------------------------------------------------------------------
# Safety Guard
# ---------------------------------------------------------------------------


@app.get("/safety/rules")
async def safety_rules():
    rules = safety_guard.list_rules()
    return ApiResponse(success=True, message=f"{len(rules)} rules", data=rules)


@app.get("/safety/log")
async def safety_log():
    log = safety_guard.get_safety_log(limit=50)
    return ApiResponse(success=True, message="OK", data=log)


@app.get("/safety/pending")
async def safety_pending():
    pending = safety_guard.get_pending_confirmations()
    return ApiResponse(success=True, message=f"{len(pending)} pending", data=pending)


class SafetyConfirmRequest(BaseModel):
    confirm_id: str
    approved: bool


@app.post("/safety/confirm")
async def safety_confirm(req: SafetyConfirmRequest):
    result = safety_guard.confirm(req.confirm_id, req.approved)
    action = "approved" if req.approved else "rejected"
    return ApiResponse(success=True, message=f"Confirmation {action}", data=result)


class SafetyModeRequest(BaseModel):
    mode: str


@app.post("/safety/mode")
async def safety_set_mode(req: SafetyModeRequest):
    try:
        safety_guard.mode = req.mode
        return ApiResponse(success=True, message=f"Safety mode set to: {req.mode}")
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))


@app.get("/safety/mode")
async def safety_get_mode():
    return ApiResponse(success=True, message="OK", data={"mode": safety_guard.mode})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("U2_SERVER_PORT", "9400"))
    uvicorn.run(app, host="0.0.0.0", port=port)
