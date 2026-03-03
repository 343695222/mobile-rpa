/**
 * AutoX/AutoJs6 手机端 HTTP 服务 v2.1
 * 
 * 完整的手机操作层，替代 ADB + uiautomator2。
 * 所有操作在手机本地执行，零网络延迟。
 * 
 * 端口: 9500
 */

"auto";

auto.waitFor();
console.log("[v2.1] 无障碍服务已启用");

var hasScreenCapture = false;
try {
    if (typeof $images !== "undefined") {
        $images.requestScreenCapture();
    } else {
        images.requestScreenCapture();
    }
    hasScreenCapture = true;
    console.log("[v2.1] 截图权限已获取");
} catch (e) {
    console.warn("[v2.1] 截图权限申请失败: " + e.message);
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
        version: "2.1",
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
