"""FastAPI server entry point for U2_Service.

Exposes REST API endpoints for uiautomator2 device operations.
Runs on port 9400 (configurable via U2_SERVER_PORT env var).
"""

from __future__ import annotations

import os
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from collector import DataCollector
from device import DeviceError, DeviceManager
from navigator import Navigator
from safety_guard import SafetyGuard
from script_store import ScriptStore
from traffic_capture import TrafficCapture
from traffic_analyzer import TrafficAnalyzer
from validator import ScriptValidator
from vision import GlmVisionClient
from vision_agent import VisionAgent

# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class ClickRequest(BaseModel):
    x: int
    y: int


class SwipeRequest(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    duration: float = 0.5


class InputTextRequest(BaseModel):
    text: str


class FindElementRequest(BaseModel):
    by: Literal["text", "resourceId", "xpath"]
    value: str


class KeyEventRequest(BaseModel):
    key_code: int


class PackageRequest(BaseModel):
    package: str


class ClipboardRequest(BaseModel):
    text: str


class VisionAnalyzeRequest(BaseModel):
    device_id: str
    prompt: str = "请描述屏幕上的内容"


class SmartTaskRequest(BaseModel):
    device_id: str
    goal: str
    max_steps: int = 20


class CollectRequest(BaseModel):
    device_id: str
    app: str
    data_type: str
    query: str = ""
    force_strategy: str | None = None


class ValidateRequest(BaseModel):
    device_id: str


class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Any = None


# ---------------------------------------------------------------------------
# App & shared state
# ---------------------------------------------------------------------------

app = FastAPI(title="U2 Service", version="0.1.0")
device_manager = DeviceManager()

# Safety guard (shared across all components)
safety_guard = SafetyGuard(mode="strict")

# Traffic capture & analysis
traffic_capture = TrafficCapture()
traffic_analyzer = TrafficAnalyzer()

# Vision components (require GLM_API_KEY)
_glm_api_key = os.environ.get(
    "GLM_API_KEY", "bbbeb98f39904758a4168fa1228fc33e.XyTbD6d7SNcqMJKa"
)
vision_client = GlmVisionClient(api_key=_glm_api_key, model="glm-4.6v")
vision_agent = VisionAgent(
    device_manager=device_manager,
    vision_client=vision_client,
    safety_guard=safety_guard,
)

# Data collection components
script_store = ScriptStore()
navigator = Navigator(
    device_manager=device_manager,
    vision_agent=vision_agent,
    script_store=script_store,
    safety_guard=safety_guard,
)
data_collector = DataCollector(
    device_manager=device_manager,
    navigator=navigator,
    script_store=script_store,
    vision_client=vision_client,
)

# Script validator
from strategies.api_strategy import ApiStrategy
from strategies.rpa_copy_strategy import RpaCopyStrategy
from strategies.rpa_ocr_strategy import RpaOcrStrategy

_strategies = {
    "api": ApiStrategy(),
    "rpa_copy": RpaCopyStrategy(device_manager=device_manager, navigator=navigator),
    "rpa_ocr": RpaOcrStrategy(
        device_manager=device_manager, navigator=navigator, vision_client=vision_client
    ),
}
script_validator = ScriptValidator(
    script_store=script_store,
    strategies=_strategies,
)


# ---------------------------------------------------------------------------
# Error handling middleware
# ---------------------------------------------------------------------------


@app.exception_handler(DeviceError)
async def device_error_handler(_request: Request, exc: DeviceError) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"success": False, "message": str(exc), "data": None},
    )


@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"success": False, "message": str(exc), "data": None},
    )


@app.exception_handler(Exception)
async def general_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": str(exc), "data": None},
    )


# ---------------------------------------------------------------------------
# Health & device listing
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> ApiResponse:
    return ApiResponse(success=True, message="U2 Service is running")


@app.get("/devices")
async def list_devices() -> ApiResponse:
    devices = device_manager.list_devices()
    return ApiResponse(success=True, message="OK", data=devices)


@app.get("/device/{device_id}/info")
async def device_info(device_id: str) -> ApiResponse:
    dev = device_manager.get_device(device_id)
    info = dev.info
    return ApiResponse(success=True, message="OK", data=info)


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------


@app.post("/device/{device_id}/screenshot")
async def screenshot(device_id: str) -> ApiResponse:
    b64 = device_manager.screenshot_base64(device_id)
    return ApiResponse(success=True, message="OK", data=b64)


# ---------------------------------------------------------------------------
# Touch / gesture
# ---------------------------------------------------------------------------


@app.post("/device/{device_id}/click")
async def click(device_id: str, req: ClickRequest) -> ApiResponse:
    device_manager.click(device_id, req.x, req.y)
    return ApiResponse(success=True, message=f"Clicked ({req.x}, {req.y})")


@app.post("/device/{device_id}/swipe")
async def swipe(device_id: str, req: SwipeRequest) -> ApiResponse:
    device_manager.swipe(device_id, req.x1, req.y1, req.x2, req.y2, req.duration)
    return ApiResponse(
        success=True,
        message=f"Swiped ({req.x1},{req.y1}) -> ({req.x2},{req.y2})",
    )


# ---------------------------------------------------------------------------
# Text input / key events
# ---------------------------------------------------------------------------


@app.post("/device/{device_id}/input_text")
async def input_text(device_id: str, req: InputTextRequest) -> ApiResponse:
    device_manager.input_text(device_id, req.text)
    return ApiResponse(success=True, message="Text input sent")


@app.post("/device/{device_id}/key_event")
async def key_event(device_id: str, req: KeyEventRequest) -> ApiResponse:
    device_manager.key_event(device_id, req.key_code)
    return ApiResponse(success=True, message=f"Key event {req.key_code} sent")


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------


@app.post("/device/{device_id}/app_start")
async def app_start(device_id: str, req: PackageRequest) -> ApiResponse:
    device_manager.app_start(device_id, req.package)
    return ApiResponse(success=True, message=f"Started {req.package}")


@app.post("/device/{device_id}/app_stop")
async def app_stop(device_id: str, req: PackageRequest) -> ApiResponse:
    device_manager.app_stop(device_id, req.package)
    return ApiResponse(success=True, message=f"Stopped {req.package}")


@app.get("/device/{device_id}/current_app")
async def current_app(device_id: str) -> ApiResponse:
    info = device_manager.current_app(device_id)
    return ApiResponse(success=True, message="OK", data=info)


# ---------------------------------------------------------------------------
# Element operations
# ---------------------------------------------------------------------------


@app.post("/device/{device_id}/find_element")
async def find_element(device_id: str, req: FindElementRequest) -> ApiResponse:
    el = device_manager.find_element(device_id, req.by, req.value)
    if el is None:
        return ApiResponse(success=True, message="Element not found", data=None)
    return ApiResponse(success=True, message="Element found", data=el)


@app.post("/device/{device_id}/click_element")
async def click_element(device_id: str, req: FindElementRequest) -> ApiResponse:
    clicked = device_manager.click_element(device_id, req.by, req.value)
    if not clicked:
        return ApiResponse(success=True, message="Element not found", data=False)
    return ApiResponse(success=True, message="Element clicked", data=True)


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------


@app.get("/device/{device_id}/clipboard")
async def get_clipboard(device_id: str) -> ApiResponse:
    text = device_manager.get_clipboard(device_id)
    return ApiResponse(success=True, message="OK", data=text)


@app.post("/device/{device_id}/clipboard")
async def set_clipboard(device_id: str, req: ClipboardRequest) -> ApiResponse:
    device_manager.set_clipboard(device_id, req.text)
    return ApiResponse(success=True, message="Clipboard set")


# ---------------------------------------------------------------------------
# UI hierarchy
# ---------------------------------------------------------------------------


@app.get("/device/{device_id}/ui_hierarchy")
async def ui_hierarchy(device_id: str) -> ApiResponse:
    xml = device_manager.ui_hierarchy(device_id)
    return ApiResponse(success=True, message="OK", data=xml)


# ---------------------------------------------------------------------------
# Vision analysis
# ---------------------------------------------------------------------------


@app.post("/vision/analyze")
async def vision_analyze(req: VisionAnalyzeRequest) -> ApiResponse:
    if not _glm_api_key:
        return ApiResponse(success=False, message="GLM_API_KEY is not set")
    b64 = device_manager.screenshot_base64(req.device_id)
    result = await vision_client.analyze(b64, req.prompt)
    if not result.get("success"):
        return ApiResponse(success=False, message=result.get("error", "Vision analysis failed"), data=result)
    return ApiResponse(success=True, message="OK", data=result)


@app.post("/vision/smart_task")
async def vision_smart_task(req: SmartTaskRequest) -> ApiResponse:
    if not _glm_api_key:
        return ApiResponse(success=False, message="GLM_API_KEY is not set")
    result = await vision_agent.run_task(req.device_id, req.goal, req.max_steps)
    if not result.get("success"):
        return ApiResponse(success=False, message=result.get("message", "Smart task failed"), data=result)
    return ApiResponse(success=True, message=result.get("message", "Task completed"), data=result)


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------


@app.post("/collect")
async def collect_data(req: CollectRequest) -> ApiResponse:
    result = await data_collector.collect(
        device_id=req.device_id,
        app=req.app,
        data_type=req.data_type,
        query=req.query,
        force_strategy=req.force_strategy,
    )
    if not result.get("success"):
        return ApiResponse(success=False, message=result.get("error", "Collection failed"), data=result)
    return ApiResponse(success=True, message="Data collected", data=result)


@app.get("/scripts")
async def list_scripts() -> ApiResponse:
    scripts = script_store.list_all()
    return ApiResponse(success=True, message="OK", data=scripts)


@app.post("/scripts/validate")
async def validate_scripts(req: ValidateRequest) -> ApiResponse:
    result = await script_validator.validate_all(req.device_id)
    return ApiResponse(
        success=True,
        message=f"Validated {result['total']} scripts: {result['success']} passed, {result['failure']} failed",
        data=result,
    )


@app.delete("/scripts/{script_id}")
async def delete_script(script_id: str) -> ApiResponse:
    deleted = script_store.delete(script_id)
    if not deleted:
        return ApiResponse(success=False, message=f"Script {script_id} not found")
    return ApiResponse(success=True, message=f"Script {script_id} deleted")


# ---------------------------------------------------------------------------
# Traffic Capture & Analysis
# ---------------------------------------------------------------------------


class TrafficStartRequest(BaseModel):
    platform_name: str
    domain_filter: list = []


class TrafficLoadHarRequest(BaseModel):
    har_file: str


@app.post("/traffic/start")
async def traffic_start(req: TrafficStartRequest) -> ApiResponse:
    traffic_capture.start_recording(req.platform_name, req.domain_filter)
    return ApiResponse(success=True, message=f"Recording started for {req.platform_name}")


@app.post("/traffic/stop")
async def traffic_stop() -> ApiResponse:
    records = traffic_capture.stop_recording()
    filepath = traffic_capture.save_to_file() if records else ""
    return ApiResponse(
        success=True,
        message=f"Recording stopped, {len(records)} records captured",
        data={"record_count": len(records), "file": filepath},
    )


@app.get("/traffic/records")
async def traffic_records() -> ApiResponse:
    from dataclasses import asdict
    records = traffic_capture.get_records()
    stats = traffic_capture.get_stats()
    return ApiResponse(
        success=True,
        message=f"{len(records)} records",
        data={"stats": stats, "records": [asdict(r) for r in records[:100]]},
    )


@app.post("/traffic/load_har")
async def traffic_load_har(req: TrafficLoadHarRequest) -> ApiResponse:
    try:
        records = traffic_capture.load_from_har(req.har_file)
        # Auto-analyze
        result = traffic_analyzer.analyze(records, traffic_capture.platform_name)
        from dataclasses import asdict
        endpoints_data = [asdict(ep) for ep in result.api_endpoints]
        return ApiResponse(
            success=True,
            message=f"Loaded {len(records)} records, found {len(result.api_endpoints)} API endpoints",
            data={
                "record_count": len(records),
                "api_endpoints": endpoints_data,
                "page_requests": result.page_requests,
                "static_resources": result.static_resources,
                "domains": result.domains,
            },
        )
    except FileNotFoundError as exc:
        return ApiResponse(success=False, message=str(exc))


# ---------------------------------------------------------------------------
# Safety Guard
# ---------------------------------------------------------------------------


class SafetyConfirmRequest(BaseModel):
    confirm_id: str
    approved: bool


class SafetyModeRequest(BaseModel):
    mode: str  # strict / permissive / observe_only


@app.get("/safety/rules")
async def safety_rules() -> ApiResponse:
    rules = safety_guard.list_rules()
    return ApiResponse(success=True, message=f"{len(rules)} rules", data=rules)


@app.get("/safety/log")
async def safety_log() -> ApiResponse:
    log = safety_guard.get_safety_log(limit=50)
    return ApiResponse(success=True, message="OK", data=log)


@app.get("/safety/pending")
async def safety_pending() -> ApiResponse:
    pending = safety_guard.get_pending_confirmations()
    return ApiResponse(success=True, message=f"{len(pending)} pending", data=pending)


@app.post("/safety/confirm")
async def safety_confirm(req: SafetyConfirmRequest) -> ApiResponse:
    result = safety_guard.confirm(req.confirm_id, req.approved)
    action = "approved" if req.approved else "rejected"
    return ApiResponse(success=True, message=f"Confirmation {action}: {req.confirm_id}", data=result)


@app.post("/safety/mode")
async def safety_set_mode(req: SafetyModeRequest) -> ApiResponse:
    try:
        safety_guard.mode = req.mode
        return ApiResponse(success=True, message=f"Safety mode set to: {req.mode}")
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))


@app.get("/safety/mode")
async def safety_get_mode() -> ApiResponse:
    return ApiResponse(success=True, message="OK", data={"mode": safety_guard.mode})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("U2_SERVER_PORT", "9400"))
    uvicorn.run(app, host="0.0.0.0", port=port)
