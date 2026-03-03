/**
 * U2 服务 HTTP 代理
 *
 * 封装对 Python FastAPI U2_Service (localhost:9400) 的 HTTP 调用。
 * 当 U2_Service 不可用时，返回明确的不可用标识，允许调用方回退到 ADB 直连。
 */

// ============================================================
// 常量
// ============================================================

/** U2_Service 默认基础 URL */
export const U2_BASE_URL = "http://localhost:9400";

/** 默认请求超时（毫秒） */
const DEFAULT_TIMEOUT_MS = 30_000;

// ============================================================
// 类型定义
// ============================================================

/** U2_Service 标准响应格式 */
export interface U2Response {
  success: boolean;
  message: string;
  data?: unknown;
}

// ============================================================
// 核心函数
// ============================================================

/**
 * 向 U2_Service 发送 HTTP 请求。
 *
 * - GET：当 body 为 undefined 时使用 GET 方法
 * - POST：当 body 有值时使用 POST 方法
 * - 超时：默认 30 秒，通过 AbortController 实现
 * - 连接失败：返回 `{ success: false, message: "U2 service unavailable: ..." }`
 *
 * @param path   请求路径，如 "/health" 或 "/device/abc/click"
 * @param body   POST 请求体（可选，传入则使用 POST）
 * @param baseUrl 可选，覆盖默认 U2_BASE_URL
 * @returns      U2Response
 */
export async function callU2(
  path: string,
  body?: unknown,
  baseUrl: string = U2_BASE_URL,
): Promise<U2Response> {
  const url = `${baseUrl.replace(/\/+$/, "")}${path}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  try {
    const isPost = body !== undefined;
    const response = await fetch(url, {
      method: isPost ? "POST" : "GET",
      headers: isPost ? { "Content-Type": "application/json" } : undefined,
      body: isPost ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    const json = (await response.json()) as U2Response;
    return json;
  } catch (err: unknown) {
    // 超时
    if (err instanceof DOMException && err.name === "AbortError") {
      return {
        success: false,
        message: `U2 service request timeout (${DEFAULT_TIMEOUT_MS}ms): ${path}`,
      };
    }
    // 连接被拒绝或其他网络错误 — U2_Service 未运行
    const reason = err instanceof Error ? err.message : String(err);
    return {
      success: false,
      message: `U2 service unavailable: ${reason}`,
    };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * 检查 U2_Service 是否可用。
 *
 * 调用 /health 端点，返回 true 表示服务正常运行。
 *
 * @param baseUrl 可选，覆盖默认 U2_BASE_URL
 */
export async function checkU2Health(
  baseUrl: string = U2_BASE_URL,
): Promise<boolean> {
  const result = await callU2("/health", undefined, baseUrl);
  return result.success;
}
