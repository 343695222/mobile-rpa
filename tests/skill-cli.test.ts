import { describe, test, expect, beforeEach } from "bun:test";
import { DefaultSkillCli, parseInput } from "../src/skill-cli";
import type { AdbClient } from "../src/adb-client";
import type { ScreenParser } from "../src/screen-parser";
import type { ActionExecutor } from "../src/action-executor";
import type { TemplateEngine } from "../src/template-engine";
import type { RpaLoop } from "../src/rpa-loop";
import type { Logger } from "../src/logger";
import type {
  Action,
  ActionResult,
  DeviceInfo,
  ScreenState,
  ScreenDiff,
  UiElement,
  OperationTemplate,
  ResolvedTemplate,
  TemplateSummary,
  ValidationResult,
  ExecutionHistory,
  ExplorationResult,
  TemplateExecutionResult,
  StepRecord,
  SkillResponse,
  ParsedCommand,
} from "../src/types";

// === Mock Implementations ===

class MockAdbClient implements AdbClient {
  public devices: DeviceInfo[] = [];

  async listDevices(): Promise<DeviceInfo[]> {
    return this.devices;
  }
  async isConnected(_deviceId: string): Promise<boolean> {
    return true;
  }
  async dumpUiHierarchy(_deviceId: string): Promise<string> {
    return "<hierarchy></hierarchy>";
  }
  async screenshot(_deviceId: string): Promise<string> {
    return "base64mockdata";
  }
  async tap(_d: string, _x: number, _y: number): Promise<void> {}
  async inputText(_d: string, _t: string): Promise<void> {}
  async swipe(_d: string, _x1: number, _y1: number, _x2: number, _y2: number, _dur: number): Promise<void> {}
  async keyEvent(_d: string, _k: number): Promise<void> {}
  async shell(_d: string, _c: string): Promise<string> {
    return "";
  }
}

class MockScreenParser implements ScreenParser {
  async captureScreen(deviceId: string): Promise<ScreenState> {
    return {
      timestamp: Date.now(),
      deviceId,
      elements: [
        {
          id: "elem_0",
          type: "Button",
          text: "OK",
          contentDesc: "",
          bounds: { left: 0, top: 0, right: 100, bottom: 50 },
          clickable: true,
          scrollable: false,
          focusable: true,
          enabled: true,
          resourceId: "",
          className: "android.widget.Button",
        },
      ],
      rawXml: "<hierarchy></hierarchy>",
    };
  }
  diffScreens(_prev: ScreenState, _curr: ScreenState): ScreenDiff {
    return { added: [], removed: [], changed: [] };
  }
  parseAccessibilityTree(_xml: string): UiElement[] {
    return [];
  }
}

class MockActionExecutor implements ActionExecutor {
  async execute(deviceId: string, action: Action): Promise<ActionResult> {
    return { success: true, action, durationMs: 10 };
  }
  async executeBatch(deviceId: string, actions: Action[]): Promise<ActionResult[]> {
    return actions.map((a) => ({ success: true, action: a, durationMs: 10 }));
  }
  async validateConnection(_deviceId: string): Promise<boolean> {
    return true;
  }
}

class MockTemplateEngine implements TemplateEngine {
  public templates: Map<string, OperationTemplate> = new Map();

  async loadTemplates(_dir: string): Promise<OperationTemplate[]> {
    return Array.from(this.templates.values());
  }
  getTemplate(name: string): OperationTemplate | undefined {
    return this.templates.get(name);
  }
  listTemplates(): TemplateSummary[] {
    return Array.from(this.templates.values()).map((t) => ({
      name: t.name,
      description: t.description,
      params: t.params,
    }));
  }
  async saveTemplate(template: OperationTemplate, _dir: string): Promise<void> {
    this.templates.set(template.name, template);
  }
  validateTemplate(_template: unknown): ValidationResult {
    return { valid: true, errors: [] };
  }
  resolveParams(template: OperationTemplate, _params: Record<string, string>): ResolvedTemplate {
    return { name: template.name, steps: template.steps };
  }
  generateFromHistory(history: ExecutionHistory, taskName: string): OperationTemplate {
    return {
      name: taskName,
      description: "auto",
      params: [],
      steps: [],
      metadata: { createdAt: new Date().toISOString(), source: "auto-generated" },
    };
  }
  findMatchingTemplate(taskDescription: string): OperationTemplate | undefined {
    const words = taskDescription.toLowerCase().split(/\s+/);
    for (const t of this.templates.values()) {
      const searchText = `${t.name} ${t.description} ${t.metadata?.taskDescription ?? ""}`.toLowerCase();
      if (words.some((w) => searchText.includes(w))) {
        return t;
      }
    }
    return undefined;
  }
  serialize(template: OperationTemplate): string {
    return JSON.stringify(template);
  }
  deserialize(json: string): OperationTemplate {
    return JSON.parse(json);
  }
}

class MockRpaLoop implements RpaLoop {
  async runExploration(
    deviceId: string,
    goal: string,
  ): Promise<ExplorationResult> {
    return {
      success: true,
      history: { taskGoal: goal, steps: [], startTime: Date.now(), endTime: Date.now() },
      message: "Exploration completed",
    };
  }
  async runTemplate(
    _deviceId: string,
    template: ResolvedTemplate,
  ): Promise<TemplateExecutionResult> {
    return {
      success: true,
      stepsCompleted: template.steps.length,
      totalSteps: template.steps.length,
      stepResults: [],
      message: `All ${template.steps.length} steps completed successfully`,
    };
  }
  detectStuck(_history: StepRecord[]): boolean {
    return false;
  }
}

class MockLogger implements Logger {
  public logs: Array<{ command: string; result: string }> = [];
  async log(command: string, result: string): Promise<void> {
    this.logs.push({ command, result });
  }
}

// === Helpers ===

function createCli() {
  const adbClient = new MockAdbClient();
  const screenParser = new MockScreenParser();
  const actionExecutor = new MockActionExecutor();
  const templateEngine = new MockTemplateEngine();
  const rpaLoop = new MockRpaLoop();
  const logger = new MockLogger();

  const cli = new DefaultSkillCli(
    adbClient,
    screenParser,
    actionExecutor,
    templateEngine,
    rpaLoop,
    logger,
  );

  return { cli, adbClient, screenParser, actionExecutor, templateEngine, rpaLoop, logger };
}

// === parseInput Tests ===

describe("parseInput", () => {
  test("parses valid list_devices command", () => {
    const cmd = parseInput('{"type": "list_devices"}');
    expect(cmd.type).toBe("list_devices");
  });

  test("parses valid get_screen command with deviceId", () => {
    const cmd = parseInput('{"type": "get_screen", "deviceId": "emulator-5554"}');
    expect(cmd.type).toBe("get_screen");
    expect(cmd.deviceId).toBe("emulator-5554");
  });

  test("parses valid execute_action command", () => {
    const cmd = parseInput('{"type": "execute_action", "deviceId": "dev1", "action": {"type": "tap", "x": 100, "y": 200}}');
    expect(cmd.type).toBe("execute_action");
    expect(cmd.action).toEqual({ type: "tap", x: 100, y: 200 });
  });

  test("parses valid run_template command", () => {
    const cmd = parseInput('{"type": "run_template", "deviceId": "dev1", "templateName": "open-app", "templateParams": {"app": "Settings"}}');
    expect(cmd.type).toBe("run_template");
    expect(cmd.templateName).toBe("open-app");
    expect(cmd.templateParams).toEqual({ app: "Settings" });
  });

  test("parses valid run_task command", () => {
    const cmd = parseInput('{"type": "run_task", "deviceId": "dev1", "taskGoal": "Open settings"}');
    expect(cmd.type).toBe("run_task");
    expect(cmd.taskGoal).toBe("Open settings");
  });

  test("parses valid list_templates command", () => {
    const cmd = parseInput('{"type": "list_templates"}');
    expect(cmd.type).toBe("list_templates");
  });

  test("throws on invalid JSON", () => {
    expect(() => parseInput("not json")).toThrow();
  });

  test("throws on non-object input", () => {
    expect(() => parseInput('"just a string"')).toThrow("Input must be a JSON object");
  });

  test("throws on array input", () => {
    expect(() => parseInput("[]")).toThrow("Input must be a JSON object");
  });

  test("throws on unknown command type with supported list", () => {
    expect(() => parseInput('{"type": "unknown_cmd"}')).toThrow("Unknown command type");
    expect(() => parseInput('{"type": "unknown_cmd"}')).toThrow("Supported commands:");
  });

  test("throws on missing type field", () => {
    expect(() => parseInput('{"deviceId": "dev1"}')).toThrow("Unknown command type");
  });
});

// === handleCommand Tests ===

describe("SkillCli - handleCommand", () => {
  test("returns error for invalid JSON input (Req 7.3)", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand("not valid json");
    expect(response.status).toBe("error");
    expect(response.message).toBeTruthy();
  });

  test("returns error for unknown command type (Req 7.3)", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "bad_command"}');
    expect(response.status).toBe("error");
    expect(response.message).toContain("Unknown command type");
    expect(response.message).toContain("list_devices");
    expect(response.message).toContain("get_screen");
    expect(response.message).toContain("execute_action");
    expect(response.message).toContain("run_template");
    expect(response.message).toContain("run_task");
    expect(response.message).toContain("list_templates");
  });

  test("logs every command execution (Req 7.5)", async () => {
    const { cli, logger } = createCli();
    await cli.handleCommand('{"type": "list_devices"}');
    expect(logger.logs.length).toBe(1);
    expect(logger.logs[0].result).toContain("success");
  });

  test("logs failed commands too (Req 7.5)", async () => {
    const { cli, logger } = createCli();
    await cli.handleCommand("bad json");
    expect(logger.logs.length).toBe(1);
    expect(logger.logs[0].result).toContain("error");
  });

  test("response always has status and message fields (Req 7.2)", async () => {
    const { cli } = createCli();

    const r1 = await cli.handleCommand('{"type": "list_devices"}');
    expect(r1.status).toBeDefined();
    expect(r1.message).toBeDefined();
    expect(typeof r1.message).toBe("string");

    const r2 = await cli.handleCommand("bad");
    expect(r2.status).toBeDefined();
    expect(r2.message).toBeDefined();
    expect(typeof r2.message).toBe("string");
  });
});

// === routeCommand - list_devices ===

describe("SkillCli - list_devices", () => {
  test("returns device list (Req 7.1)", async () => {
    const { cli, adbClient } = createCli();
    adbClient.devices = [
      { id: "emulator-5554", model: "Pixel_4", status: "device" },
      { id: "192.168.1.100:5555", model: "unknown", status: "offline" },
    ];

    const response = await cli.handleCommand('{"type": "list_devices"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("2");
    expect(response.data).toEqual(adbClient.devices);
  });

  test("returns empty list when no devices", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "list_devices"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("0");
    expect(response.data).toEqual([]);
  });
});

// === routeCommand - get_screen ===

describe("SkillCli - get_screen", () => {
  test("returns screen state with elements (Req 7.1)", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "get_screen", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("1 UI element");
    expect(response.data).toBeDefined();
  });

  test("returns error when deviceId is missing", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "get_screen"}');
    expect(response.status).toBe("error");
    expect(response.message).toContain("deviceId");
  });
});

// === routeCommand - execute_action ===

describe("SkillCli - execute_action", () => {
  test("executes action and returns result (Req 7.1)", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand(
      '{"type": "execute_action", "deviceId": "dev1", "action": {"type": "tap", "x": 100, "y": 200}}',
    );
    expect(response.status).toBe("success");
    expect(response.message).toContain("tap");
  });

  test("returns error when deviceId is missing", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand(
      '{"type": "execute_action", "action": {"type": "tap", "x": 100, "y": 200}}',
    );
    expect(response.status).toBe("error");
    expect(response.message).toContain("deviceId");
  });

  test("returns error when action is missing", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand(
      '{"type": "execute_action", "deviceId": "dev1"}',
    );
    expect(response.status).toBe("error");
    expect(response.message).toContain("action");
  });
});

// === routeCommand - run_template ===

describe("SkillCli - run_template", () => {
  test("runs template and returns result (Req 7.1)", async () => {
    const { cli, templateEngine } = createCli();
    const template: OperationTemplate = {
      name: "open-app",
      description: "Opens an app",
      params: [],
      steps: [
        { order: 1, action: { type: "tap", x: 100, y: 200 }, description: "Tap" },
      ],
      metadata: { createdAt: "2024-01-01", source: "manual" },
    };
    templateEngine.templates.set("open-app", template);

    const response = await cli.handleCommand(
      '{"type": "run_template", "deviceId": "dev1", "templateName": "open-app"}',
    );
    expect(response.status).toBe("success");
  });

  test("returns error when template not found", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand(
      '{"type": "run_template", "deviceId": "dev1", "templateName": "nonexistent"}',
    );
    expect(response.status).toBe("error");
    expect(response.message).toContain("Template not found");
  });

  test("returns error when deviceId is missing", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand(
      '{"type": "run_template", "templateName": "open-app"}',
    );
    expect(response.status).toBe("error");
    expect(response.message).toContain("deviceId");
  });

  test("returns error when templateName is missing", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand(
      '{"type": "run_template", "deviceId": "dev1"}',
    );
    expect(response.status).toBe("error");
    expect(response.message).toContain("templateName");
  });
});

// === routeCommand - run_task ===

describe("SkillCli - run_task", () => {
  test("returns step-by-step guidance when no matching template (Req 7.1)", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand(
      '{"type": "run_task", "deviceId": "dev1", "taskGoal": "Open settings"}',
    );
    expect(response.status).toBe("success");
    expect(response.message).toContain("step-by-step");
    expect(response.message).toContain("get_screen");
    expect(response.message).toContain("execute_action");
    expect((response.data as any).mode).toBe("step-by-step");
  });

  test("runs template when matching template exists (Req 7.1)", async () => {
    const { cli, templateEngine } = createCli();
    const template: OperationTemplate = {
      name: "open-settings",
      description: "Opens settings app",
      params: [],
      steps: [
        { order: 1, action: { type: "tap", x: 100, y: 200 }, description: "Tap" },
      ],
      metadata: { createdAt: "2024-01-01", source: "manual", taskDescription: "open settings" },
    };
    templateEngine.templates.set("open-settings", template);

    const response = await cli.handleCommand(
      '{"type": "run_task", "deviceId": "dev1", "taskGoal": "open settings"}',
    );
    expect(response.status).toBe("success");
    expect(response.message).toContain("completed successfully");
  });

  test("returns error when deviceId is missing", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand(
      '{"type": "run_task", "taskGoal": "Open settings"}',
    );
    expect(response.status).toBe("error");
    expect(response.message).toContain("deviceId");
  });

  test("returns error when taskGoal is missing", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand(
      '{"type": "run_task", "deviceId": "dev1"}',
    );
    expect(response.status).toBe("error");
    expect(response.message).toContain("taskGoal");
  });
});

// === routeCommand - list_templates ===

describe("SkillCli - list_templates", () => {
  test("returns template list (Req 7.1)", async () => {
    const { cli, templateEngine } = createCli();
    templateEngine.templates.set("t1", {
      name: "t1",
      description: "Template 1",
      params: [],
      steps: [],
      metadata: { createdAt: "2024-01-01", source: "manual" },
    });

    const response = await cli.handleCommand('{"type": "list_templates"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("1");
    expect(response.data).toEqual([
      { name: "t1", description: "Template 1", params: [] },
    ]);
  });

  test("returns empty list when no templates", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "list_templates"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("0");
  });
});

// === routeCommand - convenience operations ===

describe("SkillCli - open_app", () => {
  test("opens app with packageName", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "open_app", "deviceId": "dev1", "packageName": "com.tencent.mm"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("com.tencent.mm");
  });

  test("returns error when deviceId is missing", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "open_app", "packageName": "com.tencent.mm"}');
    expect(response.status).toBe("error");
    expect(response.message).toContain("deviceId");
  });

  test("returns error when packageName is missing", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "open_app", "deviceId": "dev1"}');
    expect(response.status).toBe("error");
    expect(response.message).toContain("packageName");
  });
});

describe("SkillCli - go_back / go_home / scroll / wake / lock", () => {
  test("go_back succeeds", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "go_back", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("back");
  });

  test("go_home succeeds", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "go_home", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("home");
  });

  test("scroll_up succeeds", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "scroll_up", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("up");
  });

  test("scroll_down succeeds", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "scroll_down", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("down");
  });

  test("wake_screen succeeds", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "wake_screen", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("woken");
  });

  test("lock_screen succeeds", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "lock_screen", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("locked");
  });

  test("simple actions return error when deviceId is missing", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "go_back"}');
    expect(response.status).toBe("error");
    expect(response.message).toContain("deviceId");
  });
});

describe("SkillCli - get_current_app", () => {
  test("returns current app info", async () => {
    const { cli, adbClient } = createCli();
    adbClient.shell = async (_d: string, _c: string) => "  mResumedActivity: ActivityRecord{abc u0 com.tencent.mm/.ui.LauncherUI t123}";
    const response = await cli.handleCommand('{"type": "get_current_app", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("com.tencent.mm");
  });

  test("returns raw output when no match", async () => {
    const { cli, adbClient } = createCli();
    adbClient.shell = async (_d: string, _c: string) => "some other output";
    const response = await cli.handleCommand('{"type": "get_current_app", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect((response.data as any).raw).toBe("some other output");
  });

  test("returns error when deviceId is missing", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "get_current_app"}');
    expect(response.status).toBe("error");
    expect(response.message).toContain("deviceId");
  });
});

describe("parseInput - new commands", () => {
  test("parses open_app with packageName", () => {
    const cmd = parseInput('{"type": "open_app", "deviceId": "dev1", "packageName": "com.tencent.mm"}');
    expect(cmd.type).toBe("open_app");
    expect(cmd.packageName).toBe("com.tencent.mm");
  });

  test("parses go_back", () => {
    const cmd = parseInput('{"type": "go_back", "deviceId": "dev1"}');
    expect(cmd.type).toBe("go_back");
  });

  test("parses get_current_app", () => {
    const cmd = parseInput('{"type": "get_current_app", "deviceId": "dev1"}');
    expect(cmd.type).toBe("get_current_app");
  });
});


// === Convenience Commands ===

describe("SkillCli - open_app", () => {
  test("opens app with packageName", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand(
      '{"type": "open_app", "deviceId": "dev1", "packageName": "com.tencent.mm"}',
    );
    expect(response.status).toBe("success");
    expect(response.message).toContain("com.tencent.mm");
  });

  test("returns error when deviceId is missing", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "open_app", "packageName": "com.tencent.mm"}');
    expect(response.status).toBe("error");
    expect(response.message).toContain("deviceId");
  });

  test("returns error when packageName is missing", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "open_app", "deviceId": "dev1"}');
    expect(response.status).toBe("error");
    expect(response.message).toContain("packageName");
  });
});

describe("SkillCli - go_back", () => {
  test("presses back button", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "go_back", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("back");
  });

  test("returns error when deviceId is missing", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "go_back"}');
    expect(response.status).toBe("error");
    expect(response.message).toContain("deviceId");
  });
});

describe("SkillCli - go_home", () => {
  test("presses home button", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "go_home", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("home");
  });
});

describe("SkillCli - scroll_up / scroll_down", () => {
  test("scrolls up", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "scroll_up", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("up");
  });

  test("scrolls down", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "scroll_down", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("down");
  });
});

describe("SkillCli - wake_screen / lock_screen", () => {
  test("wakes screen", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "wake_screen", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("woken");
  });

  test("locks screen", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "lock_screen", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("locked");
  });
});

describe("SkillCli - get_current_app", () => {
  test("returns current app info", async () => {
    const { cli, adbClient } = createCli();
    // Mock shell to return activity info
    adbClient.shell = async (_d: string, _c: string) => {
      return "    mResumedActivity: ActivityRecord{abc u0 com.tencent.mm/.ui.LauncherUI t123}";
    };
    const response = await cli.handleCommand('{"type": "get_current_app", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect(response.message).toContain("com.tencent.mm");
    expect((response.data as any).packageName).toBe("com.tencent.mm");
  });

  test("returns error when deviceId is missing", async () => {
    const { cli } = createCli();
    const response = await cli.handleCommand('{"type": "get_current_app"}');
    expect(response.status).toBe("error");
    expect(response.message).toContain("deviceId");
  });

  test("returns raw output when no match found", async () => {
    const { cli, adbClient } = createCli();
    adbClient.shell = async (_d: string, _c: string) => "some other output";
    const response = await cli.handleCommand('{"type": "get_current_app", "deviceId": "dev1"}');
    expect(response.status).toBe("success");
    expect((response.data as any).raw).toBe("some other output");
  });
});

describe("parseInput - new convenience commands", () => {
  test("parses open_app command", () => {
    const cmd = parseInput('{"type": "open_app", "deviceId": "dev1", "packageName": "com.tencent.mm"}');
    expect(cmd.type).toBe("open_app");
    expect(cmd.packageName).toBe("com.tencent.mm");
  });

  test("parses go_back command", () => {
    const cmd = parseInput('{"type": "go_back", "deviceId": "dev1"}');
    expect(cmd.type).toBe("go_back");
  });

  test("parses get_current_app command", () => {
    const cmd = parseInput('{"type": "get_current_app", "deviceId": "dev1"}');
    expect(cmd.type).toBe("get_current_app");
  });

  test("parses wake_screen command", () => {
    const cmd = parseInput('{"type": "wake_screen", "deviceId": "dev1"}');
    expect(cmd.type).toBe("wake_screen");
  });

  test("parses lock_screen command", () => {
    const cmd = parseInput('{"type": "lock_screen", "deviceId": "dev1"}');
    expect(cmd.type).toBe("lock_screen");
  });
});
