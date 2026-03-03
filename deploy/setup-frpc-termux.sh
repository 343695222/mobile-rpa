#!/bin/bash
# ============================================
# Termux 一键安装 frpc 脚本
# 在手机 Termux 里粘贴运行即可
# ============================================

set -e

echo "📱 正在安装 frpc..."

# 安装依赖
pkg update -y && pkg install -y wget

# 下载 frpc (ARM64)
cd ~
wget -q https://github.com/fatedier/frp/releases/download/v0.61.1/frp_0.61.1_linux_arm64.tar.gz
tar -xzf frp_0.61.1_linux_arm64.tar.gz
cp frp_0.61.1_linux_arm64/frpc ~/frpc
chmod +x ~/frpc
rm -rf frp_0.61.1_linux_arm64*

# 写入配置
cat > ~/frpc.toml << 'EOF'
serverAddr = "101.32.242.14"
serverPort = 7000
auth.token = "openclaw-frp-2024"

[[proxies]]
name = "autox-http"
type = "tcp"
localIP = "127.0.0.1"
localPort = 9500
remotePort = 9501
EOF

echo "✅ 安装完成！"
echo ""
echo "启动命令：  ~/frpc -c ~/frpc.toml"
echo "后台运行：  nohup ~/frpc -c ~/frpc.toml > ~/frpc.log 2>&1 &"
echo ""

# 直接启动
~/frpc -c ~/frpc.toml
