"""SafetyGuard 单元测试。

测试安全守卫的核心功能：规则匹配、操作拦截、人工确认、模式切换。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from safety_guard import SafetyGuard, SafetyLevel, SafetyRule, SafetyBlockedError


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def guard():
    """默认 strict 模式的 SafetyGuard。"""
    return SafetyGuard(mode="strict")


@pytest.fixture
def permissive_guard():
    return SafetyGuard(mode="permissive")


@pytest.fixture
def observe_guard():
    return SafetyGuard(mode="observe_only")


# ============================================================
# 安全操作（应该放行）
# ============================================================

class TestSafeActions:
    def test_swipe_is_safe(self, guard):
        result = guard.check_action({"type": "swipe", "x1": 0, "y1": 0, "x2": 100, "y2": 100})
        assert result.allowed is True
        assert result.level == SafetyLevel.SAFE

    def test_wait_is_safe(self, guard):
        result = guard.check_action({"type": "wait", "ms": 1000})
        assert result.allowed is True

    def test_back_key_is_safe(self, guard):
        result = guard.check_action({"type": "key_event", "keyCode": 4})
        assert result.allowed is True

    def test_home_key_is_safe(self, guard):
        result = guard.check_action({"type": "key_event", "keyCode": 3})
        assert result.allowed is True

    def test_tap_without_dangerous_context(self, guard):
        result = guard.check_action(
            {"type": "tap", "x": 540, "y": 960},
            reasoning="点击列表中的第一个商品查看详情",
        )
        assert result.allowed is True


# ============================================================
# BLOCKED 操作（应该直接拒绝）
# ============================================================

class TestBlockedActions:
    def test_block_payment_text(self, guard):
        result = guard.check_action(
            {"type": "tap", "x": 540, "y": 1800},
            reasoning="点击支付按钮完成付款",
        )
        assert result.allowed is False
        assert result.level == SafetyLevel.BLOCKED
        assert "支付" in result.reason or "付款" in result.reason

    def test_block_transfer(self, guard):
        result = guard.check_action(
            {"type": "tap", "x": 300, "y": 500},
            reasoning="点击转账按钮",
        )
        assert result.allowed is False
        assert result.level == SafetyLevel.BLOCKED

    def test_block_password_input(self, guard):
        result = guard.check_action(
            {"type": "input_text", "text": "mypassword123"},
            reasoning="输入密码",
        )
        assert result.allowed is False
        assert result.level == SafetyLevel.BLOCKED

    def test_block_delete_account(self, guard):
        result = guard.check_action(
            {"type": "tap", "x": 540, "y": 960},
            reasoning="点击注销账号",
        )
        assert result.allowed is False
        assert result.level == SafetyLevel.BLOCKED


# ============================================================
# DANGER 操作（strict 模式需要确认）
# ============================================================

class TestDangerActions:
    def test_bid_requires_confirmation(self, guard):
        result = guard.check_action(
            {"type": "tap", "x": 540, "y": 1600},
            reasoning="点击出价按钮参与竞拍",
        )
        assert result.allowed is False
        assert result.level == SafetyLevel.DANGER
        assert result.requires_confirmation is True
        assert "竞拍" in result.reason or "出价" in result.reason

    def test_submit_order_requires_confirmation(self, guard):
        result = guard.check_action(
            {"type": "tap", "x": 540, "y": 1800},
            reasoning="点击提交订单",
        )
        assert result.allowed is False
        assert result.requires_confirmation is True

    def test_amount_input_requires_confirmation(self, guard):
        result = guard.check_action(
            {"type": "input_text", "text": "15000"},
            reasoning="输入出价金额",
        )
        assert result.allowed is False
        assert result.requires_confirmation is True

    def test_confirm_dialog_in_bid_context(self, guard):
        result = guard.check_action(
            {"type": "tap", "x": 540, "y": 960},
            reasoning="确认出价",
        )
        assert result.allowed is False
        assert result.requires_confirmation is True

    def test_danger_allowed_in_permissive_mode(self, permissive_guard):
        result = permissive_guard.check_action(
            {"type": "tap", "x": 540, "y": 1600},
            reasoning="点击出价按钮",
        )
        assert result.allowed is True
        assert result.level == SafetyLevel.DANGER

    def test_danger_allowed_in_observe_mode(self, observe_guard):
        result = observe_guard.check_action(
            {"type": "tap", "x": 540, "y": 1600},
            reasoning="点击出价按钮",
        )
        assert result.allowed is True


# ============================================================
# 人工确认流程
# ============================================================

class TestConfirmation:
    def test_confirm_flow(self, guard):
        # 1. 操作被拦截
        result = guard.check_action(
            {"type": "tap", "x": 540, "y": 1600},
            reasoning="点击出价按钮",
        )
        assert result.allowed is False
        assert result.requires_confirmation is True

        # 2. 请求确认
        confirm_id = guard.request_confirmation(result)
        assert confirm_id.startswith("confirm_")

        # 3. 查看待确认列表
        pending = guard.get_pending_confirmations()
        assert len(pending) == 1
        assert pending[0]["confirm_id"] == confirm_id

        # 4. 人工批准
        approved = guard.confirm(confirm_id, approved=True)
        assert approved is True

        # 5. 待确认列表清空
        assert len(guard.get_pending_confirmations()) == 0

        # 6. 相同操作现在可以执行
        result2 = guard.check_action(
            {"type": "tap", "x": 540, "y": 1600},
            reasoning="点击出价按钮",
        )
        assert result2.allowed is True

    def test_reject_flow(self, guard):
        result = guard.check_action(
            {"type": "tap", "x": 540, "y": 1600},
            reasoning="点击出价按钮",
        )
        confirm_id = guard.request_confirmation(result)

        # 人工拒绝
        approved = guard.confirm(confirm_id, approved=False)
        assert approved is False

        # 操作仍然被拦截
        result2 = guard.check_action(
            {"type": "tap", "x": 540, "y": 1600},
            reasoning="点击出价按钮",
        )
        assert result2.allowed is False

    def test_invalid_confirm_id(self, guard):
        result = guard.confirm("nonexistent_id", approved=True)
        assert result is False


# ============================================================
# CAUTION 操作（记录但允许）
# ============================================================

class TestCautionActions:
    def test_login_is_caution(self, guard):
        result = guard.check_action(
            {"type": "tap", "x": 540, "y": 960},
            reasoning="点击登录按钮",
        )
        assert result.allowed is True
        assert result.level == SafetyLevel.CAUTION

    def test_share_is_caution(self, guard):
        result = guard.check_action(
            {"type": "tap", "x": 540, "y": 960},
            reasoning="点击分享按钮",
        )
        assert result.allowed is True
        assert result.level == SafetyLevel.CAUTION


# ============================================================
# 模式切换
# ============================================================

class TestModes:
    def test_switch_to_permissive(self, guard):
        guard.mode = "permissive"
        result = guard.check_action(
            {"type": "tap", "x": 540, "y": 1600},
            reasoning="点击出价按钮",
        )
        assert result.allowed is True

    def test_switch_to_observe(self, guard):
        guard.mode = "observe_only"
        # 即使是 BLOCKED 级别也放行
        result = guard.check_action(
            {"type": "tap", "x": 540, "y": 1800},
            reasoning="点击支付按钮",
        )
        assert result.allowed is True

    def test_invalid_mode(self, guard):
        with pytest.raises(ValueError):
            guard.mode = "invalid_mode"

    def test_blocked_not_affected_by_permissive(self, permissive_guard):
        """BLOCKED 级别即使在 permissive 模式也应该被拦截。"""
        result = permissive_guard.check_action(
            {"type": "tap", "x": 540, "y": 1800},
            reasoning="点击支付按钮",
        )
        assert result.allowed is False
        assert result.level == SafetyLevel.BLOCKED


# ============================================================
# 安全日志
# ============================================================

class TestSafetyLog:
    def test_log_records_events(self, guard):
        guard.check_action(
            {"type": "tap", "x": 540, "y": 1800},
            reasoning="点击支付按钮",
        )
        log = guard.get_safety_log()
        assert len(log) >= 1
        assert log[-1]["event"] == "blocked"

    def test_log_limit(self, guard):
        log = guard.get_safety_log(limit=5)
        assert len(log) <= 5


# ============================================================
# 自定义规则
# ============================================================

class TestCustomRules:
    def test_add_custom_rule(self, guard):
        guard.add_rule(SafetyRule(
            name="block_custom",
            level=SafetyLevel.BLOCKED,
            text_patterns=["自定义危险操作"],
            description="自定义拦截规则",
        ))
        result = guard.check_action(
            {"type": "tap", "x": 100, "y": 100},
            reasoning="执行自定义危险操作",
        )
        assert result.allowed is False
        assert result.matched_rule == "block_custom"

    def test_remove_rule(self, guard):
        removed = guard.remove_rule("block_payment")
        assert removed is True
        # 支付操作不再被拦截（但可能被其他规则匹配）
        rules = guard.list_rules()
        assert not any(r["name"] == "block_payment" for r in rules)


# ============================================================
# 竞拍场景端到端测试
# ============================================================

class TestBidScenario:
    """模拟完整的竞拍分析场景。"""

    def test_browsing_is_safe(self, guard):
        """浏览竞拍列表 → 安全"""
        actions = [
            ({"type": "tap", "x": 540, "y": 300}, "点击查看竞拍列表页面"),
            ({"type": "swipe", "x1": 540, "y1": 1600, "x2": 540, "y2": 400}, "向下滑动查看更多"),
            ({"type": "tap", "x": 540, "y": 600}, "点击查看详情"),
            ({"type": "key_event", "keyCode": 4}, "返回上一页"),
        ]
        for action, reasoning in actions:
            result = guard.check_action(action, reasoning=reasoning)
            assert result.allowed is True, f"Should be safe: {reasoning}"

    def test_bid_flow_blocked_then_confirmed(self, guard):
        """出价流程：先被拦截 → 人工确认 → 允许执行"""
        # 浏览到出价页面（安全 — 只是查看详情）
        r1 = guard.check_action(
            {"type": "tap", "x": 540, "y": 800},
            reasoning="点击进入竞拍详情页查看信息",
        )
        assert r1.allowed is True

        # 点击出价按钮（被拦截）
        r2 = guard.check_action(
            {"type": "tap", "x": 540, "y": 1600},
            reasoning="点击出价按钮参与竞拍",
        )
        assert r2.allowed is False
        assert r2.requires_confirmation is True

        # 人工确认
        cid = guard.request_confirmation(r2)
        guard.confirm(cid, approved=True)

        # 再次点击出价（已确认，允许）
        r3 = guard.check_action(
            {"type": "tap", "x": 540, "y": 1600},
            reasoning="点击出价按钮参与竞拍",
        )
        assert r3.allowed is True

    def test_pure_number_input_flagged(self, guard):
        """输入纯数字（可能是金额）→ 需要确认"""
        result = guard.check_action(
            {"type": "input_text", "text": "25000"},
            reasoning="在输入框中输入数字",
        )
        assert result.allowed is False
        assert result.requires_confirmation is True

    def test_text_input_safe(self, guard):
        """输入普通文本 → 安全"""
        result = guard.check_action(
            {"type": "input_text", "text": "搜索生猪"},
            reasoning="在搜索框输入关键词",
        )
        assert result.allowed is True
