# WiFi 无线连接部署（3步搞定）

不需要 USB 线，手机连 WiFi 就能用。

## 架构
```
QQ → Agent → Python:9400 → frp隧道:9501 → 手机:9500 (AutoJS)
```

---

## 第1步：云服务器启动 frps（一次性）

SSH 到云服务器，执行：

```bash
# 下载 frp（如果没装过）
cd /opt
wget -q https://github.com/fatedier/frp/releases/download/v0.61.1/frp_0.61.1_linux_amd64.tar.gz
tar -xzf frp_0.61.1_linux_amd64.tar.gz
cp frp_0.61.1_linux_amd64/frps /usr/local/bin/frps
rm -rf frp_0.61.1_linux_amd64*

# 放行端口
firewall-cmd --add-port=7000/tcp --permanent 2>/dev/null; firewall-cmd --reload 2>/dev/null

# 启动 frps（后台运行）
cd ~/.openclaw/workspace/skills/mobile-rpa
nohup frps -c deploy/frps.toml > /tmp/frps.log 2>&1 &
```

验证：`ps aux | grep frps`

## 第2步：手机 Termux 安装 frpc（一次性）

1. 手机安装 Termux（从 F-Droid 下载，不要用 Play Store 版）
2. 打开 Termux，粘贴以下全部内容：

```bash
pkg update -y && pkg install -y wget && cd ~ && wget -q https://github.com/fatedier/frp/releases/download/v0.61.1/frp_0.61.1_linux_arm64.tar.gz && tar -xzf frp_0.61.1_linux_arm64.tar.gz && cp frp_0.61.1_linux_arm64/frpc ~/frpc && chmod +x ~/frpc && rm -rf frp_0.61.1_linux_arm64* && cat > ~/frpc.toml << 'EOF'
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
echo "✅ 安装完成！运行: ~/frpc -c ~/frpc.toml"
```

3. 启动 frpc：
```bash
~/frpc -c ~/frpc.toml
```

看到 `proxy added ... autox-http` 就成功了。

## 第3步：云服务器启动 server_autox

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa/u2-server
nohup uv run uvicorn server_autox:app --host 0.0.0.0 --port 9400 > server.log 2>&1 &
```

## 验证

在云服务器上：
```bash
# 测试 frp 隧道
curl -s -X POST http://localhost:9501/health

# 测试 server_autox
curl -s http://localhost:9400/health
```

## 日常使用

每次用之前确保：
1. 手机 AutoJS 脚本在运行（autox-server-v2.js）
2. 手机 Termux 里 frpc 在运行：`~/frpc -c ~/frpc.toml`
3. 云服务器 frps 和 server_autox 在运行

frpc 后台运行（不用一直开着 Termux）：
```bash
nohup ~/frpc -c ~/frpc.toml > ~/frpc.log 2>&1 &
```
