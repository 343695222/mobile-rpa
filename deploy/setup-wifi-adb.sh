#!/bin/bash
# ============================================
# 手机端 WiFi ADB 启动脚本（Termux 中运行）
# 开启 WiFi ADB 后，frp 会把 5555 端口映射到云端
# ============================================

echo "=== 开启 WiFi ADB ==="

# 方法1: 有 root 权限
if command -v su &>/dev/null; then
  echo "检测到 root，使用 root 方式开启..."
  su -c 'setprop service.adb.tcp.port 5555; stop adbd; start adbd'
  echo "✓ WiFi ADB 已开启 (端口 5555)"
else
  echo "无 root 权限，请手动开启:"
  echo "  设置 → 开发者选项 → 无线调试 → 开启"
  echo ""
  echo "或者先用 USB 连电脑，在电脑上执行:"
  echo "  adb tcpip 5555"
  echo "  adb disconnect"
  echo "然后拔掉 USB 线"
fi

echo ""

# 验证
echo "=== 验证 ADB 端口 ==="
if ss -tlnp 2>/dev/null | grep -q ":5555"; then
  echo "✓ 端口 5555 已监听"
elif netstat -tlnp 2>/dev/null | grep -q ":5555"; then
  echo "✓ 端口 5555 已监听"
else
  echo "⚠ 端口 5555 未监听，WiFi ADB 可能未开启"
fi

echo ""
echo "=== 下一步 ==="
echo "启动 frp 客户端: ./frpc -c frpc.toml"
