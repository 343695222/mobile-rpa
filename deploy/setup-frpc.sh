#!/bin/bash
# 手机端一键安装 frpc 脚本
# 在 Termux 中运行: curl -sL https://raw.githubusercontent.com/343695222/mobile-rpa/main/deploy/setup-frpc.sh | bash

echo "=== 安装 frpc ==="

# 检测架构
ARCH=$(uname -m)
if [ "$ARCH" = "aarch64" ]; then
    FRP_ARCH="linux_arm64"
elif [ "$ARCH" = "armv7l" ]; then
    FRP_ARCH="linux_arm"
else
    echo "不支持的架构: $ARCH"
    exit 1
fi

FRP_VERSION="0.61.1"
FRP_FILE="frp_${FRP_VERSION}_${FRP_ARCH}"
FRP_URL="https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/${FRP_FILE}.tar.gz"

# 下载并解压
cd ~
if [ ! -f ~/frpc ]; then
    echo "下载 frpc..."
    curl -L -o frp.tar.gz "$FRP_URL"
    tar -xzf frp.tar.gz
    cp ${FRP_FILE}/frpc ~/frpc
    chmod +x ~/frpc
    rm -rf frp.tar.gz ${FRP_FILE}
    echo "frpc 安装完成"
else
    echo "frpc 已存在，跳过下载"
fi

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

echo "=== 配置完成 ==="
echo ""
echo "启动命令: ~/frpc -c ~/frpc.toml"
echo ""

# 直接启动
~/frpc -c ~/frpc.toml
