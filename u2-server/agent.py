"""
OpenClaw 自然语言交互 Agent

交互式命令行工具，接收自然语言输入，通过百炼平台 qwen-turbo 理解意图，
自动生成 JSON 指令调用 skill-cli.ts 执行手机操作。

用法：
    cd u2-server
    uv run python agent.py

    # 指定设备 ID（默认 a394960e）
    uv run python agent.py --device emulator-5554
"""

import asyncio
import json
import os
import subprocess
import sys

import httpx

from dashscope_client import DashScopeTextClient

# ============================================================
# 配置
# ============================================================

_text_model = os.environ.get("DASHSCOPE_TEXT_MODEL", "qwen-turbo")
text_client = DashScopeTextClient(model=_text_model)
DEFAULT_DEVICE = "a394960e"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_CLI = os.path.join(PROJECT_ROOT, "src", "skill-cli.ts")
U2_BASE = "http://localhost:9400"

# ============================================================
# SKILL.md 加载（让 LLM 知道有哪些能力）
# ============================================================

def load_skill_md() -> str:
    """读取 SKILL.md 中的指令说明部分。"""
    skill_path = os.path.join(PROJECT_ROOT, "SKILL.md")
    try:
        with open(skill_path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "SKILL.md not found"

# ============================================================
# 系统提示词
# ============================================================

SYSTEM_PROMPT_TEMPLATE = """你是 OpenClaw 移动端自动化 Agent。用户会用自然语言告诉你想在手机上做什么，你需要将用户意图转换为 JSON 指令。

## 你的能力（来自 SKILL.md）

{skill_md}

## 规则

1. 你必须返回一个合法的 JSON 指令，格式为 {{"type": "...", ...}}
2. 当前设备 ID 是 `{device_id}`，需要 deviceId 的指令自动填入这个值
3. 如果用户想打开某个 App（如"打开微信"、"打开抖音"），优先使用 `execute_action` 的 `app_start` 类型，常见包名：
   - 微信: com.tencent.mm
   - QQ: com.tencent.mobileqq
   - 抖音: com.ss.android.ugc.aweme
   - 支付宝: com.eg.android.AlipayGphone
   - 淘宝: com.taobao.taobao
   - 京东: com.jingdong.app.mall
   - 美团: com.sankuai.meituan
   - 拼多多: com.xunmeng.pinduoduo
   - 百度: com.baidu.searchbox
   - 高德地图: com.autonavi.minimap
   - 设置: com.android.settings
   - 相机: com.android.camera
   - 如果不确定包名，再用 smart_task
4. 如果用户的请求是一个复杂任务（比如"发消息给张三"），使用 `smart_task` 指令
5. 如果用户想看屏幕上有什么，使用 `analyze_screen` 指令
6. 如果用户想截图，使用 `screenshot` 指令
7. 如果用户想采集数据，使用 `collect_data` 指令
8. 如果用户想执行简单操作（点击某个坐标、输入文字），使用 `execute_action` 指令
9. 如果用户想查看设备，使用 `list_devices` 指令
10. 如果不确定用什么指令，优先用 `smart_task`

## 输出格式

只输出 JSON，不要输出任何其他文字。不要用 markdown 代码块包裹。

## 示例

用户: 打开微信
输出: {{"type": "smart_task", "deviceId": "{device_id}", "taskGoal": "打开微信"}}

用户: 屏幕上有什么
输出: {{"type": "analyze_screen", "deviceId": "{device_id}", "prompt": "请详细描述屏幕上的所有内容"}}

用户: 点击屏幕中间
输出: {{"type": "execute_action", "deviceId": "{device_id}", "action": {{"type": "tap", "x": 540, "y": 960}}}}

用户: 采集微信联系人
输出: {{"type": "collect_data", "deviceId": "{device_id}", "app": "微信", "dataType": "联系人列表"}}

用户: 截个图看看
输出: {{"type": "screenshot", "deviceId": "{device_id}"}}
"""


# ============================================================
# LLM 调用（百炼平台 DashScopeTextClient）
# ============================================================

async def call_llm(messages: list[dict]) -> str:
    """调用百炼平台文本模型，返回文本响应。"""
    return await text_client.chat(messages)

# ============================================================
# 指令执行
# ============================================================

def execute_skill_command(json_cmd: dict) -> dict:
    """通过 bun run skill-cli.ts 执行指令。"""
    try:
        result = subprocess.run(
            ["bun", "run", SKILL_CLI],
            input=json.dumps(json_cmd),
            capture_output=True,
            text=True,
            timeout=120,
            cwd=PROJECT_ROOT,
        )
        stdout = result.stdout.strip()
        if stdout:
            # skill-cli 输出可能有多行，取最后一个 JSON
            for line in reversed(stdout.split("\n")):
                line = line.strip()
                if line.startswith("{"):
                    return json.loads(line)
            return {"status": "success", "message": stdout[:500]}
        if result.stderr:
            return {"status": "error", "message": result.stderr[:500]}
        return {"status": "error", "message": "无输出"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "执行超时 (120s)"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def execute_via_u2(json_cmd: dict) -> dict | None:
    """尝试直接通过 U2 HTTP API 执行（更快，跳过 bun 启动开销）。"""
    cmd_type = json_cmd.get("type", "")
    device_id = json_cmd.get("deviceId", DEFAULT_DEVICE)

    route_map = {
        "screenshot": ("POST", f"/device/{device_id}/screenshot", None),
        "list_devices": ("GET", "/devices", None),
        "analyze_screen": (
            "POST",
            "/vision/analyze",
            {"device_id": device_id, "prompt": json_cmd.get("prompt", "描述屏幕内容")},
        ),
        "smart_task": (
            "POST",
            "/vision/smart_task",
            {
                "device_id": device_id,
                "goal": json_cmd.get("taskGoal", ""),
                "max_steps": json_cmd.get("maxSteps", 20),
            },
        ),
        "collect_data": (
            "POST",
            "/collect",
            {
                "device_id": device_id,
                "app": json_cmd.get("app", ""),
                "data_type": json_cmd.get("dataType", ""),
                "query": json_cmd.get("query", ""),
                "force_strategy": json_cmd.get("forceStrategy"),
            },
        ),
    }

    if cmd_type not in route_map:
        return None  # 回退到 bun

    method, path, body = route_map[cmd_type]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            if method == "GET":
                resp = await client.get(f"{U2_BASE}{path}")
            else:
                resp = await client.post(f"{U2_BASE}{path}", json=body)
            return resp.json()
    except Exception:
        return None  # U2 不可用，回退到 bun


async def execute_command(json_cmd: dict) -> dict:
    """执行指令：优先走 U2 HTTP，不行就走 bun。"""
    # 先尝试 U2 直连
    result = await execute_via_u2(json_cmd)
    if result is not None:
        return result

    # 回退到 bun
    return execute_skill_command(json_cmd)

# ============================================================
# 结果摘要（让 LLM 把结果翻译成人话）
# ============================================================

async def summarize_result(user_input: str, json_cmd: dict, result: dict) -> str:
    """让 LLM 把执行结果翻译成自然语言。"""
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个手机自动化助手。用户让你操作手机，你已经执行了操作。"
                "现在请用简洁的中文告诉用户执行结果。"
                "如果结果包含 base64 图片数据，只说'截图已完成'，不要输出 base64 内容。"
                "如果是 smart_task，总结每一步做了什么和最终结果。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"用户请求: {user_input}\n"
                f"执行的指令: {json.dumps(json_cmd, ensure_ascii=False)}\n"
                f"执行结果: {json.dumps(result, ensure_ascii=False)[:2000]}"
            ),
        },
    ]
    return await call_llm(messages)


# ============================================================
# 交互主循环
# ============================================================

async def main():
    device_id = DEFAULT_DEVICE

    # 解析命令行参数
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--device" and i + 1 < len(args):
            device_id = args[i + 1]
            i += 2
        else:
            i += 1

    skill_md = load_skill_md()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        skill_md=skill_md, device_id=device_id
    )

    print("=" * 50)
    print("  OpenClaw 自然语言手机控制 Agent")
    print(f"  设备: {device_id}")
    print(f"  模型: {_text_model}")
    print("  输入 'quit' 或 'exit' 退出")
    print("=" * 50)
    print()

    conversation: list[dict] = [{"role": "system", "content": system_prompt}]

    while True:
        try:
            sys.stdout.write("你> ")
            sys.stdout.flush()
            raw = sys.stdin.buffer.readline()
            if not raw:
                print("\n再见！")
                break
            # Try utf-8 first, fallback to latin-1 (lossless)
            try:
                user_input = raw.decode("utf-8").strip()
            except UnicodeDecodeError:
                user_input = raw.decode("latin-1").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("再见！")
            break

        # 1. LLM 理解意图，生成 JSON 指令
        conversation.append({"role": "user", "content": user_input})

        print("🤔 理解中...")
        llm_response = await call_llm(conversation)

        # 解析 JSON
        try:
            # 去掉可能的 markdown 代码块
            clean = llm_response.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
                clean = clean.strip()
            json_cmd = json.loads(clean)
        except json.JSONDecodeError:
            print(f"⚠️  模型返回了非 JSON 内容: {llm_response[:200]}")
            conversation.append({"role": "assistant", "content": llm_response})
            continue

        print(f"📋 指令: {json.dumps(json_cmd, ensure_ascii=False)}")

        # 2. 执行指令
        print("⚡ 执行中...")
        result = await execute_command(json_cmd)

        # 3. 摘要结果
        print("📝 整理结果...")
        summary = await summarize_result(user_input, json_cmd, result)

        print(f"\n🤖 {summary}\n")

        # 更新对话历史（保持简短，避免 token 爆炸）
        conversation.append({"role": "assistant", "content": clean})
        # 只保留最近 10 轮对话
        if len(conversation) > 21:  # 1 system + 10 pairs
            conversation = [conversation[0]] + conversation[-20:]


if __name__ == "__main__":
    asyncio.run(main())
