/**
 * AutoX/AutoJs6 手机端 HTTP 服务 v2
 * 
 * 完整的手机操作层，替代 ADB + uiautomator2。
 * 所有操作在手机本地执行，零网络延迟。
 * 
 * 端口: 9500
 * 
 * 新增能力（相比 v1）:
 * - /screenshot    截图返回 base64
 * - /swipe         滑动手势
 * - /long_click    长按
 * - /key           按键（返回、Home、最近任务）
 * - /app/start     启动 App
 * - /app/stop      停止 App
 * - /app/current   当前前台 App
 * - /ui_tree       获取 UI 树（无障碍节点）
 * - /device_info   设备信息
 * - /scroll        上下滚动
 * - /wait_element  等待元素出现
 * - /click_element 查找并点击元素
 */

"auto";

auto.waitFor();
console.log("[v2] 无障碍服务已启用");

var hasScreenCapture = false;
try {
    if (typeof $images !== "undefined") {
        $images.requestScreenCapture();
    } else {
        images.requestScreenCapture();
    }
    hasScreenCapture = true;
    console.log("[v2] 截图权限已获取");
} catch (e) {
    console.warn("[v2] 截图权限申请失败: " + e.message);
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

function requireParams(body, names) {
    for (var i = 0; i < names.length; i++) {
        if (body[names[i]] === undefined || body[names[i]] === null) {
            return "缺少参数: " + names[i];
        }
    }
    return null;
}

function buildSelector(by, value) {
    var sel = selector();
    switch (String(by)) {
        case "text": return sel.text(String(value));
        case "textContains": return sel.textContains(String(value));
        case "id": return sel.id(String(value));
        case "className": return sel.className(String(value));
        case "desc": return sel.desc(String(value));
        case "descContains": return sel.descContains(String(value));
        default: return null;
    }
}

function elementToJson(el) {
    if (!el) return null;
    var b = el.bounds();
    return {
        text: el.text() || "",
        desc: el.contentDescription || el.desc() || "",
        className: el.className() || "",
        id: el.id() || "",
        clickable: !!el.clickable(),
        scrollable: !!el.scrollable(),
        enabled: !!el.enabled(),
        bounds: { left: b.left, top: b.top, right: b.right, bottom: b.bottom },
        centerX: b.centerX(),
        centerY: b.centerY()
    };
}


// ============================================================
// 端点处理
// ============================================================

function handleHealth() {
    return ok({
        version: "2.0",
        status: "running",
        port: 9500,
        screenCapture: hasScreenCapture,
        ts: new Date().toISOString()
    });
}

// --- 基础操作 ---

function handleClick(body) {
    var err = requireParams(body, ["x", "y"]);
    if (err) return fail(err);
    var x = parseInt(body.x), y = parseInt(body.y);
    try { click(x, y); return ok({ x: x, y: y }); }
    catch (e) { return fail("点击失败: " + e.message); }
}

function handleLongClick(body) {
    var err = requireParams(body, ["x", "y"]);
    if (err) return fail(err);
    var x = parseInt(body.x), y = parseInt(body.y);
    var duration = parseInt(body.duration) || 500;
    try { press(x, y, duration); return ok({ x: x, y: y, duration: duration }); }
    catch (e) { return fail("长按失败: " + e.message); }
}

function handleSwipe(body) {
    var err = requireParams(body, ["x1", "y1", "x2", "y2"]);
    if (err) return fail(err);
    var x1 = parseInt(body.x1), y1 = parseInt(body.y1);
    var x2 = parseInt(body.x2), y2 = parseInt(body.y2);
    var duration = parseInt(body.duration) || 500;
    try { swipe(x1, y1, x2, y2, duration); return ok({ x1: x1, y1: y1, x2: x2, y2: y2, duration: duration }); }
    catch (e) { return fail("滑动失败: " + e.message); }
}

function handleScroll(body) {
    var direction = String(body.direction || "down");
    var w = device.width || 1080;
    var h = device.height || 2340;
    var cx = Math.floor(w / 2);
    try {
        if (direction === "up") {
            swipe(cx, Math.floor(h * 0.3), cx, Math.floor(h * 0.7), 500);
        } else {
            swipe(cx, Math.floor(h * 0.7), cx, Math.floor(h * 0.3), 500);
        }
        return ok({ direction: direction });
    } catch (e) { return fail("滚动失败: " + e.message); }
}

function handleInput(body) {
    var err = requireParams(body, ["text"]);
    if (err) return fail(err);
    try { setText(String(body.text)); return ok({ text: String(body.text) }); }
    catch (e) { return fail("输入失败: " + e.message); }
}

function handleKey(body) {
    var key = String(body.key || "back");
    try {
        switch (key) {
            case "back": back(); break;
            case "home": home(); break;
            case "recents": recents(); break;
            case "power": KeyCode("KEYCODE_POWER"); break;
            default: return fail("不支持的按键: " + key);
        }
        return ok({ key: key });
    } catch (e) { return fail("按键失败: " + e.message); }
}

// --- 截图 ---

function handleScreenshot() {
    if (!hasScreenCapture) return fail("截图权限未获取");
    try {
        var img;
        if (typeof $images !== "undefined") img = $images.captureScreen();
        else img = images.captureScreen();
        if (!img) return fail("截图失败");

        // 编码为 base64 PNG
        var baos = new java.io.ByteArrayOutputStream();
        img.getBitmap().compress(android.graphics.Bitmap.CompressFormat.JPEG, 70, baos);
        var bytes = baos.toByteArray();
        var b64 = android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP);
        img.recycle();
        baos.close();

        return ok({ base64: String(b64), format: "jpeg", length: b64.length() });
    } catch (e) { return fail("截图失败: " + e.message); }
}

// --- App 管理 ---

function handleAppStart(body) {
    var err = requireParams(body, ["package"]);
    if (err) return fail(err);
    try {
        app.launch(String(body.package));
        return ok({ package: String(body.package) });
    } catch (e) { return fail("启动失败: " + e.message); }
}

function handleAppStop(body) {
    var err = requireParams(body, ["package"]);
    if (err) return fail(err);
    try {
        // 通过 shell 强制停止
        var pkg = String(body.package);
        shell("am force-stop " + pkg, true);
        return ok({ package: pkg });
    } catch (e) { return fail("停止失败: " + e.message); }
}

function handleAppCurrent() {
    try {
        var pkg = currentPackage();
        var act = currentActivity();
        return ok({ package: pkg || "", activity: act || "" });
    } catch (e) { return fail("获取当前App失败: " + e.message); }
}

// --- 元素操作 ---

function handleFindElement(body) {
    var err = requireParams(body, ["by", "value"]);
    if (err) return fail(err);
    try {
        var sel = buildSelector(body.by, body.value);
        if (!sel) return fail("不支持的选择器: " + body.by);
        var timeout = parseInt(body.timeout) || 3000;
        var el = sel.findOne(timeout);
        if (el) return ok({ found: true, element: elementToJson(el) });
        return ok({ found: false, element: null });
    } catch (e) { return fail("查找失败: " + e.message); }
}

function handleClickElement(body) {
    var err = requireParams(body, ["by", "value"]);
    if (err) return fail(err);
    try {
        var sel = buildSelector(body.by, body.value);
        if (!sel) return fail("不支持的选择器: " + body.by);
        var timeout = parseInt(body.timeout) || 3000;
        var el = sel.findOne(timeout);
        if (!el) return ok({ clicked: false, reason: "元素未找到" });
        var b = el.bounds();
        click(b.centerX(), b.centerY());
        return ok({ clicked: true, element: elementToJson(el) });
    } catch (e) { return fail("点击元素失败: " + e.message); }
}

function handleWaitElement(body) {
    var err = requireParams(body, ["by", "value"]);
    if (err) return fail(err);
    try {
        var sel = buildSelector(body.by, body.value);
        if (!sel) return fail("不支持的选择器: " + body.by);
        var timeout = parseInt(body.timeout) || 10000;
        var el = sel.findOne(timeout);
        if (el) return ok({ found: true, element: elementToJson(el) });
        return ok({ found: false, element: null });
    } catch (e) { return fail("等待失败: " + e.message); }
}

function handleFindElements(body) {
    var err = requireParams(body, ["by", "value"]);
    if (err) return fail(err);
    try {
        var sel = buildSelector(body.by, body.value);
        if (!sel) return fail("不支持的选择器: " + body.by);
        var els = sel.find();
        var results = [];
        for (var i = 0; i < els.length && i < 50; i++) {
            results.push(elementToJson(els[i]));
        }
        return ok({ count: results.length, elements: results });
    } catch (e) { return fail("查找失败: " + e.message); }
}


// --- UI 树 ---

function handleUiTree(body) {
    try {
        var maxDepth = parseInt(body.maxDepth) || 3;
        var root = auto.rootInActiveWindow;
        if (!root) return fail("无法获取 UI 树（无障碍服务可能未启用）");
        var tree = nodeToJson(root, 0, maxDepth);
        return ok(tree);
    } catch (e) { return fail("获取 UI 树失败: " + e.message); }
}

function nodeToJson(node, depth, maxDepth) {
    if (!node || depth > maxDepth) return null;
    var b = node.bounds();
    var result = {
        text: node.text() || "",
        desc: node.contentDescription || "",
        className: (node.className() || "").replace("android.widget.", ""),
        id: node.id() || "",
        clickable: !!node.clickable(),
        scrollable: !!node.scrollable(),
        bounds: { l: b.left, t: b.top, r: b.right, b: b.bottom }
    };
    // 只保留有意义的字段，减少传输量
    if (!result.text) delete result.text;
    if (!result.desc) delete result.desc;
    if (!result.id) delete result.id;
    if (!result.clickable) delete result.clickable;
    if (!result.scrollable) delete result.scrollable;

    var childCount = node.childCount();
    if (childCount > 0 && depth < maxDepth) {
        result.children = [];
        for (var i = 0; i < childCount; i++) {
            var child = nodeToJson(node.child(i), depth + 1, maxDepth);
            if (child) result.children.push(child);
        }
        if (result.children.length === 0) delete result.children;
    }
    return result;
}

// --- OCR ---

function handleOcr() {
    if (!hasScreenCapture) return fail("截图权限未获取");
    try {
        var img;
        if (typeof $images !== "undefined") img = $images.captureScreen();
        else img = images.captureScreen();
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

// --- 剪贴板 ---

function handleClipboard(body) {
    try {
        if (body.text !== undefined && body.text !== null) {
            setClip(String(body.text));
            return ok({ action: "write", text: String(body.text) });
        }
        return ok({ action: "read", text: getClip() || "" });
    } catch (e) { return fail("剪贴板失败: " + e.message); }
}

// --- 设备信息 ---

function handleDeviceInfo() {
    return ok({
        brand: device.brand || "",
        model: device.model || "",
        product: device.product || "",
        sdkInt: device.sdkInt || 0,
        release: device.release || "",
        width: device.width || 0,
        height: device.height || 0,
        serial: device.serial || "",
        imei: device.getIMEI ? device.getIMEI() : ""
    });
}

// --- 自定义脚本 ---

function handleRunScript(body) {
    var err = requireParams(body, ["script"]);
    if (err) return fail(err);
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
        // 基础
        case "/health":         return handleHealth();
        case "/device_info":    return handleDeviceInfo();
        // 操作
        case "/click":          return handleClick(body);
        case "/long_click":     return handleLongClick(body);
        case "/swipe":          return handleSwipe(body);
        case "/scroll":         return handleScroll(body);
        case "/input":          return handleInput(body);
        case "/key":            return handleKey(body);
        // 截图
        case "/screenshot":     return handleScreenshot();
        case "/ocr":            return handleOcr();
        // App
        case "/app/start":      return handleAppStart(body);
        case "/app/stop":       return handleAppStop(body);
        case "/app/current":    return handleAppCurrent();
        // 元素
        case "/find_element":   return handleFindElement(body);
        case "/find_elements":  return handleFindElements(body);
        case "/click_element":  return handleClickElement(body);
        case "/wait_element":   return handleWaitElement(body);
        // UI 树
        case "/ui_tree":        return handleUiTree(body);
        // 剪贴板
        case "/clipboard":      return handleClipboard(body);
        // 脚本
        case "/run_script":     return handleRunScript(body);
        default:                return fail("未知端点: " + path);
    }
}

// ============================================================
// HTTP 服务器
// ============================================================

var PORT = 9500;
var running = true;
var serverSocket = new java.net.ServerSocket(PORT);

console.log("[v2] HTTP 服务已启动，端口: " + PORT);
console.log("[v2] 端点: /health /click /long_click /swipe /scroll /input /key");
console.log("[v2]        /screenshot /ocr /app/start /app/stop /app/current");
console.log("[v2]        /find_element /find_elements /click_element /wait_element");
console.log("[v2]        /ui_tree /clipboard /device_info /run_script");

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
        responseBody = fail("内部错误: " + e.message);
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
                    console.error("[v2] 处理请求出错: " + e);
                } finally {
                    try { s.close(); } catch (e2) {}
                }
            });
        } catch (e) {
            if (running) console.error("[v2] accept 出错: " + e);
        }
    }
});

setInterval(function () {}, 30000);

events.on("exit", function () {
    running = false;
    try { serverSocket.close(); } catch (e) {}
    console.log("[v2] 已停止");
});
