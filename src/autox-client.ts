/**
 * AutoX.js HTTP 客户端 v2
 *
 * 通过 frp 隧道映射端口调用手机端 AutoX.js HTTP 服务。
 * 默认连接 localhost:9501（frp 映射端口）。
 * 
 * 与 autox-server-v2.js 完全对齐。
 */

// ============================================================
// 类型定义
// ============================================================

export interface AutoXSelector {
  by: "text" | "textContains" | "id" | "className" | "desc" | "descContains";
  value: string;
}

export interface AutoXElement {
  text: string;
  desc: string;
  className: string;
  id: string;
  clickable: boolean;
  scrollable: boolean;
  enabled: boolean;
  bounds: { left: number; top: number; right: number; bottom: number };
  centerX: number;
  centerY: number;
}

export interface AutoXResult<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface OcrText {
  text: string;
  confidence: number;
  bounds: number[];
}

export interface DeviceInfo {
  brand: string;
  model: string;
  product: string;
  sdkInt: number;
  release: string;
  width: number;
  height: number;
  serial: string;
  imei: string;
}

export interface AppInfo {
  package: string;
  activity: string;
}

export interface UiTreeNode {
  text?: string;
  desc?: string;
  className: string;
  id?: string;
  clickable?: boolean;
  scrollable?: boolean;
  bounds: { l: number; t: number; r: number; b: number };
  children?: UiTreeNode[];
}

// ============================================================
// AutoXClient 实现
// ============================================================

export class AutoXClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  constructor(baseUrl = "http://localhost:9501", timeoutMs = 10000) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.timeoutMs = timeoutMs;
  }

  /**
   * 发送 POST 请求到 AutoX 服务端
   */
  private async post<T = unknown>(endpoint: string, body?: unknown): Promise<AutoXResult<T>> {
    const url = `${this.baseUrl}${endpoint}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body !== undefined ? JSON.stringify(body) : "{}",
        signal: controller.signal,
      });

      const json = (await response.json()) as AutoXResult<T>;
      return json;
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return {
          success: false,
          error: `AutoX request timeout (${this.timeoutMs}ms): ${endpoint}`,
        };
      }
      return {
        success: false,
        error: `AutoX service unavailable: ${String(err instanceof Error ? err.message : err)}`,
      };
    } finally {
      clearTimeout(timer);
    }
  }

  // ------------------------------------------------------------------
  // 健康检查
  // ------------------------------------------------------------------

  async healthCheck(): Promise<boolean> {
    const result = await this.post<{ status: string }>("/health");
    return result.success && result.data?.status === "running";
  }

  async getHealth(): Promise<AutoXResult<{ version: string; status: string; port: number; screenCapture: boolean; ts: string }>> {
    return this.post("/health");
  }

  // ------------------------------------------------------------------
  // 设备信息
  // ------------------------------------------------------------------

  async getDeviceInfo(): Promise<AutoXResult<DeviceInfo>> {
    return this.post("/device_info");
  }

  // ------------------------------------------------------------------
  // 截图
  // ------------------------------------------------------------------

  async screenshot(): Promise<AutoXResult<{ base64: string; format: string; length: number }>> {
    return this.post("/screenshot");
  }

  async screenshotBase64(): Promise<string> {
    const result = await this.screenshot();
    return result.data?.base64 ?? "";
  }

  // ------------------------------------------------------------------
  // 触摸操作
  // ------------------------------------------------------------------

  async click(x: number, y: number): Promise<AutoXResult> {
    return this.post("/click", { x, y });
  }

  async longClick(x: number, y: number, duration = 500): Promise<AutoXResult> {
    return this.post("/long_click", { x, y, duration });
  }

  async swipe(x1: number, y1: number, x2: number, y2: number, duration = 500): Promise<AutoXResult> {
    return this.post("/swipe", { x1, y1, x2, y2, duration });
  }

  async scroll(direction: "up" | "down" = "down"): Promise<AutoXResult> {
    return this.post("/scroll", { direction });
  }

  // ------------------------------------------------------------------
  // 文本输入
  // ------------------------------------------------------------------

  async inputText(text: string): Promise<AutoXResult> {
    return this.post("/input", { text });
  }

  // ------------------------------------------------------------------
  // 按键
  // ------------------------------------------------------------------

  async pressKey(key: "back" | "home" | "recents" | "power"): Promise<AutoXResult> {
    return this.post("/key", { key });
  }

  async pressBack(): Promise<AutoXResult> {
    return this.pressKey("back");
  }

  async pressHome(): Promise<AutoXResult> {
    return this.pressKey("home");
  }

  async pressRecents(): Promise<AutoXResult> {
    return this.pressKey("recents");
  }

  // ------------------------------------------------------------------
  // App 管理
  // ------------------------------------------------------------------

  async appStart(packageName: string): Promise<AutoXResult> {
    return this.post("/app/start", { package: packageName });
  }

  async appStop(packageName: string): Promise<AutoXResult> {
    return this.post("/app/stop", { package: packageName });
  }

  async appCurrent(): Promise<AutoXResult<AppInfo>> {
    return this.post("/app/current");
  }

  // ------------------------------------------------------------------
  // 元素操作
  // ------------------------------------------------------------------

  async findElement(selector: AutoXSelector, timeout = 3000): Promise<AutoXElement | null> {
    const result = await this.post<{ found: boolean; element: AutoXElement | null }>("/find_element", {
      by: selector.by,
      value: selector.value,
      timeout,
    });
    if (result.success && result.data?.found) {
      return result.data.element;
    }
    return null;
  }

  async findElements(selector: AutoXSelector): Promise<AutoXElement[]> {
    const result = await this.post<{ count: number; elements: AutoXElement[] }>("/find_elements", {
      by: selector.by,
      value: selector.value,
    });
    return result.data?.elements ?? [];
  }

  async clickElement(selector: AutoXSelector, timeout = 3000): Promise<boolean> {
    const result = await this.post<{ clicked: boolean }>("/click_element", {
      by: selector.by,
      value: selector.value,
      timeout,
    });
    return result.data?.clicked ?? false;
  }

  async waitElement(selector: AutoXSelector, timeout = 10000): Promise<AutoXElement | null> {
    const result = await this.post<{ found: boolean; element: AutoXElement | null }>("/wait_element", {
      by: selector.by,
      value: selector.value,
      timeout,
    });
    if (result.success && result.data?.found) {
      return result.data.element;
    }
    return null;
  }

  // ------------------------------------------------------------------
  // UI 树
  // ------------------------------------------------------------------

  async uiTree(maxDepth = 3): Promise<AutoXResult<UiTreeNode>> {
    return this.post("/ui_tree", { maxDepth });
  }

  // ------------------------------------------------------------------
  // OCR
  // ------------------------------------------------------------------

  async ocr(): Promise<OcrText[]> {
    const result = await this.post<{ texts: OcrText[]; count: number }>("/ocr");
    return result.data?.texts ?? [];
  }

  // ------------------------------------------------------------------
  // 剪贴板
  // ------------------------------------------------------------------

  async getClipboard(): Promise<string> {
    const result = await this.post<{ action: string; text: string }>("/clipboard", {});
    return result.data?.text ?? "";
  }

  async setClipboard(text: string): Promise<AutoXResult> {
    return this.post("/clipboard", { text });
  }

  // ------------------------------------------------------------------
  // 自定义脚本
  // ------------------------------------------------------------------

  async runScript(script: string): Promise<AutoXResult<unknown>> {
    return this.post("/run_script", { script });
  }
}
