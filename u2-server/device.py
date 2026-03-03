"""DeviceManager — uiautomator2 device operations wrapper.

Manages multi-device connections with caching, and exposes a clean API
for screenshots, clicks, swipes, text input, element operations,
clipboard, app lifecycle, and UI hierarchy.
"""

from __future__ import annotations

import base64
import io
import subprocess
import threading
from typing import Any

import uiautomator2 as u2

# Supported element selector types
SUPPORTED_SELECTORS = ("text", "resourceId", "xpath")

# Default operation timeout (seconds)
DEFAULT_TIMEOUT = 10


class DeviceError(Exception):
    """Raised when a device is not connected or an operation fails."""

    def __init__(self, device_id: str, detail: str = ""):
        self.device_id = device_id
        self.detail = detail
        msg = f"Device not connected: {device_id}"
        if detail:
            msg = f"{msg} — {detail}"
        super().__init__(msg)


class DeviceManager:
    """Manages uiautomator2 device connections and operations."""

    def __init__(self) -> None:
        self._devices: dict[str, u2.Device] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def get_device(self, device_id: str) -> u2.Device:
        """Return a cached u2.Device, connecting on first access."""
        with self._lock:
            if device_id in self._devices:
                return self._devices[device_id]
        # Connect outside the lock to avoid blocking other callers.
        try:
            dev = u2.connect(device_id)
            dev.settings["operation_delay"] = (0, 0)
            dev.settings["wait_timeout"] = DEFAULT_TIMEOUT
        except Exception as exc:
            raise DeviceError(device_id, str(exc)) from exc
        with self._lock:
            self._devices[device_id] = dev
        return dev

    # ------------------------------------------------------------------
    # Device listing
    # ------------------------------------------------------------------

    def list_devices(self) -> list[dict]:
        """List connected ADB devices via ``adb devices``.

        Returns a list of dicts with ``serial`` and ``status`` keys.
        """
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError:
            return []
        except subprocess.TimeoutExpired:
            return []

        devices: list[dict] = []
        for line in result.stdout.strip().splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                devices.append({"serial": parts[0], "status": parts[1]})
        return devices

    # ------------------------------------------------------------------
    # Screenshot
    # ------------------------------------------------------------------

    def screenshot_base64(self, device_id: str) -> str:
        """Take a screenshot and return it as a base64-encoded PNG string."""
        dev = self.get_device(device_id)
        img = dev.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    # ------------------------------------------------------------------
    # Touch / gesture
    # ------------------------------------------------------------------

    def click(self, device_id: str, x: int, y: int) -> None:
        """Click at the given (x, y) coordinate."""
        dev = self.get_device(device_id)
        dev.click(x, y)

    def swipe(
        self,
        device_id: str,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.5,
    ) -> None:
        """Swipe from (x1, y1) to (x2, y2) over *duration* seconds."""
        dev = self.get_device(device_id)
        dev.swipe(x1, y1, x2, y2, duration=duration)

    # ------------------------------------------------------------------
    # Text input / key events
    # ------------------------------------------------------------------

    def input_text(self, device_id: str, text: str) -> None:
        """Input *text* (including CJK characters) on the focused field."""
        dev = self.get_device(device_id)
        dev.send_keys(text)

    def key_event(self, device_id: str, key_code: int) -> None:
        """Send a key event (Android KeyEvent code)."""
        dev = self.get_device(device_id)
        dev.press(key_code)

    # ------------------------------------------------------------------
    # Element operations
    # ------------------------------------------------------------------

    def find_element(
        self, device_id: str, by: str, value: str
    ) -> dict[str, Any] | None:
        """Find a UI element using *by* selector (text / resourceId / xpath).

        Returns a dict with element info or ``None`` if not found.
        Raises ``ValueError`` for unsupported selector types.
        """
        if by not in SUPPORTED_SELECTORS:
            raise ValueError(
                f"Unsupported selector type: '{by}'. "
                f"Supported types: {', '.join(SUPPORTED_SELECTORS)}"
            )

        dev = self.get_device(device_id)
        el = self._select_element(dev, by, value)

        if not el.exists:
            return None

        info = el.info
        return {
            "text": info.get("text", ""),
            "resourceId": info.get("resourceName", ""),
            "className": info.get("className", ""),
            "bounds": info.get("bounds", {}),
            "contentDescription": info.get("contentDescription", ""),
            "clickable": info.get("clickable", False),
            "enabled": info.get("enabled", False),
        }

    def click_element(self, device_id: str, by: str, value: str) -> bool:
        """Find and click a UI element. Returns ``True`` if clicked."""
        if by not in SUPPORTED_SELECTORS:
            raise ValueError(
                f"Unsupported selector type: '{by}'. "
                f"Supported types: {', '.join(SUPPORTED_SELECTORS)}"
            )

        dev = self.get_device(device_id)
        el = self._select_element(dev, by, value)

        if not el.exists:
            return False

        el.click()
        return True

    @staticmethod
    def _select_element(dev: u2.Device, by: str, value: str):
        """Return a uiautomator2 selector object for the given *by* type."""
        if by == "text":
            return dev(text=value)
        if by == "resourceId":
            return dev(resourceId=value)
        # by == "xpath"
        return dev.xpath(value)

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def get_clipboard(self, device_id: str) -> str:
        """Read the device clipboard text."""
        dev = self.get_device(device_id)
        return dev.clipboard or ""

    def set_clipboard(self, device_id: str, text: str) -> None:
        """Write *text* to the device clipboard."""
        dev = self.get_device(device_id)
        dev.set_clipboard(text)

    # ------------------------------------------------------------------
    # App lifecycle
    # ------------------------------------------------------------------

    def app_start(self, device_id: str, package: str) -> None:
        """Launch an app by package name."""
        dev = self.get_device(device_id)
        dev.app_start(package)

    def app_stop(self, device_id: str, package: str) -> None:
        """Force-stop an app by package name."""
        dev = self.get_device(device_id)
        dev.app_stop(package)

    def current_app(self, device_id: str) -> dict:
        """Return info about the current foreground app."""
        dev = self.get_device(device_id)
        info = dev.app_current()
        return {
            "package": getattr(info, "package", "") or "",
            "activity": getattr(info, "activity", "") or "",
        }

    # ------------------------------------------------------------------
    # UI hierarchy
    # ------------------------------------------------------------------

    def ui_hierarchy(self, device_id: str) -> str:
        """Return the current UI hierarchy as an XML string."""
        dev = self.get_device(device_id)
        return dev.dump_hierarchy()
