#!/bin/bash
# ============================================
# 云端一键启动所有服务
# 包括：frps + U2_Service + OpenClaw Gateway
# Midscene 通过 frp 隧道从本地 PC 映射过来
# ============================================
PROJECT=~/.openclaw/workspace/skills/mobile-rpa

# ── 加载 .env ──
if [ -f "$PROJECT/.env" ]; then
  sed -i 's/\r$//' "$PROJECT/.env"
  set -a
  source "$PROJECT/.env"
  set +a
  echo "✓ 已加载 .env 配置"
else
  echo "⚠ 未找到 .env，请执行: cp .env.example .env 并填入 API Key"
fi

# 云端 ADB
export ANDROID_HOME=/opt/adb
export PATH="$ANDROID_HOME:$PATH"

echo ""

# ── 0. 清理残留 ──
echo "=== 0. 清理残留进程 ==="
pkill -f "uvicorn server:app" 2>/dev/null
pkill -f "midscene-client" 2>/dev/null
pkill -f "frps" 2>/dev/null
pkill -f "openclaw" 2>/dev/null
fuser -k 5037/tcp 2>/dev/null
sleep 2
echo ""

# ── 1. frps ──
echo "=== 1. 启动 frp 服务端 ==="
cd $PROJECT
nohup frps -c deploy/frps.toml > frps-run.log 2>&1 &
echo "frps PID: $!"
sleep 1

# ── 2. Midscene 说明 ──
echo "=== 2. Midscene 服务 (:9401) ==="
echo "  ⚠ 云端不启动 Midscene，通过 frp 隧道使用本地 PC 的 Midscene"
echo "  本地 PC 执行: deploy\\start-local-to-cloud.cmd"
echo ""

# ── 3. U2_Service ──
echo "=== 3. 启动 U2_Service (:9400) ==="
cd $PROJECT/u2-server
nohup uv run uvicorn server:app --host 0.0.0.0 --port 9400 > u2-server.log 2>&1 &
echo "U2_Service PID: $!"
sleep 3

# ── 4. OpenClaw Gateway ──
echo "=== 4. 重启 OpenClaw Gateway ==="
nohup openclaw gateway > ~/.openclaw/openclaw.log 2>&1 &
echo "OpenClaw Gateway PID: $!"
sleep 5

# ── 健康检查 ──
echo ""
echo "=== 健康检查 ==="
echo -n "U2_Service:  "; curl -s http://localhost:9400/health 2>/dev/null || echo "FAIL"
echo ""
echo -n "Midscene:    "; curl -s http://localhost:9401/health 2>/dev/null || echo "FAIL (等待本地 frpc 连接)"
echo ""

# 检查 OpenClaw 进程
echo -n "OpenClaw:    "
if pgrep -f "openclaw-gateway" > /dev/null 2>&1; then
  echo "✓ Gateway 运行中"
else
  echo "✗ Gateway 未启动，请检查 ~/.openclaw/openclaw.log"
fi

# 检查 SKILL.md 是否为新版本
echo -n "SKILL.md:    "
MIDSCENE_COUNT=$(grep -c midscene $PROJECT/SKILL.md 2>/dev/null)
if [ "$MIDSCENE_COUNT" -gt 0 ] 2>/dev/null; then
  echo "✓ Midscene 版本 (${MIDSCENE_COUNT} 处引用)"
else
  echo "✗ 旧版本！需要手动更新 SKILL.md（CRLF 换行符问题）"
fi

echo ""
echo "=== 本地 PC 操作 ==="
echo "1. 启动模拟器 (Android Studio)"
echo "2. 双击运行: deploy\\start-local-to-cloud.cmd"
echo ""
echo "隧道建立后，云端 U2_Service 自动通过 localhost:9401 调用本地 Midscene"
