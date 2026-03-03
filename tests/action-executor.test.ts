import { describe, test, expect, beforeEach } from "bun:test";
import type { AdbClient } from "../src/adb-client";
import type { ScreenParser } from "../src/screen-parser";
import type { Action, DeviceInfo, ScreenState, UiElement, ScreenDiff } from "../src/types";
import { DefaultActionExecutor } from "../src/action-executor";

// === Mock ADB Client ===

class MockAdbClient implements AdbClient {
  private connectedDevices = new Set<string>();
  public commandLog: string[] = [];
  public shouldFail = false;
  public failMessage = "ADB command failed";

  setConnected(deviceId: string, connected: boolean) {
    if (connected) {
      this.connectedDevices.add(deviceId);
    } else {
      this.connectedDevices.delete(deviceId);
    }
  }

  async listDevices(): Promise<DeviceInfo[]> {
    return Array.from(this.connectedDevices).map((id) => ({
      id,
      model: "MockDevice",
      status: "device" as const,
    }));
  }

  async isConnected(deviceId: string): Promise<boolean> {
    return this.connectedDevices.has(deviceId);
  }

  async dumpUiHierarchy(_deviceId: string): Promise<string> {
    return "<hierarchy></hierarchy>";
  }

  async tap(deviceId: string, x: number, y: number): Promise<void> {
    if (this.shouldFail) throw new Error(this.failMessage);
    this.commandLog.push(`tap:${deviceId}:${x},${y}`);
  }

  async inputText(deviceId: string, text: string): Promise<void> {
    if (this.shouldFail) throw new Error(this.failMessage);
    this.commandLog.push(`input_text:${deviceId}:${text}`);
  }

  async swipe(
    deviceId: string,
    x1: number, y1: number, x2: number, y2: number, durationMs: number,
  ): Promise<void> {
    if (this.shouldFail) throw new Error(this.failMessage);
    this.commandLog.push(`swipe:${deviceId}:${x1},${y1},${x2},${y2},${durationMs}`);
  }

  async keyEvent(deviceId: string, keyCode: number): Promise<void> {
    if (this.shouldFail) throw new Error(this.failMessage);
    this.commandLog.push(`key_event:${deviceId}:${keyCode}`);
  }

  async screenshot(_deviceId: string): Promise<string> {
    return "base64mockdata";
  }

  async shell(deviceId: string, command: string): Promise<string> {
    this.commandLog.push(`shell:${deviceId}:${command}`);
    return "";
  }
}

// === Mock Screen Parser ===

function makeMockElement(overrides: Partial<UiElement> = {}): UiElement {
  return {
    id: "elem_0",
    type: "Button",
    text: "OK",
    contentDesc: "",
    bounds: { left: 100, top: 200, right: 300, bottom: 400 },
    clickable: true,
    scrollable: false,
    focusable: true,
    enabled: true,
    resourceId: "com.app:id/btn_ok",
    className: "android.widget.Button",
    ...overrides,
  };
}

class MockScreenParser implements ScreenParser {
  public elements: UiElement[] = [makeMockElement()];

  async captureScreen(deviceId: string): Promise<ScreenState> {
    return {
      timestamp: Date.now(),
      deviceId,
      elements: this.elements,
      rawXml: "<hierarchy></hierarchy>",
    };
  }

  diffScreens(): ScreenDiff {
    return { added: [], removed: [], changed: [] };
  }

  parseAccessibilityTree(): UiElement[] {
    return this.elements;
  }
}

// === Tests ===

const DEVICE_ID = "emulator-5554";

describe("ActionExecutor - validateConnection", () => {
  test("returns true for connected device", async () => {
    const adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    const executor = new DefaultActionExecutor(adb);

    expect(await executor.validateConnection(DEVICE_ID)).toBe(true);
  });

  test("returns false for disconnected device", async () => {
    const adb = new MockAdbClient();
    const executor = new DefaultActionExecutor(adb);

    expect(await executor.validateConnection(DEVICE_ID)).toBe(false);
  });
});

describe("ActionExecutor - execute (connection validation)", () => {
  test("rejects execution when device is not connected (Req 2.4)", async () => {
    const adb = new MockAdbClient();
    const executor = new DefaultActionExecutor(adb);

    const result = await executor.execute(DEVICE_ID, { type: "tap", x: 100, y: 200 });

    expect(result.success).toBe(false);
    expect(result.error).toContain("not connected");
    expect(result.action.type).toBe("tap");
    expect(adb.commandLog).toHaveLength(0); // No ADB command should be sent
  });

  test("includes durationMs in result even on connection failure", async () => {
    const adb = new MockAdbClient();
    const executor = new DefaultActionExecutor(adb);

    const result = await executor.execute(DEVICE_ID, { type: "wait", ms: 10 });

    expect(result.durationMs).toBeGreaterThanOrEqual(0);
  });
});

describe("ActionExecutor - execute (tap)", () => {
  let adb: MockAdbClient;
  let executor: DefaultActionExecutor;

  beforeEach(() => {
    adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    executor = new DefaultActionExecutor(adb);
  });

  test("executes tap action with correct coordinates (Req 4.1)", async () => {
    const result = await executor.execute(DEVICE_ID, { type: "tap", x: 150, y: 300 });

    expect(result.success).toBe(true);
    expect(result.action).toEqual({ type: "tap", x: 150, y: 300 });
    expect(adb.commandLog).toContain(`tap:${DEVICE_ID}:150,300`);
    expect(result.durationMs).toBeGreaterThanOrEqual(0);
  });

  test("returns failure when ADB tap command fails", async () => {
    adb.shouldFail = true;
    adb.failMessage = "Device connection lost";

    const result = await executor.execute(DEVICE_ID, { type: "tap", x: 10, y: 20 });

    expect(result.success).toBe(false);
    expect(result.error).toBe("Device connection lost");
  });
});

describe("ActionExecutor - execute (input_text)", () => {
  let adb: MockAdbClient;
  let executor: DefaultActionExecutor;

  beforeEach(() => {
    adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    executor = new DefaultActionExecutor(adb);
  });

  test("executes input_text action (Req 4.2)", async () => {
    const result = await executor.execute(DEVICE_ID, { type: "input_text", text: "hello world" });

    expect(result.success).toBe(true);
    expect(adb.commandLog).toContain(`input_text:${DEVICE_ID}:hello world`);
  });
});

describe("ActionExecutor - execute (swipe)", () => {
  let adb: MockAdbClient;
  let executor: DefaultActionExecutor;

  beforeEach(() => {
    adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    executor = new DefaultActionExecutor(adb);
  });

  test("executes swipe action with all parameters (Req 4.3)", async () => {
    const action: Action = { type: "swipe", x1: 100, y1: 200, x2: 300, y2: 400, duration: 500 };
    const result = await executor.execute(DEVICE_ID, action);

    expect(result.success).toBe(true);
    expect(adb.commandLog).toContain(`swipe:${DEVICE_ID}:100,200,300,400,500`);
  });
});

describe("ActionExecutor - execute (key_event)", () => {
  let adb: MockAdbClient;
  let executor: DefaultActionExecutor;

  beforeEach(() => {
    adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    executor = new DefaultActionExecutor(adb);
  });

  test("executes key_event action (Req 4.4)", async () => {
    const result = await executor.execute(DEVICE_ID, { type: "key_event", keyCode: 4 }); // KEYCODE_BACK

    expect(result.success).toBe(true);
    expect(adb.commandLog).toContain(`key_event:${DEVICE_ID}:4`);
  });
});

describe("ActionExecutor - execute (wait)", () => {
  let adb: MockAdbClient;
  let executor: DefaultActionExecutor;

  beforeEach(() => {
    adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    executor = new DefaultActionExecutor(adb);
  });

  test("executes wait action for specified duration (Req 4.5)", async () => {
    const result = await executor.execute(DEVICE_ID, { type: "wait", ms: 50 });

    expect(result.success).toBe(true);
    expect(result.durationMs).toBeGreaterThanOrEqual(40); // Allow small timing variance
    expect(adb.commandLog).toHaveLength(0); // No ADB command for wait
  });
});

describe("ActionExecutor - execute (tap_element)", () => {
  test("resolves element coordinates and taps center", async () => {
    const adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    const screenParser = new MockScreenParser();
    screenParser.elements = [
      makeMockElement({ id: "elem_0", bounds: { left: 100, top: 200, right: 300, bottom: 400 } }),
    ];
    const executor = new DefaultActionExecutor(adb, screenParser);

    const result = await executor.execute(DEVICE_ID, { type: "tap_element", elementId: "elem_0" });

    expect(result.success).toBe(true);
    // Center of [100,200][300,400] = (200, 300)
    expect(adb.commandLog).toContain(`tap:${DEVICE_ID}:200,300`);
  });

  test("fails when element not found", async () => {
    const adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    const screenParser = new MockScreenParser();
    screenParser.elements = [];
    const executor = new DefaultActionExecutor(adb, screenParser);

    const result = await executor.execute(DEVICE_ID, { type: "tap_element", elementId: "elem_99" });

    expect(result.success).toBe(false);
    expect(result.error).toContain("Element not found");
  });

  test("fails when element is not clickable", async () => {
    const adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    const screenParser = new MockScreenParser();
    screenParser.elements = [makeMockElement({ id: "elem_0", clickable: false })];
    const executor = new DefaultActionExecutor(adb, screenParser);

    const result = await executor.execute(DEVICE_ID, { type: "tap_element", elementId: "elem_0" });

    expect(result.success).toBe(false);
    expect(result.error).toContain("not clickable");
  });

  test("fails when no ScreenParser is provided", async () => {
    const adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    const executor = new DefaultActionExecutor(adb); // No screenParser

    const result = await executor.execute(DEVICE_ID, { type: "tap_element", elementId: "elem_0" });

    expect(result.success).toBe(false);
    expect(result.error).toContain("ScreenParser is required");
  });
});

describe("ActionExecutor - execute (timeout)", () => {
  test("returns timeout error when operation exceeds timeout (Req 4.7)", async () => {
    const adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    // Set a very short timeout
    const executor = new DefaultActionExecutor(adb, undefined, 50);

    // wait action longer than timeout
    const result = await executor.execute(DEVICE_ID, { type: "wait", ms: 5000 });

    expect(result.success).toBe(false);
    expect(result.error).toContain("timed out");
  });
});

describe("ActionExecutor - execute (result format)", () => {
  test("ActionResult always contains success, action, and durationMs (Req 4.6)", async () => {
    const adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    const executor = new DefaultActionExecutor(adb);

    const action: Action = { type: "tap", x: 50, y: 60 };
    const result = await executor.execute(DEVICE_ID, action);

    expect(typeof result.success).toBe("boolean");
    expect(result.action).toEqual(action);
    expect(typeof result.durationMs).toBe("number");
  });
});

describe("ActionExecutor - executeBatch", () => {
  let adb: MockAdbClient;
  let executor: DefaultActionExecutor;

  beforeEach(() => {
    adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    executor = new DefaultActionExecutor(adb);
  });

  test("executes all actions sequentially on success", async () => {
    const actions: Action[] = [
      { type: "tap", x: 10, y: 20 },
      { type: "input_text", text: "test" },
      { type: "key_event", keyCode: 66 }, // KEYCODE_ENTER
    ];

    const results = await executor.executeBatch(DEVICE_ID, actions);

    expect(results).toHaveLength(3);
    expect(results.every((r) => r.success)).toBe(true);
    expect(adb.commandLog).toEqual([
      `tap:${DEVICE_ID}:10,20`,
      `input_text:${DEVICE_ID}:test`,
      `key_event:${DEVICE_ID}:66`,
    ]);
  });

  test("stops on first failure and returns partial results", async () => {
    const actions: Action[] = [
      { type: "tap", x: 10, y: 20 },
      { type: "tap", x: 30, y: 40 }, // This will fail
      { type: "tap", x: 50, y: 60 }, // Should not execute
    ];

    // Make the second tap fail
    let callCount = 0;
    const originalTap = adb.tap.bind(adb);
    adb.tap = async (deviceId: string, x: number, y: number) => {
      callCount++;
      if (callCount === 2) {
        throw new Error("Connection lost");
      }
      return originalTap(deviceId, x, y);
    };

    const results = await executor.executeBatch(DEVICE_ID, actions);

    expect(results).toHaveLength(2); // Only 2 results (stopped at failure)
    expect(results[0].success).toBe(true);
    expect(results[1].success).toBe(false);
    expect(results[1].error).toBe("Connection lost");
  });

  test("returns empty array for empty actions list", async () => {
    const results = await executor.executeBatch(DEVICE_ID, []);
    expect(results).toHaveLength(0);
  });

  test("stops immediately if device is not connected", async () => {
    adb.setConnected(DEVICE_ID, false);

    const actions: Action[] = [
      { type: "tap", x: 10, y: 20 },
      { type: "tap", x: 30, y: 40 },
    ];

    const results = await executor.executeBatch(DEVICE_ID, actions);

    expect(results).toHaveLength(1); // First action fails, stops
    expect(results[0].success).toBe(false);
    expect(results[0].error).toContain("not connected");
  });
});

// === New Action Types ===

describe("ActionExecutor - execute (long_press)", () => {
  test("executes long_press as swipe from same point", async () => {
    const adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    const executor = new DefaultActionExecutor(adb);

    const result = await executor.execute(DEVICE_ID, { type: "long_press", x: 200, y: 300, duration: 1000 });

    expect(result.success).toBe(true);
    expect(adb.commandLog).toContain(`swipe:${DEVICE_ID}:200,300,200,300,1000`);
  });
});

describe("ActionExecutor - execute (open_app)", () => {
  test("executes open_app via shell monkey command", async () => {
    const adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    const executor = new DefaultActionExecutor(adb);

    const result = await executor.execute(DEVICE_ID, { type: "open_app", packageName: "com.tencent.mm" });

    expect(result.success).toBe(true);
    expect(adb.commandLog).toContain(`shell:${DEVICE_ID}:monkey -p com.tencent.mm -c android.intent.category.LAUNCHER 1`);
  });
});

describe("ActionExecutor - execute (go_back)", () => {
  test("executes go_back as keyEvent 4", async () => {
    const adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    const executor = new DefaultActionExecutor(adb);

    const result = await executor.execute(DEVICE_ID, { type: "go_back" });

    expect(result.success).toBe(true);
    expect(adb.commandLog).toContain(`key_event:${DEVICE_ID}:4`);
  });
});

describe("ActionExecutor - execute (go_home)", () => {
  test("executes go_home as keyEvent 3", async () => {
    const adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    const executor = new DefaultActionExecutor(adb);

    const result = await executor.execute(DEVICE_ID, { type: "go_home" });

    expect(result.success).toBe(true);
    expect(adb.commandLog).toContain(`key_event:${DEVICE_ID}:3`);
  });
});

describe("ActionExecutor - execute (scroll_up)", () => {
  test("executes scroll_up as swipe from bottom to top", async () => {
    const adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    const executor = new DefaultActionExecutor(adb);

    const result = await executor.execute(DEVICE_ID, { type: "scroll_up" });

    expect(result.success).toBe(true);
    expect(adb.commandLog).toContain(`swipe:${DEVICE_ID}:540,1600,540,600,300`);
  });
});

describe("ActionExecutor - execute (scroll_down)", () => {
  test("executes scroll_down as swipe from top to bottom", async () => {
    const adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    const executor = new DefaultActionExecutor(adb);

    const result = await executor.execute(DEVICE_ID, { type: "scroll_down" });

    expect(result.success).toBe(true);
    expect(adb.commandLog).toContain(`swipe:${DEVICE_ID}:540,600,540,1600,300`);
  });
});

describe("ActionExecutor - execute (wake_screen)", () => {
  test("executes wake_screen as keyEvent 224", async () => {
    const adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    const executor = new DefaultActionExecutor(adb);

    const result = await executor.execute(DEVICE_ID, { type: "wake_screen" });

    expect(result.success).toBe(true);
    expect(adb.commandLog).toContain(`key_event:${DEVICE_ID}:224`);
  });
});

describe("ActionExecutor - execute (lock_screen)", () => {
  test("executes lock_screen as keyEvent 223", async () => {
    const adb = new MockAdbClient();
    adb.setConnected(DEVICE_ID, true);
    const executor = new DefaultActionExecutor(adb);

    const result = await executor.execute(DEVICE_ID, { type: "lock_screen" });

    expect(result.success).toBe(true);
    expect(adb.commandLog).toContain(`key_event:${DEVICE_ID}:223`);
  });
});
