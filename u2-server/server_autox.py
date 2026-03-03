"""FastAPI server — AutoJS 模式。

直接调用手机端 AutoJS 服务，不依赖 ADB/uiautomator2。
更简单、更快、延迟更低。

端口: 9400
AutoJS 服务: localhost:9501 (frp 映射)
"""

from __future__ import annotations

import os
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from autox_device import AutoXDevice, AutoXDeviceError
from safety_guard import SafetyGuard
from vision import GlmVisionClient

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

# Vision client
_glm_api_key = os.environ.get(
    "GLM_API_KEY", "bbbeb98f39904758a4168fa1228fc33e.XyTbD6d7SNcqMJKa"
)
vision_client = GlmVisionClient(api_key=_glm_api_key, model="glm-4.6v")


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
    b64 = await autox.screenshot_base64()
    result = await vision_client.analyze(b64, req.prompt)
    if not result.get("success"):
        return ApiResponse(success=False, message=result.get("error", "Vision analysis failed"))
    return ApiResponse(success=True, message="OK", data=result)


@app.post("/vision/smart_task")
async def vision_smart_task(req: SmartTaskRequest):
    """AI 驱动的智能任务循环"""
    import asyncio
    
    max_steps = req.max_steps
    history: list[str] = []
    steps: list[dict] = []
    
    for i in range(1, max_steps + 1):
        # 截图
        b64 = await autox.screenshot_base64()
        
        # 构建 prompt
        history_text = "\n".join(history[-5:]) if history else "无"
        prompt = f"""你是一个手机自动化助手。

当前任务目标: {req.goal}

最近操作历史:
{history_text}

请分析当前屏幕，决定下一步操作。

输出格式（JSON）:
{{
  "done": true/false,  // 任务是否已完成
  "reasoning": "分析和决策理由",
  "action": {{  // 如果 done=false，给出下一步操作
    "type": "click/swipe/input/back/home/scroll/wait",
    "x": 数字,  // click/swipe 需要
    "y": 数字,
    "x2": 数字,  // swipe 需要
    "y2": 数字,
    "text": "文本",  // input 需要
    "direction": "up/down"  // scroll 需要
  }}
}}

只输出 JSON，不要其他文字。"""
        
        result = await vision_client.analyze(b64, prompt)
        if not result.get("success"):
            return ApiResponse(
                success=False,
                message=f"Vision error at step {i}",
                data={"steps": steps},
            )
        
        # 解析响应
        import json
        import re
        
        text = result.get("description", "")
        # 提取 JSON
        match = re.search(r'\{[\s\S]*\}', text)
        if not match:
            steps.append({"step": i, "error": "无法解析响应"})
            continue
        
        try:
            decision = json.loads(match.group())
        except json.JSONDecodeError:
            steps.append({"step": i, "error": "JSON 解析失败"})
            continue
        
        reasoning = decision.get("reasoning", "")
        
        # 检查是否完成
        if decision.get("done"):
            steps.append({"step": i, "reasoning": reasoning, "done": True})
            return ApiResponse(
                success=True,
                message=f"Task completed in {i} steps: {reasoning}",
                data={"steps": steps},
            )
        
        # 执行操作
        action = decision.get("action", {})
        action_type = action.get("type", "")
        
        try:
            if action_type == "click":
                x, y = action.get("x", 0), action.get("y", 0)
                # Safety check
                check = safety_guard.check_action({"type": "tap", "x": x, "y": y}, reasoning=reasoning)
                if not check.allowed:
                    steps.append({"step": i, "reasoning": reasoning, "blocked": check.reason})
                    history.append(f"步骤{i}: 被安全守卫拦截 - {check.reason}")
                    await autox.press_back()  # 自动返回
                    continue
                await autox.click(x, y)
            elif action_type == "swipe":
                await autox.swipe(
                    action.get("x", 0), action.get("y", 0),
                    action.get("x2", 0), action.get("y2", 0),
                    action.get("duration", 500),
                )
            elif action_type == "input":
                text = action.get("text", "")
                check = safety_guard.check_text_input(text, reasoning=reasoning)
                if not check.allowed:
                    steps.append({"step": i, "reasoning": reasoning, "blocked": check.reason})
                    history.append(f"步骤{i}: 输入被拦截 - {check.reason}")
                    continue
                await autox.input_text(text)
            elif action_type == "back":
                await autox.press_back()
            elif action_type == "home":
                await autox.press_home()
            elif action_type == "scroll":
                await autox.scroll(action.get("direction", "down"))
            elif action_type == "wait":
                await asyncio.sleep(action.get("duration", 1000) / 1000)
            else:
                steps.append({"step": i, "error": f"未知操作类型: {action_type}"})
                continue
            
            steps.append({"step": i, "reasoning": reasoning, "action": action})
            history.append(f"步骤{i}: {reasoning} → {action_type}")
            
        except Exception as e:
            steps.append({"step": i, "error": str(e)})
            history.append(f"步骤{i}: 执行失败 - {e}")
        
        # 等待界面响应
        await asyncio.sleep(0.8)
    
    return ApiResponse(
        success=False,
        message=f"Reached max steps ({max_steps})",
        data={"steps": steps},
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
