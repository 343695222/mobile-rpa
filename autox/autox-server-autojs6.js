/**
 * AutoJs6 手机端 HTTP 服务脚本
 * 
 * 使用 Java ServerSocket 实现 HTTP 服务器
 * （AutoJs6 的 http 模块不支持 createServer）
 * 
 * 端口：9500
 */

"auto";

auto.waitFor();
console.log("[Server] 无障碍服务已启用");

try {
    images.requestScreenCapture();
    console.log("[Server] 截图权限已获取");
} catch (e) {
    console.warn("[Server] 截图权限申请失败: " + e.message);
}

// ============================================================
// 工具函数
// ============================================================

function ok(data) {
    return JSON.stringify({ success: true, data: data || null });
}

function fail(error) {
    return JSON.stringify({ success: false, error: String(error) });
}

// ============================================================
// 端点处理
// ============================================================

function handleHealth() {
    return ok({ status: "running", port: 9500, ts: new Date().toISOString() });
}

function handleClick(body) {
    if (body.x == null || body.y == null) return fail("缺少参数: x, y");
    var x = parseInt(body.x), y = parseInt(body.y);
    if (isNaN(x) || isNaN(y)) return fail("x/y 必须为数字");
    try { click(x, y); return ok({ clicked: true, x: x, y: y }); }
    catch (e) { return fail("点击失败: " + e.message); }
}

function handleInput(body) {
    if (body.text == null) return fail("缺少参数: text");
    try { setText(String(body.text)); return ok({ inputted: true, text: String(body.text) }); }
    catch (e) { return fail("输入失败: " + e.message); }
}

function handleFindElement(body) {
    if (!body.by || !body.value) return fail("缺少参数: by, value");
    try {
        var sel = selector();
        switch (String(body.by)) {
            case "text": sel = sel.text(String(body.value)); break;
            case "id": sel = sel.id(String(body.value)); break;
            case "className": sel = sel.className(String(body.value)); break;
            case "desc": sel = sel.desc(String(body.value)); break;
            default: return fail("不支持的选择器: " + body.by);
        }
        var el = sel.findOne(3000);
        if (el) {
            var b = el.bounds();
            return ok({
                found: true,
                element: {
                    text: el.text() || "",
                    bounds: { left: b.left, top: b.top, right: b.right, bottom: b.bottom },
                    className: el.className() || "",
                    clickable: !!el.clickable()
                }
            });
        }
        return ok({ found: false, element: null });
    } catch (e) { return fail("查找失败: " + e.message); }
}

function handleOcr() {
    try {
        var img = images.captureScreen();
        if (!img) return fail("截图失败");
        var results;
        if (typeof paddle !== "undefined") results = paddle.ocr(img);
        else if (typeof ocr !== "undefined") results = ocr.detect(img);
        else { img.recycle(); return fail("无 OCR 引擎"); }
        img.recycle();
        if (!results || results.length === 0) return ok({ texts: [], count: 0 });
        var texts = [];
        for (var i = 0; i < results.length; i++) {
            texts.push({
                text: results[i].text || "",
                confidence: results[i].confidence || 0,
                bounds: results[i].bounds || []
            });
        }
        return ok({ texts: texts, count: texts.length });
    } catch (e) { return fail("OCR 失败: " + e.message); }
}

function handleClipboard(body) {
    try {
        if (body.text != null) { setClip(String(body.text)); return ok({ action: "write", text: String(body.text) }); }
        return ok({ action: "read", text: getClip() || "" });
    } catch (e) { return fail("剪贴板失败: " + e.message); }
}

function handleRunScript(body) {
    if (!body.script) return fail("缺少参数: script");
    try {
        var result = eval(String(body.script));
        return ok({ executed: true, result: result !== undefined ? result : null });
    } catch (e) { return fail("脚本失败: " + e.message); }
}

// ============================================================
// 路由
// ============================================================

function route(path, body) {
    switch (path) {
        case "/health": return handleHealth();
        case "/click": return handleClick(body);
        case "/input": return handleInput(body);
        case "/find_element": return handleFindElement(body);
        case "/ocr": return handleOcr();
        case "/clipboard": return handleClipboard(body);
        case "/run_script": return handleRunScript(body);
        default: return fail("未知端点: " + path);
    }
}

// ============================================================
// Java ServerSocket HTTP 服务器
// ============================================================

var PORT = 9500;
var running = true;
var serverSocket = new java.net.ServerSocket(PORT);

console.log("[Server] HTTP 服务已启动，端口: " + PORT);
console.log("[Server] 端点: /health /click /input /find_element /ocr /clipboard /run_script");

function handleConnection(socket) {
    var reader = new java.io.BufferedReader(
        new java.io.InputStreamReader(socket.getInputStream(), "UTF-8")
    );

    // 读取请求行
    var requestLine = reader.readLine();
    if (!requestLine) return;

    var parts = String(requestLine).split(" ");
    var path = (parts[1] || "/").split("?")[0];

    // 读取 headers
    var contentLength = 0;
    var line;
    while ((line = reader.readLine()) !== null) {
        var lineStr = String(line);
        if (lineStr.length === 0) break;
        if (lineStr.toLowerCase().indexOf("content-length:") === 0) {
            contentLength = parseInt(lineStr.substring(15).trim()) || 0;
        }
    }

    // 读取 body
    var body = {};
    if (contentLength > 0) {
        var buf = java.lang.reflect.Array.newInstance(java.lang.Character.TYPE, contentLength);
        var totalRead = 0;
        while (totalRead < contentLength) {
            var n = reader.read(buf, totalRead, contentLength - totalRead);
            if (n === -1) break;
            totalRead += n;
        }
        var bodyStr = new java.lang.String(buf, 0, totalRead);
        try { body = JSON.parse(String(bodyStr)); } catch (e) { body = {}; }
    }

    // 处理请求
    var responseBody;
    try {
        responseBody = route(path, body);
    } catch (e) {
        responseBody = fail("内部错误: " + e.message);
    }

    // 发送 HTTP 响应
    var responseBytes = new java.lang.String(responseBody).getBytes("UTF-8");
    var output = socket.getOutputStream();
    var writer = new java.io.BufferedWriter(
        new java.io.OutputStreamWriter(output, "UTF-8")
    );

    writer.write("HTTP/1.1 200 OK\r\n");
    writer.write("Content-Type: application/json; charset=utf-8\r\n");
    writer.write("Content-Length: " + responseBytes.length + "\r\n");
    writer.write("Connection: close\r\n");
    writer.write("\r\n");
    writer.flush();
    output.write(responseBytes);
    output.flush();
}

// 主循环：接受连接并处理请求
threads.start(function () {
    while (running) {
        try {
            var socket = serverSocket.accept();
            threads.start(function () {
                var s = socket;
                try {
                    handleConnection(s);
                } catch (e) {
                    console.error("[Server] 处理请求出错: " + e);
                } finally {
                    try { s.close(); } catch (e2) {}
                }
            });
        } catch (e) {
            if (running) console.error("[Server] accept 出错: " + e);
        }
    }
});

// 保持脚本运行
setInterval(function () {}, 30000);

// 脚本退出时关闭服务器
events.on("exit", function () {
    running = false;
    try { serverSocket.close(); } catch (e) {}
    console.log("[Server] 已停止");
});
