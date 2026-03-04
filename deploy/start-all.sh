#!/bin/bash
# ============================================
# 云端一键启动所有服务
# Midscene 通过 frp 隧道连接手机 WiFi ADB
# 不需要 USB、不需要 SSH 隧道、不需要本地电脑
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

# ── 2. Midscene 服务 ──
echo "=== 2. 启动 Midscene 服务 (:9401) ==="
cd $PROJECT
sed -i 's/if (aNeedle\[aColumnName\] < 0)/if (aNeedle[aColumnName] < -1)/' node_modules/source-map/lib/source-map-consumer.js 2>/dev/null
nohup bun run src/midscene-client.ts > midscene.log 2>&1 &
echo "Midscene PID: $!"
sleep 2

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
echo -n "Midscene:    "; curl -s http://localhost:9401/health 2>/dev/null || echo "FAIL"
echo ""

echo ""
echo "=== 手机端操作 ==="
echo "1. 手机开启 WiFi ADB:"
echo "   设置 → 开发者选项 → 无线调试 → 开启"
echo "   或在 Termux 执行: su -c 'setprop service.adb.tcp.port 5555; stop adbd; start adbd'"
echo ""
echo "2. 手机 Termux 启动 frp 客户端:"
echo "   cd ~ && ./frpc -c frpc.toml"
echo ""
echo "3. 云端连接设备:"
echo "   curl -X POST http://localhost:9401/connect"
