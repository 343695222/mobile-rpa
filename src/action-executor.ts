import type { AdbClient } from "./adb-client";
import type { ScreenParser } from "./screen-parser";
import type { Action, ActionResult } from "./types";

/**
 * ActionExecutor 接口 - 将抽象操作指令转换为 ADB 命令并执行
 */
export interface ActionExecutor {
  execute(deviceId: string, action: Action): Promise<ActionResult>;
  executeBatch(deviceId: string, actions: Action[]): Promise<ActionResult[]>;
  validateConnection(deviceId: string): Promise<boolean>;
}

/** 默认操作超时时间（毫秒） */
const DEFAULT_TIMEOUT_MS = 30_000;

/**
 * 创建一个超时 Promise，在指定时间后 reject
 */
function timeoutPromise(ms: number, signal: AbortSignal): Promise<never> {
  return new Promise<never>((_, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`Operation timed out after ${ms}ms`));
    }, ms);

    signal.addEventListener("abort", () => {
      clearTimeout(timer);
    });
  });
}

/**
 * DefaultActionExecutor - ActionExecutor 的具体实现
 *
 * 通过构造函数注入 AdbClient 和可选的 ScreenParser（用于 tap_element 解析）。
 * 每次执行前验证设备连接状态，使用 Promise.race 实现超时控制。
 */
export class DefaultActionExecutor implements ActionExecutor {
  constructor(
    private readonly adbClient: AdbClient,
    private readonly screenParser?: ScreenParser,
    private readonly timeoutMs: number = DEFAULT_TIMEOUT_MS,
  ) {}

  async validateConnection(deviceId: string): Promise<boolean> {
    return this.adbClient.isConnected(deviceId);
  }

  async execute(deviceId: string, action: Action): Promise<ActionResult> {
    const startTime = Date.now();

    // 执行前连接验证 (Req 2.4)
    const connected = await this.validateConnection(deviceId);
    if (!connected) {
      return {
        success: false,
        action,
        error: `Device ${deviceId} is not connected`,
        durationMs: Date.now() - startTime,
      };
    }

    // 超时控制 (Req 4.7)
    const controller = new AbortController();
    const { signal } = controller;

    try {
      await Promise.race([
        this.executeAction(deviceId, action, signal),
        timeoutPromise(this.timeoutMs, signal),
      ]);

      return {
        success: true,
        action,
        durationMs: Date.now() - startTime,
      };
    } catch (err) {
      return {
        success: false,
        action,
        error: err instanceof Error ? err.message : String(err),
        durationMs: Date.now() - startTime,
      };
    } finally {
      controller.abort();
    }
  }

  async executeBatch(deviceId: string, actions: Action[]): Promise<ActionResult[]> {
    const results: ActionResult[] = [];

    for (const action of actions) {
      const result = await this.execute(deviceId, action);
      results.push(result);

      // 遇到失败立即停止 (Req 2.5 - 操作失败时停止)
      if (!result.success) {
        break;
      }
    }

    return results;
  }

  /**
   * 根据 Action 类型分发到对应的 ADB 命令
   */
  private async executeAction(
    deviceId: string,
    action: Action,
    signal: AbortSignal,
  ): Promise<void> {
    // 在每步执行前检查是否已被中止
    if (signal.aborted) {
      throw new Error("Operation aborted");
    }

    switch (action.type) {
      case "tap":
        await this.adbClient.tap(deviceId, action.x, action.y);
        break;

      case "tap_element":
        await this.executeTapElement(deviceId, action.elementId);
        break;

      case "input_text":
        await this.adbClient.inputText(deviceId, action.text);
        break;

      case "swipe":
        await this.adbClient.swipe(
          deviceId,
          action.x1,
          action.y1,
          action.x2,
          action.y2,
          action.duration,
        );
        break;

      case "key_event":
        await this.adbClient.keyEvent(deviceId, action.keyCode);
        break;

      case "wait":
        await this.executeWait(action.ms, signal);
        break;

      case "long_press":
        // Long press = swipe from same point to same point with duration
        await this.adbClient.swipe(deviceId, action.x, action.y, action.x, action.y, action.duration);
        break;

      case "open_app":
        await this.adbClient.shell(deviceId, `monkey -p ${action.packageName} -c android.intent.category.LAUNCHER 1`);
        break;

      case "go_back":
        await this.adbClient.keyEvent(deviceId, 4);
        break;

      case "go_home":
        await this.adbClient.keyEvent(deviceId, 3);
        break;

      case "scroll_up":
        // Scroll up: swipe from center-bottom to center-top
        await this.adbClient.swipe(deviceId, 540, 1600, 540, 600, 300);
        break;

      case "scroll_down":
        // Scroll down: swipe from center-top to center-bottom
        await this.adbClient.swipe(deviceId, 540, 600, 540, 1600, 300);
        break;

      case "wake_screen":
        await this.adbClient.keyEvent(deviceId, 224); // KEYCODE_WAKEUP
        break;

      case "lock_screen":
        await this.adbClient.keyEvent(deviceId, 223); // KEYCODE_SLEEP
        break;

      default: {
        const _exhaustive: never = action;
        throw new Error(`Unknown action type: ${(action as Action).type}`);
      }
    }
  }

  /**
   * tap_element: 通过 ScreenParser 解析元素坐标，然后点击元素中心
   */
  private async executeTapElement(deviceId: string, elementId: string): Promise<void> {
    if (!this.screenParser) {
      throw new Error("ScreenParser is required for tap_element actions");
    }

    const screenState = await this.screenParser.captureScreen(deviceId);
    const element = screenState.elements.find((e) => e.id === elementId);

    if (!element) {
      throw new Error(`Element not found: ${elementId}`);
    }

    if (!element.clickable) {
      throw new Error(`Element ${elementId} is not clickable`);
    }

    // 计算元素中心坐标
    const centerX = Math.round((element.bounds.left + element.bounds.right) / 2);
    const centerY = Math.round((element.bounds.top + element.bounds.bottom) / 2);

    await this.adbClient.tap(deviceId, centerX, centerY);
  }

  /**
   * wait: 暂停指定毫秒数，支持通过 AbortSignal 提前中止
   */
  private executeWait(ms: number, signal: AbortSignal): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const timer = setTimeout(resolve, ms);

      signal.addEventListener("abort", () => {
        clearTimeout(timer);
        reject(new Error("Wait aborted"));
      });
    });
  }
}
