# 安全设计：敏感操作防护机制

## 核心问题

分析竞品平台时，有些接口只有真实操作才能触发抓包：
- 竞拍出价 → 需要点"出价"按钮才能抓到提交接口
- 支付确认 → 需要进入支付流程才能看到支付接口
- 下单购买 → 需要点"立即购买"才能抓到订单接口

但 AI 绝对不能真的完成这些操作（会产生真实交易）。

## 解决方案：三层防护

```
┌─────────────────────────────────────────────┐
│  Layer 1: 操作分级 — 哪些能做，哪些不能做     │
│  Layer 2: 拦截点 — 在关键时刻暂停等人确认     │
│  Layer 3: 网络层拦截 — 即使点了也不让请求发出  │
└─────────────────────────────────────────────┘
```


## Layer 1: 操作分级系统

把所有可能的操作分为 4 个安全等级：

```
Level 0 (安全): 浏览、截图、滑动、返回
  → AI 完全自主，无需确认

Level 1 (低风险): 点击列表项、进入详情页、搜索
  → AI 自主执行，记录日志

Level 2 (中风险): 点击"出价"按钮、进入支付页面、填写表单
  → AI 执行到这一步时暂停，等人确认后继续
  → 目的：抓到请求的构造过程，但不提交

Level 3 (高危): 确认支付、确认出价、确认下单、转账
  → 绝对禁止，AI 不允许执行
  → 即使人确认也需要二次确认 + 网络层拦截
```

### 关键词识别规则

```python
# 安全等级关键词配置
SAFETY_RULES = {
    "level_3_blocked": {
        "keywords": [
            "确认支付", "立即支付", "确认出价", "提交出价",
            "确认购买", "立即购买", "确认下单", "立即下单",
            "确认转账", "支付", "付款", "扣款",
            "确定", "提交",  # 在出价/支付上下文中
        ],
        "context_keywords": [  # 需要结合上下文判断
            "出价", "竞拍", "支付", "购买", "下单", "转账",
        ],
        "action": "block",  # 直接阻止
    },
    "level_2_pause": {
        "keywords": [
            "出价", "竞拍", "加入竞拍", "我要出价",
            "购买", "加入购物车", "立即抢购",
            "充值", "提现",
        ],
        "action": "pause_and_ask",  # 暂停等人确认
    },
    "level_1_log": {
        "keywords": [
            "搜索", "筛选", "排序", "查看详情",
            "收藏", "关注", "分享",
        ],
        "action": "allow_with_log",
    },
    "level_0_safe": {
        "keywords": [
            "返回", "首页", "列表", "刷新", "滑动",
            "截图", "查看",
        ],
        "action": "allow",
    },
}
```

## Layer 2: 操作拦截器 (ActionGuard)

在 VisionAgent 的操作执行前插入安全检查。

```python
# u2-server/action_guard.py

class ActionGuard:
    """操作安全守卫 — 在执行前检查操作的安全等级"""
    
    def __init__(self):
        self._pending_confirmation: dict | None = None
        self._blocked_log: list[dict] = []
        self._analysis_mode = False  # 分析模式开关
    
    def enable_analysis_mode(self):
        """启用分析模式 — 更严格的安全检查"""
        self._analysis_mode = True
    
    def check_action(self, action: dict, screen_context: str = "") -> dict:
        """
        检查操作的安全等级。
        
        Args:
            action: VisionAgent 要执行的操作
            screen_context: 当前屏幕的文字描述（GLM 分析结果）
        
        Returns:
            {
                "allowed": bool,
                "level": int,          # 0-3
                "reason": str,
                "action": "allow" | "pause" | "block",
                "requires_confirmation": bool,
            }
        """
        # 分析操作类型
        action_type = action.get("type", "")
        
        # 非点击操作通常安全
        if action_type in ("swipe", "wait", "key_event"):
            key_code = action.get("keyCode", 0)
            if key_code in (3, 4):  # Home, Back — 安全
                return self._allow(0, "导航操作")
            return self._allow(0, "非交互操作")
        
        if action_type == "input_text":
            text = action.get("text", "")
            # 检查是否在输入金额
            if self._looks_like_amount(text):
                return self._pause(2, f"检测到可能的金额输入: {text}")
            return self._allow(1, "文本输入")
        
        if action_type != "tap":
            return self._allow(0, "未知操作类型")
        
        # === 点击操作 — 需要结合屏幕上下文判断 ===
        
        # 检查屏幕上下文中的危险关键词
        level = self._assess_tap_risk(screen_context)
        
        if level >= 3:
            self._blocked_log.append({
                "action": action,
                "context": screen_context[:200],
                "reason": "检测到高危操作（支付/确认出价）",
            })
            return self._block(3, "检测到高危操作，已阻止。屏幕上下文包含支付/确认相关元素。")
        
        if level >= 2:
            self._pending_confirmation = {
                "action": action,
                "context": screen_context[:500],
                "level": level,
            }
            return self._pause(2, 
                "检测到中风险操作（进入出价/购买流程）。"
                "这一步会触发请求但不会提交。"
                "请确认是否继续（用于抓包分析）。"
            )
        
        return self._allow(level, "安全操作")
    
    def confirm_pending(self) -> dict | None:
        """人工确认待处理的操作"""
        action = self._pending_confirmation
        self._pending_confirmation = None
        return action
    
    def reject_pending(self) -> None:
        """人工拒绝待处理的操作"""
        if self._pending_confirmation:
            self._blocked_log.append({
                **self._pending_confirmation,
                "reason": "人工拒绝",
            })
        self._pending_confirmation = None
    
    def get_blocked_log(self) -> list[dict]:
        """获取被阻止的操作日志"""
        return list(self._blocked_log)
    
    # === 内部方法 ===
    
    def _assess_tap_risk(self, context: str) -> int:
        """评估点击操作的风险等级"""
        if not context:
            return 1  # 无上下文时默认低风险
        
        ctx_lower = context.lower()
        
        # Level 3: 确认类操作
        level3_patterns = [
            "确认支付", "立即支付", "确认出价", "提交出价",
            "确认购买", "确认下单", "立即下单", "确认转账",
            "输入密码", "支付密码", "验证码",
        ]
        for p in level3_patterns:
            if p in ctx_lower:
                return 3
        
        # Level 3: "确认/提交" + 交易上下文
        if any(w in ctx_lower for w in ["确认", "提交", "确定"]):
            if any(w in ctx_lower for w in ["出价", "支付", "购买", "下单", "转账", "金额"]):
                return 3
        
        # Level 2: 进入交易流程
        level2_patterns = [
            "出价", "竞拍", "我要出价", "参与竞拍",
            "购买", "加入购物车", "立即抢购",
            "充值", "提现", "余额",
        ]
        for p in level2_patterns:
            if p in ctx_lower:
                return 2
        
        return 0  # 安全
    
    def _looks_like_amount(self, text: str) -> bool:
        """检查文本是否像金额"""
        import re
        # 纯数字或带小数点的数字
        return bool(re.match(r'^\d+\.?\d*$', text.strip()))
    
    def _allow(self, level: int, reason: str) -> dict:
        return {"allowed": True, "level": level, "reason": reason, 
                "action": "allow", "requires_confirmation": False}
    
    def _pause(self, level: int, reason: str) -> dict:
        return {"allowed": False, "level": level, "reason": reason,
                "action": "pause", "requires_confirmation": True}
    
    def _block(self, level: int, reason: str) -> dict:
        return {"allowed": False, "level": level, "reason": reason,
                "action": "block", "requires_confirmation": False}
```

## Layer 3: 网络层拦截 (RequestBlocker)

即使 AI 意外点了确认按钮，在网络层也要拦住真实的提交请求。
这是最后一道防线。

```python
# u2-server/request_blocker.py
# 通过 mitmproxy addon 实现

class RequestBlocker:
    """网络层请求拦截器 — 最后一道防线
    
    工作原理：
    1. 在 mitmproxy 中注册为 addon
    2. 对所有经过代理的请求进行检查
    3. 匹配到危险请求时，直接返回 mock 响应，不转发到真实服务器
    4. 同时记录被拦截的请求（用于分析接口结构）
    """
    
    # 危险请求的 URL 关键词
    BLOCK_URL_PATTERNS = [
        "/order/create", "/order/submit", "/order/confirm",
        "/pay/", "/payment/", "/charge/",
        "/bid/submit", "/bid/create", "/bid/confirm",
        "/auction/bid", "/auction/offer",
        "/trade/", "/transaction/",
        "/transfer/",
    ]
    
    # 危险请求的 body 关键词
    BLOCK_BODY_PATTERNS = [
        "price", "amount", "bid_price", "offer_price",
        "pay_type", "payment_method",
        "order_id", "trade_no",
    ]
    
    def __init__(self):
        self._blocked_requests: list[dict] = []
        self._enabled = True
        self._custom_patterns: list[str] = []
    
    def should_block(self, url: str, method: str, body: str = "") -> tuple[bool, str]:
        """检查请求是否应该被拦截"""
        if not self._enabled:
            return False, ""
        
        # 只拦截 POST/PUT（GET 请求通常安全）
        if method.upper() not in ("POST", "PUT", "PATCH"):
            return False, ""
        
        url_lower = url.lower()
        
        # URL 模式匹配
        for pattern in self.BLOCK_URL_PATTERNS + self._custom_patterns:
            if pattern in url_lower:
                return True, f"URL 匹配危险模式: {pattern}"
        
        # Body 关键词匹配（针对出价/支付类请求）
        if body:
            body_lower = body.lower()
            # 同时包含金额相关字段 + 提交动作
            has_amount = any(p in body_lower for p in ["price", "amount", "money", "金额"])
            has_action = any(p in body_lower for p in ["submit", "confirm", "create", "提交", "确认"])
            if has_amount and has_action:
                return True, "请求体包含金额+提交动作"
        
        return False, ""
    
    def intercept(self, url: str, method: str, headers: dict, body: str) -> dict:
        """拦截请求并记录（不转发到真实服务器）
        
        Returns:
            被拦截的请求详情（用于接口分析）
        """
        record = {
            "url": url,
            "method": method,
            "headers": headers,
            "body": body,
            "intercepted": True,
            "reason": "安全拦截：检测到交易类请求",
        }
        self._blocked_requests.append(record)
        return record
    
    def get_mock_response(self) -> dict:
        """返回给 App 的 mock 响应（让 App 以为请求成功了）"""
        return {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body": '{"code": 0, "msg": "success", "data": null}',
        }
    
    def get_blocked_requests(self) -> list[dict]:
        """获取所有被拦截的请求（这些就是我们要分析的接口）"""
        return list(self._blocked_requests)
    
    def add_custom_pattern(self, pattern: str):
        """添加自定义拦截模式"""
        self._custom_patterns.append(pattern)
    
    def disable(self):
        """临时禁用拦截（谨慎使用）"""
        self._enabled = False
    
    def enable(self):
        """启用拦截"""
        self._enabled = True
```

## 集成到 VisionAgent 的流程

```python
# 修改 vision_agent.py 的 run_task 方法

async def run_task_safe(self, device_id, goal, max_steps=20):
    """带安全检查的任务执行"""
    guard = ActionGuard()
    guard.enable_analysis_mode()
    
    for step in range(1, max_steps + 1):
        # 1. 截图 + GLM 分析
        decision = await self.decide_next_action(device_id, goal, history)
        
        if decision.get("done"):
            break
        
        action = decision.get("action")
        if not action:
            continue
        
        # 2. 安全检查（关键！）
        screen_desc = decision.get("reasoning", "")
        safety = guard.check_action(action, screen_desc)
        
        if safety["action"] == "block":
            # 高危操作 — 直接跳过，记录日志
            steps.append({
                "step": step,
                "action": action,
                "blocked": True,
                "reason": safety["reason"],
            })
            # 不执行操作，但继续分析（按返回键退出危险页面）
            self.device_manager.key_event(device_id, 4)  # Back
            continue
        
        if safety["action"] == "pause":
            # 中风险操作 — 暂停等人确认
            steps.append({
                "step": step,
                "action": action,
                "paused": True,
                "reason": safety["reason"],
                "awaiting_confirmation": True,
            })
            # 返回暂停状态，等待人工确认
            return {
                "success": False,
                "paused": True,
                "message": safety["reason"],
                "pending_action": action,
                "steps": steps,
                "step_number": step,
            }
        
        # 3. 安全操作 — 正常执行
        await self._execute_action(device_id, action)
```

## 实际操作流程（以分析竞拍出价为例）

```
1. AI 打开聚宝猪小程序                    → Level 0 ✅ 自动执行
2. AI 浏览竞拍列表                        → Level 0 ✅ 自动执行
3. AI 点击某个竞拍详情                    → Level 1 ✅ 自动执行
4. AI 看到"我要出价"按钮，准备点击         → Level 2 ⏸️ 暂停
   
   系统输出：
   "检测到中风险操作：进入出价流程。
    这一步会打开出价界面，用于抓包分析接口结构。
    请确认是否继续？[Y/N]"
   
   人工确认 Y → AI 点击"我要出价"
   
5. AI 看到出价输入框，准备输入金额          → Level 2 ⏸️ 暂停
   
   系统输出：
   "检测到金额输入操作。
    建议输入一个明显不合理的测试金额（如 0.01）。
    请确认是否继续？[Y/N]"
   
   人工确认 Y → AI 输入 0.01
   
6. AI 看到"确认出价"按钮                  → Level 3 🚫 阻止
   
   系统输出：
   "⛔ 高危操作已阻止：确认出价。
    已抓到出价接口的请求构造（URL、参数、Header）。
    AI 将自动按返回键退出。"
   
   同时 mitmproxy RequestBlocker 也在网络层拦截，
   即使 AI 意外点了确认，请求也不会真的发出去。
   
7. 分析完成，输出报告：
   "出价接口: POST /api/bid/submit
    参数: {auction_id, price, token}
    鉴权: Bearer Token
    难度: Level 2（需要登录态）"
```

## 安全配置文件

每个平台可以有独立的安全配置：

```json
// u2-server/platform_configs/jubaozhu_safety.json
{
  "platform_name": "聚宝猪",
  "block_url_patterns": [
    "/bid/submit",
    "/bid/confirm", 
    "/order/create",
    "/pay/"
  ],
  "pause_keywords": [
    "出价", "竞拍", "我要出价"
  ],
  "block_keywords": [
    "确认出价", "提交出价", "确认支付"
  ],
  "safe_exploration_pages": [
    "首页", "竞拍列表", "猪源详情", "历史成交"
  ],
  "max_exploration_depth": 3,
  "allow_form_fill": false,
  "allow_amount_input": false
}
```

## FastAPI 安全端点

```python
# 新增端点
POST /safety/check          # 手动检查操作安全性
POST /safety/confirm        # 确认暂停的操作
POST /safety/reject         # 拒绝暂停的操作
GET  /safety/blocked_log    # 查看被阻止的操作日志
GET  /safety/blocked_requests  # 查看被拦截的网络请求（这些就是要分析的接口）
PUT  /safety/config         # 更新平台安全配置
```

## 关键设计原则

1. **默认拒绝**: 不确定的操作默认阻止，宁可漏抓接口也不能产生真实交易
2. **双重防护**: 操作层 + 网络层两道防线，任何一层都能独立阻止危险操作
3. **人在回路**: Level 2 操作必须人工确认，Level 3 操作直接阻止
4. **拦截即分析**: 被网络层拦截的请求本身就是我们要分析的接口数据
5. **可审计**: 所有操作（包括被阻止的）都有完整日志
