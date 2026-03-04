#!/bin/bash
# ============================================
# 云端一键启动所有服务
# Midscene 通过 frp 隧道从本地 PC 映射过来
# 云端不启动 Midscene，只启动 frps + U2_Service
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

# 云端 ADB（仅用于 adb connect 远程设备）
export ANDROID_HOME=/opt/adb
export PATH="$ANDROID_HOME:$PATH"

echo ""

# ── 0. 清理残留 ──
echo "=== 0. 清理残留进程 ==="
pkill -f "uvicorn server:app" 2>/dev/null
pkill -f "midscene-client" 2>/dev/null
pkill -f "frps" 2>/dev/null
fuser -k 5037/tcp 2>/dev/null
sleep 1
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
echo "  本地 PC 执行: ./frpc -c deploy/frpc-local.toml"
echo ""

# ── 3. U2_Service ──
echo "=== 3. 启动 U2_Service (:9400) ==="
cd $PROJECT/u2-server
nohup uv run uvicorn server:app --host 0.0.0.0 --port 9400 > u2-server.log 2>&1 &
echo "U2_Service PID: $!"
sleep 3

# ── 健康检查 ──
echo ""
echo "=== 健康检查 ==="
echo -n "U2_Service:  "; curl -s http://localhost:9400/health 2>/dev/null || echo "FAIL"
echo ""
echo -n "Midscene:    "; curl -s http://localhost:9401/health 2>/dev/null || echo "FAIL (等待本地 frpc 连接)"
echo ""

echo ""
echo "=== 本地 PC 操作 ==="
echo "1. 启动模拟器 (Android Studio)"
echo "2. 启动 Midscene: bun run src/midscene-client.ts"
echo "3. 启动 frp 隧道: ./frpc -c deploy/frpc-local.toml"
echo "4. 连接设备: curl -X POST http://localhost:9401/connect (本地执行)"
echo ""
echo "隧道建立后，云端 U2_Service 自动通过 localhost:9401 调用本地 Midscene"
