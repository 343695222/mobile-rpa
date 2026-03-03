"""
ActionMapper 单元测试

测试 GUI-Plus 操作类型到 DeviceManager 操作字典的映射逻辑，
包括 CLICK、TYPE、SCROLL、KEY_PRESS、FINISH/FAIL 和未知操作类型。
"""

import pytest

from action_mapper import (
    KEY_MAP,
    SCROLL_DISTANCE,
    SCROLL_DURATION,
    ActionMapper,
)


# ---------------------------------------------------------------------------
# CLICK → tap
# ---------------------------------------------------------------------------


class TestClickMapping:
    def test_basic_click(self):
        result = ActionMapper.map_action("CLICK", {"x": 540, "y": 960})
        assert result == {"type": "tap", "x": 540, "y": 960}

    def test_click_zero_coords(self):
        result = ActionMapper.map_action("CLICK", {"x": 0, "y": 0})
        assert result == {"type": "tap", "x": 0, "y": 0}

    def test_click_case_insensitive(self):
        result = ActionMapper.map_action("click", {"x": 100, "y": 200})
        assert result == {"type": "tap", "x": 100, "y": 200}

    def test_click_mixed_case(self):
        result = ActionMapper.map_action("Click", {"x": 100, "y": 200})
        assert result == {"type": "tap", "x": 100, "y": 200}


# ---------------------------------------------------------------------------
# TYPE → input_text
# ---------------------------------------------------------------------------


class TestTypeMapping:
    def test_basic_type(self):
        result = ActionMapper.map_action("TYPE", {"text": "hello"})
        assert result == {"type": "input_text", "text": "hello"}

    def test_type_chinese_text(self):
        result = ActionMapper.map_action("TYPE", {"text": "你好世界"})
        assert result == {"type": "input_text", "text": "你好世界"}

    def test_type_empty_text(self):
        result = ActionMapper.map_action("TYPE", {"text": ""})
        assert result == {"type": "input_text", "text": ""}

    def test_type_case_insensitive(self):
        result = ActionMapper.map_action("type", {"text": "test"})
        assert result == {"type": "input_text", "text": "test"}


# ---------------------------------------------------------------------------
# SCROLL → swipe
# ---------------------------------------------------------------------------


class TestScrollMapping:
    def test_scroll_up(self):
        result = ActionMapper.map_action("SCROLL", {"x": 540, "y": 960, "direction": "up"})
        assert result == {
            "type": "swipe",
            "x1": 540, "y1": 960,
            "x2": 540, "y2": 960 - SCROLL_DISTANCE,
            "duration": SCROLL_DURATION,
        }

    def test_scroll_down(self):
        result = ActionMapper.map_action("SCROLL", {"x": 540, "y": 960, "direction": "down"})
        assert result == {
            "type": "swipe",
            "x1": 540, "y1": 960,
            "x2": 540, "y2": 960 + SCROLL_DISTANCE,
            "duration": SCROLL_DURATION,
        }

    def test_scroll_left(self):
        result = ActionMapper.map_action("SCROLL", {"x": 540, "y": 960, "direction": "left"})
        assert result == {
            "type": "swipe",
            "x1": 540, "y1": 960,
            "x2": 540 - SCROLL_DISTANCE, "y2": 960,
            "duration": SCROLL_DURATION,
        }

    def test_scroll_right(self):
        result = ActionMapper.map_action("SCROLL", {"x": 540, "y": 960, "direction": "right"})
        assert result == {
            "type": "swipe",
            "x1": 540, "y1": 960,
            "x2": 540 + SCROLL_DISTANCE, "y2": 960,
            "duration": SCROLL_DURATION,
        }

    def test_scroll_duration_is_500ms(self):
        result = ActionMapper.map_action("SCROLL", {"x": 0, "y": 0, "direction": "up"})
        assert result["duration"] == 500

    def test_scroll_case_insensitive(self):
        result = ActionMapper.map_action("scroll", {"x": 100, "y": 200, "direction": "UP"})
        assert result["type"] == "swipe"
        assert result["y2"] == 200 - SCROLL_DISTANCE


# ---------------------------------------------------------------------------
# KEY_PRESS → key_event
# ---------------------------------------------------------------------------


class TestKeyPressMapping:
    def test_enter_key(self):
        result = ActionMapper.map_action("KEY_PRESS", {"key": "enter"})
        assert result == {"type": "key_event", "keyCode": 66}

    def test_back_key(self):
        result = ActionMapper.map_action("KEY_PRESS", {"key": "back"})
        assert result == {"type": "key_event", "keyCode": 4}

    def test_home_key(self):
        result = ActionMapper.map_action("KEY_PRESS", {"key": "home"})
        assert result == {"type": "key_event", "keyCode": 3}

    def test_all_known_keys(self):
        for key_name, expected_code in KEY_MAP.items():
            result = ActionMapper.map_action("KEY_PRESS", {"key": key_name})
            assert result == {"type": "key_event", "keyCode": expected_code}, f"Failed for key: {key_name}"

    def test_key_case_insensitive(self):
        result = ActionMapper.map_action("KEY_PRESS", {"key": "ENTER"})
        assert result == {"type": "key_event", "keyCode": 66}

    def test_unknown_key_returns_error(self):
        result = ActionMapper.map_action("KEY_PRESS", {"key": "f1"})
        assert "error" in result
        assert "Unknown key" in result["error"]

    def test_key_press_action_case_insensitive(self):
        result = ActionMapper.map_action("key_press", {"key": "back"})
        assert result == {"type": "key_event", "keyCode": 4}


# ---------------------------------------------------------------------------
# FINISH / FAIL → None
# ---------------------------------------------------------------------------


class TestTerminationSignals:
    def test_finish_returns_none(self):
        assert ActionMapper.map_action("FINISH", {}) is None

    def test_fail_returns_none(self):
        assert ActionMapper.map_action("FAIL", {}) is None

    def test_finish_case_insensitive(self):
        assert ActionMapper.map_action("finish", {}) is None

    def test_fail_case_insensitive(self):
        assert ActionMapper.map_action("Fail", {}) is None

    def test_finish_with_parameters_ignored(self):
        assert ActionMapper.map_action("FINISH", {"reason": "done"}) is None

    def test_fail_with_parameters_ignored(self):
        assert ActionMapper.map_action("FAIL", {"reason": "timeout"}) is None


# ---------------------------------------------------------------------------
# Unknown action → error dict (not exception)
# ---------------------------------------------------------------------------


class TestUnknownAction:
    def test_unknown_action_returns_error_dict(self):
        result = ActionMapper.map_action("UNKNOWN", {})
        assert isinstance(result, dict)
        assert "error" in result
        assert "Unknown action type" in result["error"]

    def test_unknown_action_includes_action_name(self):
        result = ActionMapper.map_action("SWIPE_LEFT", {})
        assert "SWIPE_LEFT" in result["error"]

    def test_unknown_action_does_not_raise(self):
        # Requirement 11.5: return error info, not raise exception
        result = ActionMapper.map_action("NONEXISTENT", {"x": 1})
        assert "error" in result

    def test_empty_action_returns_error(self):
        result = ActionMapper.map_action("", {})
        assert "error" in result


# ---------------------------------------------------------------------------
# Constants validation
# ---------------------------------------------------------------------------


class TestConstants:
    def test_key_map_has_expected_keys(self):
        expected = {"enter", "back", "home", "recents", "volume_up", "volume_down",
                    "power", "delete", "tab", "space", "escape"}
        assert set(KEY_MAP.keys()) == expected

    def test_scroll_distance(self):
        assert SCROLL_DISTANCE == 600

    def test_scroll_duration(self):
        assert SCROLL_DURATION == 500
