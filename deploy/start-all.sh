#!/bin/bash
# 一键启动所有云端服务
PROJECT=~/.openclaw/workspace/skills/mobile-rpa

# ── 环境变量（确保子进程能继承）──
export ANDROID_HOME=/opt/adb
export MIDSCENE_ADB_PATH=/opt/adb/adb
export PATH="$ANDROID_HOME:$PATH"

# 加载 .env 文件（Midscene 模型配置 + DashScope API Key）
if [ -f "$PROJECT/.env" ]; then
  set -a
  source "$PROJECT/.env"
  set +a
  echo "✓ 已加载 .env 配置"
else
  echo "⚠ 未找到 .env 文件，Midscene AI 功能将不可用"
  echo "  请执行: cp $PROJECT/.env.example $PROJECT/.env 并填入 API Key"
fi

echo ""

# ── 0. 清理残留进程 ──
echo "=== 0. 清理残留进程 ==="
pkill -f "uvicorn server:app" 2>/dev/null
pkill -f "midscene-client" 2>/dev/null
pkill -f "frps" 2>/dev/null
# 杀掉云端 adb server 进程，避免和 SSH 隧道冲突（不用 adb kill-server，那会重新启动）
fuser -k 5037/tcp 2>/dev/null
sleep 1

echo ""

# ── 1. 启动 frp 服务端 ──
echo "=== 1. 启动 frp 服务端 ==="
cd $PROJECT
nohup frps -c deploy/frps.toml > frps-run.log 2>&1 &
echo "frps PID: $!"

sleep 1

# ── 2. 启动 Midscene 服务 (:9401) ──
echo "=== 2. 启动 Midscene 服务 (:9401) ==="
cd $PROJECT
# 修复 Bun + source-map 兼容性 bug（column = -1 崩溃）
sed -i 's/if (aNeedle\[aColumnName\] < 0)/if (aNeedle[aColumnName] < -1)/' node_modules/source-map/lib/source-map-consumer.js 2>/dev/null
nohup bun run src/midscene-client.ts > midscene.log 2>&1 &
echo "Midscene PID: $!"

sleep 2

# ── 3. 启动 U2_Service (:9400) ──
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

# 注意：不要在云端运行 adb devices！它会自动启动本地 adb server 抢占 5037 端口，
# 导致 SSH 隧道失效。设备连接通过 Midscene /connect 端点验证。

echo ""
echo "=== 下一步 ==="
echo "1. 本地 Windows: adb kill-server && adb start-server && adb devices"
echo "2. 本地 Windows: ssh -R 5037:127.0.0.1:5037 root@101.32.242.14"
echo "   (如果 5037 被占用，先在云端执行: kill \$(fuser 5037/tcp 2>/dev/null | head -1))"
echo "3. 云端验证: curl -X POST http://localhost:9401/connect"
echo "4. 手机运行 AutoX.js 服务脚本"
echo "5. 手机 Termux 执行: ./frpc -c frpc.toml"
echo ""
echo "⚠ 切勿在云端运行 adb devices，会抢占 SSH 隧道端口！"
