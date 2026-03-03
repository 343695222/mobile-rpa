/**
 * AutoX.js 手机端 HTTP 服务脚本（ServerSocket 版本）
 * 
 * 在 AutoX.js App 中运行，提供 HTTP API 供云服务器远程调用。
 * 端口：9500
 * 
 * 使用 Java ServerSocket 实现 HTTP 服务器（AutoX.js 不支持 http.createServer）
 */

"auto";

// ============================================================
// 初始化
// ============================================================

auto.waitFor();
console.log("[AutoX Server] 无障碍服务已启用");

try {
    if (typeof $images !== "undefined") {
        $images.requestScreenCapture();
    } else {
        images.requestScreenCapture();
    }
    console.log("[AutoX Server] 截图权限已获取");
} catch (e) {
    console.warn("[AutoX Server] 截图权限申请失败: " + e.message);
}

// ============================================================
// 工具函数
// ============================================================

function successResponse(data) {
    return JSON.stringify({ success: true, data: data || null });
}

function errorResponse(error) {
    return JSON.stringify({ success: false, error: String(error) });
}

/**
 * 解析 HTTP 请求体
 */
function parseRequestBody(inputStream) {
    try {
        var reader = new java.io.BufferedReader(new java.io.InputStreamReader(inputStream, "UTF-8"));
        var requestLine = reader.readLine();
        if (!requestLine) return { method: "", path: "/", body: {} };

        var parts = requestLine.split(" ");
        var method = parts[0] || "GET";
        var path = parts[1] || "/";

        // 读取 headers
        var contentLength = 0;
        var line;
        while ((line = reader.readLine()) !== null && line.length() > 0) {
            if (line.toLowerCase().startsWith("content-length:")) {
                contentLength = parseInt(line.substring(15).trim());
            }
        }

        // 读取 body
        var body = {};
        if (contentLength > 0) {
            var chars = java.lang.reflect.Array.newInstance(java.lang.Character.TYPE, contentLength);
            reader.read(chars, 0, contentLength);
            var bodyStr = new java.lang.String(chars);
            try {
                body = JSON.parse(String(bodyStr));
            } catch (e) {
                body = {};
            }
        }

        return { method: method, path: path, body: body };
    } catch (e) {
        return { method: "", path: "/", body: {} };
    }
}

// ============================================================
// 端点处理
// ============================================================

function handleHealth() {
    return successResponse({
        status: "running",
        service: "autox-server",
        port: 9500,
        timestamp: new Date().toISOString()
    });
}

function handleClick(body) {
    if (body.x === undefined || body.y === undefined) {
        return errorResponse("缺少必要参数: x, y");
    }
    var x = parseInt(body.x);
    var y = parseInt(body.y);
    if (isNaN(x) || isNaN(y)) {
        return errorResponse("参数类型错误: x 和 y 必须为数字");
    }
    try {
        var result = click(x, y);
        return successResponse({ clicked: true, x: x, y: y, result: result });
    } catch (e) {
        return errorResponse("点击操作失败: " + e.message);
    }
}

function handleInput(body) {
    if (body.text === undefined || body.text === null) {
        return errorResponse("缺少必要参数: text");
    }
    try {
        setText(String(body.text));
        return successResponse({ inputted: true, text: String(body.text) });
    } catch (e) {
        return errorResponse("文本输入失败: " + e.message);
    }
}

function handleFindElement(body) {
    if (!body.by || !body.value) {
        return errorResponse("缺少必要参数: by, value");
    }
    var by = String(body.by);
    var value = String(body.value);
    var supported = ["text", "id", "className", "desc"];
    if (supported.indexOf(by) === -1) {
        return errorResponse("不支持的选择器: " + by);
    }
    try {
        var sel = selector();
        switch (by) {
            case "text": sel = sel.text(value); break;
            case "id": sel = sel.id(value); break;
            case "className": sel = sel.className(value); break;
            case "desc": sel = sel.desc(value); break;
        }
        var element = sel.findOne(3000);
        if (element) {
            var bounds = element.bounds();
            return successResponse({
                found: true,
                element: {
                    text: element.text() || "",
                    bounds: { left: bounds.left, top: bounds.top, right: bounds.right, bottom: bounds.bottom },
                    className: element.className() || "",
                    clickable: element.clickable() || false
                }
            });
        }
        return successResponse({ found: false, element: null });
    } catch (e) {
        return errorResponse("元素查找失败: " + e.message);
    }
}

function handleOcr() {
    try {
        var img;
        if (typeof $images !== "undefined") {
            img = $images.captureScreen();
        } else {
            img = images.captureScreen();
        }
        if (!img) return errorResponse("截图失败");

        var results;
        if (typeof paddle !== "undefined") {
            results = paddle.ocr(img);
        } else if (typeof ocr !== "undefined") {
            results = ocr.detect(img);
        } else {
            img.recycle();
            return errorResponse("OCR 引擎不可用");
        }
        img.recycle();

        if (!results || results.length === 0) {
            return successResponse({ texts: [], count: 0 });
        }
        var texts = [];
        for (var i = 0; i < results.length; i++) {
            texts.push({
                text: results[i].text || "",
                confidence: results[i].confidence || 0,
                bounds: results[i].bounds || []
            });
        }
        return successResponse({ texts: texts, count: texts.length });
    } catch (e) {
        return errorResponse("OCR 失败: " + e.message);
    }
}

function handleClipboard(body) {
    try {
        if (body.text !== undefined && body.text !== null) {
            setClip(String(body.text));
            return successResponse({ action: "write", text: String(body.text) });
        }
        return successResponse({ action: "read", text: getClip() || "" });
    } catch (e) {
        return errorResponse("剪贴板操作失败: " + e.message);
    }
}

function handleRunScript(body) {
    if (!body.script) return errorResponse("缺少必要参数: script");
    try {
        var result = eval(String(body.script));
        return successResponse({ executed: true, result: result !== undefined ? result : null });
    } catch (e) {
        return errorResponse("脚本执行失败: " + e.message);
    }
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
        default: return errorResponse("未知端点: " + path);
    }
}

// ============================================================
// Java ServerSocket HTTP 服务器
// ============================================================

var PORT = 9500;
var running = true;
var serverSocket = new java.net.ServerSocket(PORT);

console.log("[AutoX Server] HTTP 服务已启动，端口: " + PORT);
console.log("[AutoX Server] 端点: /health /click /input /find_element /ocr /clipboard /run_script");

function handleConnection(socket) {
    var reader = new java.io.BufferedReader(
        new java.io.InputStreamReader(socket.getInputStream(), "UTF-8")
    );

    var requestLine = reader.readLine();
    if (!requestLine) return;

    var parts = String(requestLine).split(" ");
    var path = (parts[1] || "/").split("?")[0];

    var contentLength = 0;
    var line;
    while ((line = reader.readLine()) !== null) {
        var lineStr = String(line);
        if (lineStr.length === 0) break;
        if (lineStr.toLowerCase().indexOf("content-length:") === 0) {
            contentLength = parseInt(lineStr.substring(15).trim()) || 0;
        }
    }

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

    var responseBody;
    try {
        responseBody = route(path, body);
    } catch (e) {
        responseBody = errorResponse("内部错误: " + e.message);
    }

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

threads.start(function () {
    while (running) {
        try {
            var socket = serverSocket.accept();
            threads.start(function () {
                var s = socket;
                try {
                    handleConnection(s);
                } catch (e) {
                    console.error("[AutoX Server] 处理请求出错: " + e);
                } finally {
                    try { s.close(); } catch (e2) {}
                }
            });
        } catch (e) {
            if (running) console.error("[AutoX Server] accept 出错: " + e);
        }
    }
});

setInterval(function () {}, 30000);

events.on("exit", function () {
    running = false;
    try { serverSocket.close(); } catch (e) {}
    console.log("[AutoX Server] 已停止");
});
