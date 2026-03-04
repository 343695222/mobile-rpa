#!/bin/bash
# 一键停止所有云端服务
echo "=== 停止所有服务 ==="
pkill -f "uvicorn server:app" && echo "✓ U2_Service stopped" || echo "- U2_Service not running"
pkill -f "frps" && echo "✓ frps stopped" || echo "- frps not running"
echo ""
echo "注意: Midscene 运行在本地 Windows，请在本地关闭"
echo "=== 完成 ==="
