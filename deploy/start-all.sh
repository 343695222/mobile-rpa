#!/bin/bash
# 一键启动所有云端服务
PROJECT=~/.openclaw/workspace/skills/mobile-rpa

echo "=== 1. 启动 frp 服务端 ==="
cd $PROJECT
nohup frps -c deploy/frps.toml > frps-run.log 2>&1 &
echo "frps PID: $!"

sleep 1

echo "=== 2. 启动 Midscene 服务 (:9401) ==="
cd $PROJECT
# 修复 Bun + source-map 兼容性 bug（column = -1 崩溃）
sed -i 's/if (aNeedle\[aColumnName\] < 0)/if (aNeedle[aColumnName] < -1)/' node_modules/source-map/lib/source-map-consumer.js 2>/dev/null
nohup bun run src/midscene-client.ts > midscene.log 2>&1 &
echo "Midscene PID: $!"

sleep 2

echo "=== 3. 启动 U2_Service (:9400) ==="
cd $PROJECT/u2-server
nohup uv run uvicorn server:app --host 0.0.0.0 --port 9400 > u2-server.log 2>&1 &
echo "U2_Service PID: $!"

sleep 3

echo ""
echo "=== 健康检查 ==="
echo -n "U2_Service:  "; curl -s http://localhost:9400/health 2>/dev/null || echo "FAIL"
echo ""
echo -n "Midscene:    "; curl -s http://localhost:9401/health 2>/dev/null || echo "FAIL"
echo ""
echo ""
echo "=== 等待手机端连接 ==="
echo "1. 手机运行 AutoX.js 服务脚本"
echo "2. Termux 执行: ./frpc -c frpc.toml"
