"""SafetyGuard — 敏感操作安全守卫。

在 AI 自动操作手机时，拦截可能造成经济损失或不可逆后果的敏感操作。
所有设备操作在执行前都必须经过 SafetyGuard 检查。

安全等级：
- SAFE:     安全操作，直接执行（浏览、截图、返回、滑动）
- CAUTION:  需要注意的操作，记录日志但允许执行（点击普通按钮）
- DANGER:   危险操作，需要人工确认才能执行（出价、支付、提交订单）
- BLOCKED:  禁止操作，直接拒绝（删除、注销、转账）

拦截机制：
1. 文本匹配：检查即将点击的按钮/元素的文本内容
2. 区域保护：标记屏幕上的危险区域（如"确认出价"按钮位置）
3. 输入过滤：检查即将输入的文本内容（如金额、密码）
4. 上下文感知：结合当前页面判断操作风险
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class SafetyLevel(str, Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGER = "danger"
    BLOCKED = "blocked"


@dataclass
class SafetyCheckResult:
    """安全检查结果"""
    level: SafetyLevel
    allowed: bool
    reason: str
    action: dict
    matched_rule: str = ""
    requires_confirmation: bool = False
    confirmation_prompt: str = ""


@dataclass
class SafetyRule:
    """安全规则定义"""
    name: str
    level: SafetyLevel
    # 匹配条件（任一匹配即触发）
    text_patterns: list[str] = field(default_factory=list)      # 按钮/元素文本
    input_patterns: list[str] = field(default_factory=list)     # 输入内容
    url_patterns: list[str] = field(default_factory=list)       # API URL
    reasoning_patterns: list[str] = field(default_factory=list) # AI reasoning 文本
    # 描述
    description: str = ""
    confirmation_prompt: str = ""


# ============================================================
# 默认安全规则（针对生猪竞拍平台场景）
# ============================================================

DEFAULT_RULES: list[SafetyRule] = [
    # ── BLOCKED: 绝对禁止 ──
    SafetyRule(
        name="block_payment",
        level=SafetyLevel.BLOCKED,
        text_patterns=["支付", "付款", "转账", "充值", "提现"],
        input_patterns=[],
        reasoning_patterns=["支付", "付款", "转账"],
        description="禁止任何支付/转账操作",
    ),
    SafetyRule(
        name="block_delete_account",
        level=SafetyLevel.BLOCKED,
        text_patterns=["注销账号", "删除账号", "注销", "永久删除"],
        description="禁止注销/删除账号",
    ),
    SafetyRule(
        name="block_password",
        level=SafetyLevel.BLOCKED,
        input_patterns=["密码", "password"],
        reasoning_patterns=["输入密码", "填写密码"],
        description="禁止输入密码",
    ),

    # ── DANGER: 需要人工确认 ──
    SafetyRule(
        name="danger_bid",
        level=SafetyLevel.DANGER,
        text_patterns=[
            "出价", "竞价", "报价", "加价",
            "确认出价", "立即出价", "我要出价", "提交报价",
            "确认竞拍", "参与竞拍",
        ],
        reasoning_patterns=["点击出价", "执行出价", "提交出价", "确认出价", "参与竞拍", "进行竞价", "提交竞价", "提交报价"],
        description="竞拍出价操作，需要人工确认",
        confirmation_prompt="⚠️ AI 即将执行【竞拍出价】操作，这可能产生真实的经济承诺。是否允许？",
    ),
    SafetyRule(
        name="danger_submit_order",
        level=SafetyLevel.DANGER,
        text_patterns=[
            "提交订单", "确认订单", "下单", "立即购买",
            "确认购买", "立即下单",
        ],
        reasoning_patterns=["提交订单", "下单", "购买"],
        description="提交订单操作，需要人工确认",
        confirmation_prompt="⚠️ AI 即将执行【提交订单】操作。是否允许？",
    ),
    SafetyRule(
        name="danger_amount_input",
        level=SafetyLevel.DANGER,
        input_patterns=[r"^\d+\.?\d*$"],  # 纯数字输入（可能是金额）
        reasoning_patterns=["输入金额", "输入价格", "填写出价"],
        description="输入金额/价格，需要人工确认",
        confirmation_prompt="⚠️ AI 即将输入一个数字（可能是金额）。是否允许？",
    ),
    SafetyRule(
        name="danger_confirm_dialog",
        level=SafetyLevel.DANGER,
        text_patterns=["确认", "确定"],
        reasoning_patterns=["确认出价", "确认支付", "确认订单", "确认提交"],
        description="确认对话框（结合上下文判断）",
        confirmation_prompt="⚠️ AI 即将点击【确认】按钮。请检查当前页面上下文是否安全。",
    ),

    # ── CAUTION: 记录但允许 ──
    SafetyRule(
        name="caution_login",
        level=SafetyLevel.CAUTION,
        text_patterns=["登录", "登入", "注册"],
        reasoning_patterns=["登录", "注册"],
        description="登录/注册操作",
    ),
    SafetyRule(
        name="caution_share",
        level=SafetyLevel.CAUTION,
        text_patterns=["分享", "转发", "发送"],
        description="分享/转发操作",
    ),
]


class SafetyGuard:
    """敏感操作安全守卫

    使用方式：
        guard = SafetyGuard()

        # 在执行操作前检查
        result = guard.check_action(action, reasoning="点击出价按钮")
        if not result.allowed:
            if result.requires_confirmation:
                # 暂停，等待人工确认
                ...
            else:
                # 直接拒绝
                raise SafetyBlockedError(result.reason)
    """

    def __init__(
        self,
        rules: list[SafetyRule] | None = None,
        config_path: str | None = None,
        mode: str = "strict",  # strict / permissive / observe_only
    ):
        self._rules = rules or list(DEFAULT_RULES)
        self._mode = mode
        self._log: list[dict] = []
        self._pending_confirmations: dict[str, SafetyCheckResult] = {}
        self._confirmed_actions: set[str] = set()  # 已确认的操作 hash

        # 从配置文件加载自定义规则
        if config_path:
            self._load_custom_rules(config_path)

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        if value not in ("strict", "permissive", "observe_only"):
            raise ValueError(f"Invalid mode: {value}")
        self._mode = value

    # ------------------------------------------------------------------
    # 核心检查方法
    # ------------------------------------------------------------------

    def check_action(
        self,
        action: dict[str, Any],
        reasoning: str = "",
        screen_text: str = "",
    ) -> SafetyCheckResult:
        """检查一个操作是否安全。

        Args:
            action: 操作字典 {"type": "tap", "x": ..., "y": ...} 等
            reasoning: AI 给出的操作理由
            screen_text: 当前屏幕上的文本（可选，用于上下文判断）

        Returns:
            SafetyCheckResult
        """
        action_type = action.get("type", "")

        # 滑动、等待、按键（返回/Home）始终安全
        if action_type in ("swipe", "wait"):
            return self._safe(action, "操作类型安全")

        if action_type == "key_event":
            key_code = action.get("keyCode", 0)
            if key_code in (3, 4, 187):  # Home, Back, Recent
                return self._safe(action, "导航按键安全")

        # 检查所有规则
        for rule in self._rules:
            matched = self._match_rule(rule, action, reasoning, screen_text)
            if matched:
                return self._apply_rule(rule, action, matched)

        # 无规则匹配 → 默认安全
        return self._safe(action, "无匹配规则")

    def check_text_input(self, text: str, reasoning: str = "") -> SafetyCheckResult:
        """专门检查文本输入操作。"""
        action = {"type": "input_text", "text": text}
        return self.check_action(action, reasoning)

    # ------------------------------------------------------------------
    # 人工确认机制
    # ------------------------------------------------------------------

    def request_confirmation(self, check_result: SafetyCheckResult) -> str:
        """请求人工确认，返回确认 ID。"""
        confirm_id = f"confirm_{int(time.time() * 1000)}"
        self._pending_confirmations[confirm_id] = check_result
        logger.warning(
            "SAFETY: Requesting confirmation [%s]: %s — %s",
            confirm_id, check_result.reason, check_result.confirmation_prompt,
        )
        return confirm_id

    def confirm(self, confirm_id: str, approved: bool) -> bool:
        """人工确认或拒绝一个待确认操作。"""
        if confirm_id not in self._pending_confirmations:
            return False

        check_result = self._pending_confirmations.pop(confirm_id)
        action_hash = self._action_hash(check_result.action)

        if approved:
            self._confirmed_actions.add(action_hash)
            logger.info("SAFETY: Confirmed [%s] — action approved", confirm_id)
        else:
            logger.info("SAFETY: Rejected [%s] — action denied", confirm_id)

        self._log_event("confirmation", {
            "confirm_id": confirm_id,
            "approved": approved,
            "action": check_result.action,
            "reason": check_result.reason,
        })

        return approved

    def get_pending_confirmations(self) -> list[dict]:
        """获取所有待确认的操作。"""
        return [
            {
                "confirm_id": cid,
                "level": result.level.value,
                "reason": result.reason,
                "prompt": result.confirmation_prompt,
                "action": result.action,
            }
            for cid, result in self._pending_confirmations.items()
        ]

    def is_confirmed(self, action: dict) -> bool:
        """检查操作是否已被人工确认。"""
        return self._action_hash(action) in self._confirmed_actions

    # ------------------------------------------------------------------
    # 规则管理
    # ------------------------------------------------------------------

    def add_rule(self, rule: SafetyRule) -> None:
        """动态添加安全规则。"""
        self._rules.append(rule)

    def remove_rule(self, name: str) -> bool:
        """移除指定名称的规则。"""
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.name != name]
        return len(self._rules) < before

    def list_rules(self) -> list[dict]:
        """列出所有规则。"""
        return [asdict(r) for r in self._rules]

    def get_safety_log(self, limit: int = 50) -> list[dict]:
        """获取安全日志。"""
        return self._log[-limit:]

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _match_rule(
        self,
        rule: SafetyRule,
        action: dict,
        reasoning: str,
        screen_text: str,
    ) -> str:
        """检查操作是否匹配规则，返回匹配原因或空字符串。"""
        action_type = action.get("type", "")

        # 文本匹配（针对 reasoning 和 screen_text）
        if rule.text_patterns:
            combined_text = f"{reasoning} {screen_text}".lower()
            for pattern in rule.text_patterns:
                if pattern.lower() in combined_text:
                    return f"文本匹配: '{pattern}'"

        # 输入内容匹配
        if rule.input_patterns and action_type == "input_text":
            input_text = action.get("text", "")
            for pattern in rule.input_patterns:
                if pattern.startswith("^") or pattern.endswith("$"):
                    # 正则匹配
                    if re.search(pattern, input_text):
                        return f"输入匹配: '{pattern}' → '{input_text}'"
                else:
                    if pattern.lower() in input_text.lower():
                        return f"输入匹配: '{pattern}'"

        # reasoning 匹配
        if rule.reasoning_patterns and reasoning:
            for pattern in rule.reasoning_patterns:
                if pattern.lower() in reasoning.lower():
                    return f"reasoning 匹配: '{pattern}'"

        return ""

    def _apply_rule(
        self, rule: SafetyRule, action: dict, match_reason: str
    ) -> SafetyCheckResult:
        """应用匹配的规则，返回检查结果。"""
        # observe_only 模式：只记录，不拦截
        if self._mode == "observe_only":
            self._log_event("observed", {
                "rule": rule.name,
                "level": rule.level.value,
                "match": match_reason,
                "action": action,
            })
            return self._safe(action, f"[观察模式] {rule.description}")

        # BLOCKED: 直接拒绝
        if rule.level == SafetyLevel.BLOCKED:
            self._log_event("blocked", {
                "rule": rule.name,
                "match": match_reason,
                "action": action,
            })
            return SafetyCheckResult(
                level=SafetyLevel.BLOCKED,
                allowed=False,
                reason=f"🚫 操作被禁止: {rule.description} ({match_reason})",
                action=action,
                matched_rule=rule.name,
            )

        # DANGER: 需要确认
        if rule.level == SafetyLevel.DANGER:
            # 检查是否已确认
            if self.is_confirmed(action):
                self._log_event("danger_confirmed", {
                    "rule": rule.name,
                    "match": match_reason,
                    "action": action,
                })
                return SafetyCheckResult(
                    level=SafetyLevel.DANGER,
                    allowed=True,
                    reason=f"⚠️ 危险操作已确认: {rule.description}",
                    action=action,
                    matched_rule=rule.name,
                )

            # permissive 模式：DANGER 也放行（但记录）
            if self._mode == "permissive":
                self._log_event("danger_permissive", {
                    "rule": rule.name,
                    "match": match_reason,
                    "action": action,
                })
                return SafetyCheckResult(
                    level=SafetyLevel.DANGER,
                    allowed=True,
                    reason=f"⚠️ [宽松模式] {rule.description} ({match_reason})",
                    action=action,
                    matched_rule=rule.name,
                )

            # strict 模式：需要人工确认
            self._log_event("danger_blocked", {
                "rule": rule.name,
                "match": match_reason,
                "action": action,
            })
            return SafetyCheckResult(
                level=SafetyLevel.DANGER,
                allowed=False,
                reason=f"⚠️ 危险操作需要确认: {rule.description} ({match_reason})",
                action=action,
                matched_rule=rule.name,
                requires_confirmation=True,
                confirmation_prompt=rule.confirmation_prompt or f"确认执行: {rule.description}?",
            )

        # CAUTION: 记录但允许
        if rule.level == SafetyLevel.CAUTION:
            self._log_event("caution", {
                "rule": rule.name,
                "match": match_reason,
                "action": action,
            })
            return SafetyCheckResult(
                level=SafetyLevel.CAUTION,
                allowed=True,
                reason=f"⚡ 注意: {rule.description} ({match_reason})",
                action=action,
                matched_rule=rule.name,
            )

        return self._safe(action, "规则未定义行为")

    def _safe(self, action: dict, reason: str) -> SafetyCheckResult:
        return SafetyCheckResult(
            level=SafetyLevel.SAFE,
            allowed=True,
            reason=reason,
            action=action,
        )

    def _action_hash(self, action: dict) -> str:
        """生成操作的唯一标识（用于确认去重）。"""
        return json.dumps(action, sort_keys=True, ensure_ascii=False)

    def _log_event(self, event_type: str, data: dict) -> None:
        """记录安全事件。"""
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "event": event_type,
            **data,
        }
        self._log.append(entry)
        # 保持日志不超过 1000 条
        if len(self._log) > 1000:
            self._log = self._log[-500:]

    def _load_custom_rules(self, config_path: str) -> None:
        """从 JSON 配置文件加载自定义规则。"""
        path = Path(config_path)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for rule_data in data.get("rules", []):
                self._rules.append(SafetyRule(
                    name=rule_data["name"],
                    level=SafetyLevel(rule_data["level"]),
                    text_patterns=rule_data.get("text_patterns", []),
                    input_patterns=rule_data.get("input_patterns", []),
                    url_patterns=rule_data.get("url_patterns", []),
                    reasoning_patterns=rule_data.get("reasoning_patterns", []),
                    description=rule_data.get("description", ""),
                    confirmation_prompt=rule_data.get("confirmation_prompt", ""),
                ))
        except Exception as exc:
            logger.error("Failed to load custom safety rules: %s", exc)


class SafetyBlockedError(Exception):
    """操作被安全守卫拦截。"""

    def __init__(self, check_result: SafetyCheckResult):
        self.check_result = check_result
        super().__init__(check_result.reason)
