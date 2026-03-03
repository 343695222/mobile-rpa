"""
ActionMapper — 将 GUI-Plus 操作映射为 DeviceManager 兼容的操作字典。

GUI-Plus 模型输出结构化操作指令（CLICK/TYPE/SCROLL/KEY_PRESS/FINISH/FAIL），
本模块负责将这些指令转换为 DeviceManager 可执行的操作格式。
"""

from __future__ import annotations

from typing import Dict, Optional

# GUI-Plus 按键名到 Android KeyEvent 代码的映射
KEY_MAP: Dict[str, int] = {
    "enter": 66,
    "back": 4,
    "home": 3,
    "recents": 187,
    "volume_up": 24,
    "volume_down": 25,
    "power": 26,
    "delete": 67,
    "tab": 61,
    "space": 62,
    "escape": 111,
}

# 默认滑动距离（像素）和持续时间（毫秒）
SCROLL_DISTANCE: int = 600
SCROLL_DURATION: int = 500


class ActionMapper:
    """将 GUI-Plus 操作映射为 DeviceManager 兼容的操作字典。"""

    @staticmethod
    def map_action(action: str, parameters: dict) -> Optional[dict]:
        """将 GUI-Plus 的 action + parameters 映射为 DeviceManager 操作字典。

        Args:
            action: GUI-Plus 操作类型（CLICK/TYPE/SCROLL/KEY_PRESS/FINISH/FAIL）
            parameters: GUI-Plus 操作参数

        Returns:
            DeviceManager 兼容的操作字典，或 None（FINISH/FAIL 终止信号），
            或包含 "error" 键的字典（未知操作类型）。
        """
        action_upper = action.upper()

        if action_upper == "CLICK":
            return {"type": "tap", "x": parameters["x"], "y": parameters["y"]}

        if action_upper == "TYPE":
            return {"type": "input_text", "text": parameters["text"]}

        if action_upper == "SCROLL":
            return ActionMapper._map_scroll(parameters)

        if action_upper == "KEY_PRESS":
            return ActionMapper._map_key_press(parameters)

        if action_upper in ("FINISH", "FAIL"):
            return None

        return {"error": f"Unknown action type: {action}"}

    @staticmethod
    def _map_scroll(parameters: dict) -> dict:
        """根据 direction 计算 swipe 起止坐标。"""
        x = parameters["x"]
        y = parameters["y"]
        direction = parameters.get("direction", "down").lower()

        if direction == "up":
            return {"type": "swipe", "x1": x, "y1": y, "x2": x, "y2": y - SCROLL_DISTANCE, "duration": SCROLL_DURATION}
        if direction == "down":
            return {"type": "swipe", "x1": x, "y1": y, "x2": x, "y2": y + SCROLL_DISTANCE, "duration": SCROLL_DURATION}
        if direction == "left":
            return {"type": "swipe", "x1": x, "y1": y, "x2": x - SCROLL_DISTANCE, "y2": y, "duration": SCROLL_DURATION}
        if direction == "right":
            return {"type": "swipe", "x1": x, "y1": y, "x2": x + SCROLL_DISTANCE, "y2": y, "duration": SCROLL_DURATION}

        # 未知方向默认向下
        return {"type": "swipe", "x1": x, "y1": y, "x2": x, "y2": y + SCROLL_DISTANCE, "duration": SCROLL_DURATION}

    @staticmethod
    def _map_key_press(parameters: dict) -> dict:
        """将按键名映射为 Android KeyEvent 代码。"""
        key = parameters.get("key", "").lower()
        key_code = KEY_MAP.get(key)
        if key_code is not None:
            return {"type": "key_event", "keyCode": key_code}
        return {"error": f"Unknown key: {parameters.get('key', '')}"}
