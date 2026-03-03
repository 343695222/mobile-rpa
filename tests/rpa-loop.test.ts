import { describe, test, expect, beforeEach } from "bun:test";
import type { AdbClient } from "../src/adb-client";
import type { ScreenParser } from "../src/screen-parser";
import type { ActionExecutor } from "../src/action-executor";
import type { TemplateEngine } from "../src/template-engine";
import type {
  Action,
  ActionResult,
  DeviceInfo,
  ScreenState,
  ScreenDiff,
  UiElement,
  StepRecord,
  OperationTemplate,
  ResolvedTemplate,
  TemplateSummary,
  ValidationResult,
  ExecutionHistory,
  ExplorationResult,
  TemplateExecutionResult,
  LoopOptions,
} from "../src/types";
import { DefaultRpaLoop, type DecideActionFn } from "../src/rpa-loop";

// === Mock Implementations ===

function makeMockScreenState(deviceId: string, elements: Partial<UiElement>[] = []): ScreenState {
  return {
    timestamp: Date.now(),
    deviceId,
    elements: elements.map((e, i) => ({
      id: `elem_${i}`,
      type: "Button",
      text: `Button ${i}`,
      contentDesc: "",
      bounds: { left: 0, top: 0, right: 100, bottom: 50 },
      clickable: true,
      scrollable: false,
      focusable: true,
      enabled: true,
      resourceId: "",
      className: "android.widget.Button",
      ...e,
    })),
    rawXml: "<hierarchy></hierarchy>",
  };
}

class MockScreenParser implements ScreenParser {
  public screenStates: ScreenState[] = [];
  private callIndex = 0;

  async captureScreen(deviceId: string): Promise<ScreenState> {
    if (this.screenStates.length === 0) {
      return makeMockScreenState(deviceId, [{ text: "Default" }]);
    }
    const state = this.screenStates[Math.min(this.callIndex, this.screenStates.length - 1)];
    this.callIndex++;
    return state;
  }

  diffScreens(prev: ScreenState, curr: ScreenState): ScreenDiff {
    return { added: [], removed: [], changed: [] };
  }

  parseAccessibilityTree(xml: string): UiElement[] {
    return [];
  }
}

class MockActionExecutor implements ActionExecutor {
  public executedActions: Array<{ deviceId: string; action: Action }> = [];
  public shouldFail = false;
  public failAtStep = -1; // fail at specific step (0-indexed)
  public failMessage = "Mock action failed";

  async execute(deviceId: string, action: Action): Promise<ActionResult> {
    this.executedActions.push({ deviceId, action });
    const stepIndex = this.executedActions.length - 1;

    if (this.shouldFail || stepIndex === this.failAtStep) {
      return {
        success: false,
        action,
        error: this.failMessage,
        durationMs: 10,
      };
    }

    return {
      success: true,
      action,
      durationMs: 10,
    };
  }

  async executeBatch(deviceId: string, actions: Action[]): Promise<ActionResult[]> {
    const results: ActionResult[] = [];
    for (const action of actions) {
      results.push(await this.execute(deviceId, action));
    }
    return results;
  }

  async validateConnection(deviceId: string): Promise<boolean> {
    return true;
  }
}

class MockTemplateEngine implements TemplateEngine {
  public templates: Map<string, OperationTemplate> = new Map();
  public generatedTemplates: OperationTemplate[] = [];
  public generateCalled = false;

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

  validateTemplate(template: unknown): ValidationResult {
    return { valid: true, errors: [] };
  }

  resolveParams(template: OperationTemplate, params: Record<string, string>): ResolvedTemplate {
    return { name: template.name, steps: template.steps };
  }

  generateFromHistory(history: ExecutionHistory, taskName: string): OperationTemplate {
    this.generateCalled = true;
    const generated: OperationTemplate = {
      name: taskName.toLowerCase().replace(/\s+/g, "-"),
      description: `Auto-generated from: ${taskName}`,
      params: [],
      steps: history.steps.map((s, i) => ({
        order: i + 1,
        action: s.action,
        description: `Step ${i + 1}`,
      })),
      metadata: {
        createdAt: new Date().toISOString(),
        source: "auto-generated",
        taskDescription: taskName,
      },
    };
    this.generatedTemplates.push(generated);
    return generated;
  }

  findMatchingTemplate(taskDescription: string): OperationTemplate | undefined {
    for (const t of this.templates.values()) {
      const words = taskDescription.toLowerCase().split(/\s+/);
      const searchText = `${t.name} ${t.description}`.toLowerCase();
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

// === Helpers ===

function makeTemplate(overrides: Partial<OperationTemplate> = {}): OperationTemplate {
  return {
    name: "test-template",
    description: "A test template",
    params: [],
    steps: [
      { order: 1, action: { type: "tap", x: 100, y: 200 }, description: "Tap button" },
      { order: 2, action: { type: "wait", ms: 500 }, description: "Wait" },
    ],
    metadata: {
      createdAt: "2024-01-01T00:00:00Z",
      source: "manual",
    },
    ...overrides,
  };
}

function makeStepRecord(overrides: Partial<StepRecord> = {}): StepRecord {
  return {
    stepNumber: 1,
    screenSummary: "[2 elements] Button 0,Button 1",
    action: { type: "tap", x: 100, y: 200 },
    result: { success: true, action: { type: "tap", x: 100, y: 200 }, durationMs: 10 },
    timestamp: Date.now(),
    ...overrides,
  };
}

/** Simple decideAction that always returns a tap action */
const alwaysTap: DecideActionFn = (_screen, _goal) => ({
  type: "tap",
  x: 100,
  y: 200,
});

/** decideAction that returns different actions based on step count */
function varyingActions(): DecideActionFn {
  let callCount = 0;
  return (_screen, _goal) => {
    callCount++;
    if (callCount % 3 === 0) {
      return { type: "wait", ms: 100 };
    } else if (callCount % 3 === 1) {
      return { type: "tap", x: callCount * 10, y: callCount * 20 };
    } else {
      return { type: "input_text", text: `text_${callCount}` };
    }
  };
}

// === detectStuck Tests ===

describe("RpaLoop - detectStuck", () => {
  let loop: DefaultRpaLoop;

  beforeEach(() => {
    loop = new DefaultRpaLoop(
      new MockScreenParser(),
      new MockActionExecutor(),
      new MockTemplateEngine(),
      alwaysTap,
    );
  });

  test("returns false when history is shorter than threshold (Req 6.5)", () => {
    const history = [
      makeStepRecord({ stepNumber: 1 }),
      makeStepRecord({ stepNumber: 2 }),
    ];
    expect(loop.detectStuck(history)).toBe(false);
  });

  test("returns true when last N steps have same action and screenSummary (Req 6.5)", () => {
    const history = [
      makeStepRecord({ stepNumber: 1, action: { type: "tap", x: 50, y: 50 }, screenSummary: "same" }),
      makeStepRecord({ stepNumber: 2, action: { type: "tap", x: 50, y: 50 }, screenSummary: "same" }),
      makeStepRecord({ stepNumber: 3, action: { type: "tap", x: 50, y: 50 }, screenSummary: "same" }),
    ];
    expect(loop.detectStuck(history)).toBe(true);
  });

  test("returns false when actions differ", () => {
    const history = [
      makeStepRecord({ stepNumber: 1, action: { type: "tap", x: 50, y: 50 }, screenSummary: "same" }),
      makeStepRecord({ stepNumber: 2, action: { type: "tap", x: 100, y: 100 }, screenSummary: "same" }),
      makeStepRecord({ stepNumber: 3, action: { type: "tap", x: 50, y: 50 }, screenSummary: "same" }),
    ];
    expect(loop.detectStuck(history)).toBe(false);
  });

  test("returns false when screenSummary differs", () => {
    const history = [
      makeStepRecord({ stepNumber: 1, action: { type: "tap", x: 50, y: 50 }, screenSummary: "screen A" }),
      makeStepRecord({ stepNumber: 2, action: { type: "tap", x: 50, y: 50 }, screenSummary: "screen B" }),
      makeStepRecord({ stepNumber: 3, action: { type: "tap", x: 50, y: 50 }, screenSummary: "screen A" }),
    ];
    expect(loop.detectStuck(history)).toBe(false);
  });

  test("only checks the last N steps, not earlier ones", () => {
    const history = [
      makeStepRecord({ stepNumber: 1, action: { type: "wait", ms: 100 }, screenSummary: "different" }),
      makeStepRecord({ stepNumber: 2, action: { type: "tap", x: 50, y: 50 }, screenSummary: "same" }),
      makeStepRecord({ stepNumber: 3, action: { type: "tap", x: 50, y: 50 }, screenSummary: "same" }),
      makeStepRecord({ stepNumber: 4, action: { type: "tap", x: 50, y: 50 }, screenSummary: "same" }),
    ];
    expect(loop.detectStuck(history)).toBe(true);
  });

  test("respects custom stuckThreshold", () => {
    const history = [
      makeStepRecord({ stepNumber: 1, action: { type: "tap", x: 50, y: 50 }, screenSummary: "same" }),
      makeStepRecord({ stepNumber: 2, action: { type: "tap", x: 50, y: 50 }, screenSummary: "same" }),
    ];
    // With threshold 2, should detect stuck
    expect(loop.detectStuck(history, 2)).toBe(true);
    // With threshold 3, should not (only 2 steps)
    expect(loop.detectStuck(history, 3)).toBe(false);
  });

  test("returns false for empty history", () => {
    expect(loop.detectStuck([])).toBe(false);
  });
});

// === runExploration Tests ===

describe("RpaLoop - runExploration (no decideAction - hybrid mode)", () => {
  test("returns step-by-step guidance when no decideAction provided", async () => {
    const loop = new DefaultRpaLoop(
      new MockScreenParser(),
      new MockActionExecutor(),
      new MockTemplateEngine(),
    );

    const result = await loop.runExploration("dev1", "Open settings");

    expect(result.success).toBe(false);
    expect(result.message).toContain("step-by-step");
    expect(result.message).toContain("get_screen");
    expect(result.message).toContain("execute_action");
    expect(result.history.steps).toHaveLength(0);
  });
});

describe("RpaLoop - runExploration", () => {
  let screenParser: MockScreenParser;
  let actionExecutor: MockActionExecutor;
  let templateEngine: MockTemplateEngine;

  beforeEach(() => {
    screenParser = new MockScreenParser();
    actionExecutor = new MockActionExecutor();
    templateEngine = new MockTemplateEngine();
  });

  test("executes exploration loop and records steps (Req 6.1, 6.3)", async () => {
    // Use varying actions to avoid stuck detection
    const loop = new DefaultRpaLoop(screenParser, actionExecutor, templateEngine, varyingActions());

    // Set different screen states to avoid stuck detection
    screenParser.screenStates = [
      makeMockScreenState("dev1", [{ text: "Screen A" }]),
      makeMockScreenState("dev1", [{ text: "Screen B" }]),
      makeMockScreenState("dev1", [{ text: "Screen C" }]),
    ];

    const result = await loop.runExploration("dev1", "Open settings", { maxSteps: 3 });

    expect(result.success).toBe(true);
    expect(result.history.steps).toHaveLength(3);
    expect(result.history.taskGoal).toBe("Open settings");

    // Verify step numbers are sequential
    result.history.steps.forEach((step, i) => {
      expect(step.stepNumber).toBe(i + 1);
    });
  });

  test("records screenSummary for each step (Req 6.3)", async () => {
    const loop = new DefaultRpaLoop(screenParser, actionExecutor, templateEngine, varyingActions());
    screenParser.screenStates = [
      makeMockScreenState("dev1", [{ text: "Home" }]),
      makeMockScreenState("dev1", [{ text: "Settings" }]),
    ];

    const result = await loop.runExploration("dev1", "test", { maxSteps: 2 });

    expect(result.history.steps[0].screenSummary).toContain("Home");
    expect(result.history.steps[1].screenSummary).toContain("Settings");
  });

  test("enforces maxSteps limit (Req 6.4)", async () => {
    const loop = new DefaultRpaLoop(screenParser, actionExecutor, templateEngine, varyingActions());

    // Provide enough different screens to avoid stuck
    screenParser.screenStates = Array.from({ length: 10 }, (_, i) =>
      makeMockScreenState("dev1", [{ text: `Screen ${i}` }]),
    );

    const result = await loop.runExploration("dev1", "test", { maxSteps: 5 });

    expect(result.history.steps.length).toBeLessThanOrEqual(5);
    expect(actionExecutor.executedActions.length).toBeLessThanOrEqual(5);
  });

  test("detects stuck state and stops (Req 6.5)", async () => {
    // alwaysTap returns the same action every time
    const loop = new DefaultRpaLoop(screenParser, actionExecutor, templateEngine, alwaysTap);

    // Same screen state every time → stuck
    screenParser.screenStates = [
      makeMockScreenState("dev1", [{ text: "Same" }]),
    ];

    const result = await loop.runExploration("dev1", "test", { maxSteps: 10, stuckThreshold: 3 });

    expect(result.success).toBe(false);
    expect(result.message).toContain("Stuck");
    expect(result.history.steps).toHaveLength(3);
  });

  test("calls generateFromHistory on success (Req 6.6)", async () => {
    const loop = new DefaultRpaLoop(screenParser, actionExecutor, templateEngine, varyingActions());
    screenParser.screenStates = Array.from({ length: 3 }, (_, i) =>
      makeMockScreenState("dev1", [{ text: `Screen ${i}` }]),
    );

    const result = await loop.runExploration("dev1", "Open app", { maxSteps: 3 });

    expect(result.success).toBe(true);
    expect(templateEngine.generateCalled).toBe(true);
    expect(result.generatedTemplate).toBeDefined();
    expect(result.generatedTemplate!.metadata.source).toBe("auto-generated");
  });

  test("does NOT call generateFromHistory on failure", async () => {
    const loop = new DefaultRpaLoop(screenParser, actionExecutor, templateEngine, alwaysTap);
    screenParser.screenStates = [makeMockScreenState("dev1", [{ text: "Same" }])];

    const result = await loop.runExploration("dev1", "test", { maxSteps: 10, stuckThreshold: 3 });

    expect(result.success).toBe(false);
    expect(templateEngine.generateCalled).toBe(false);
    expect(result.generatedTemplate).toBeUndefined();
  });

  test("stops on action failure", async () => {
    actionExecutor.failAtStep = 1; // fail on second action
    const loop = new DefaultRpaLoop(screenParser, actionExecutor, templateEngine, varyingActions());
    screenParser.screenStates = [
      makeMockScreenState("dev1", [{ text: "A" }]),
      makeMockScreenState("dev1", [{ text: "B" }]),
    ];

    const result = await loop.runExploration("dev1", "test", { maxSteps: 10 });

    expect(result.success).toBe(false);
    expect(result.message).toContain("Action failed");
    expect(result.history.steps).toHaveLength(2);
  });

  test("enforces timeout (Req 6.4)", async () => {
    const loop = new DefaultRpaLoop(screenParser, actionExecutor, templateEngine, varyingActions());
    screenParser.screenStates = Array.from({ length: 30 }, (_, i) =>
      makeMockScreenState("dev1", [{ text: `Screen ${i}` }]),
    );

    // Use a very short timeout (1ms) to trigger timeout quickly
    const result = await loop.runExploration("dev1", "test", { maxSteps: 100, timeoutMs: 1 });

    // Should have stopped due to timeout (may complete 0 or a few steps before checking)
    expect(result.success).toBe(false);
    expect(result.message).toContain("Timeout");
  });

  test("history includes correct startTime and endTime", async () => {
    const loop = new DefaultRpaLoop(screenParser, actionExecutor, templateEngine, varyingActions());
    screenParser.screenStates = [makeMockScreenState("dev1", [{ text: "A" }])];

    const before = Date.now();
    const result = await loop.runExploration("dev1", "test", { maxSteps: 1 });
    const after = Date.now();

    expect(result.history.startTime).toBeGreaterThanOrEqual(before);
    expect(result.history.endTime).toBeLessThanOrEqual(after);
    expect(result.history.endTime).toBeGreaterThanOrEqual(result.history.startTime);
  });

  test("uses default options when none provided", async () => {
    const loop = new DefaultRpaLoop(screenParser, actionExecutor, templateEngine, varyingActions());
    screenParser.screenStates = Array.from({ length: 35 }, (_, i) =>
      makeMockScreenState("dev1", [{ text: `Screen ${i}` }]),
    );

    const result = await loop.runExploration("dev1", "test");

    // Default maxSteps is 30
    expect(result.history.steps.length).toBeLessThanOrEqual(30);
  });
});

// === runTemplate Tests ===

describe("RpaLoop - runTemplate", () => {
  let screenParser: MockScreenParser;
  let actionExecutor: MockActionExecutor;
  let templateEngine: MockTemplateEngine;
  let loop: DefaultRpaLoop;

  beforeEach(() => {
    screenParser = new MockScreenParser();
    actionExecutor = new MockActionExecutor();
    templateEngine = new MockTemplateEngine();
    loop = new DefaultRpaLoop(screenParser, actionExecutor, templateEngine, alwaysTap);
  });

  test("executes all template steps sequentially (Req 6.2, 6.7)", async () => {
    const template: ResolvedTemplate = {
      name: "test",
      steps: [
        { order: 1, action: { type: "tap", x: 100, y: 200 }, description: "Tap" },
        { order: 2, action: { type: "input_text", text: "hello" }, description: "Type" },
        { order: 3, action: { type: "wait", ms: 500 }, description: "Wait" },
      ],
    };

    const result = await loop.runTemplate("dev1", template);

    expect(result.success).toBe(true);
    expect(result.stepsCompleted).toBe(3);
    expect(result.totalSteps).toBe(3);
    expect(result.stepResults).toHaveLength(3);
    expect(result.stepResults.every((r) => r.success)).toBe(true);
  });

  test("stops on step failure and reports progress (Req 6.7)", async () => {
    actionExecutor.failAtStep = 1; // fail on second step

    const template: ResolvedTemplate = {
      name: "test",
      steps: [
        { order: 1, action: { type: "tap", x: 100, y: 200 }, description: "Tap" },
        { order: 2, action: { type: "input_text", text: "hello" }, description: "Type" },
        { order: 3, action: { type: "wait", ms: 500 }, description: "Wait" },
      ],
    };

    const result = await loop.runTemplate("dev1", template);

    expect(result.success).toBe(false);
    expect(result.stepsCompleted).toBe(2);
    expect(result.totalSteps).toBe(3);
    expect(result.stepResults).toHaveLength(2);
    expect(result.stepResults[0].success).toBe(true);
    expect(result.stepResults[1].success).toBe(false);
    expect(result.message).toContain("Step 2/3 failed");
  });

  test("handles empty template", async () => {
    const template: ResolvedTemplate = { name: "empty", steps: [] };

    const result = await loop.runTemplate("dev1", template);

    expect(result.success).toBe(true);
    expect(result.stepsCompleted).toBe(0);
    expect(result.totalSteps).toBe(0);
    expect(result.stepResults).toHaveLength(0);
  });

  test("executes actions with correct deviceId", async () => {
    const template: ResolvedTemplate = {
      name: "test",
      steps: [
        { order: 1, action: { type: "tap", x: 50, y: 50 }, description: "Tap" },
      ],
    };

    await loop.runTemplate("my-device-123", template);

    expect(actionExecutor.executedActions[0].deviceId).toBe("my-device-123");
  });

  test("returns correct action types in stepResults", async () => {
    const template: ResolvedTemplate = {
      name: "test",
      steps: [
        { order: 1, action: { type: "tap", x: 10, y: 20 }, description: "Tap" },
        { order: 2, action: { type: "key_event", keyCode: 4 }, description: "Back" },
      ],
    };

    const result = await loop.runTemplate("dev1", template);

    expect(result.stepResults[0].action.type).toBe("tap");
    expect(result.stepResults[1].action.type).toBe("key_event");
  });
});

// === run (mode selection) Tests ===

describe("RpaLoop - run (mode selection)", () => {
  let screenParser: MockScreenParser;
  let actionExecutor: MockActionExecutor;
  let templateEngine: MockTemplateEngine;
  let loop: DefaultRpaLoop;

  beforeEach(() => {
    screenParser = new MockScreenParser();
    actionExecutor = new MockActionExecutor();
    templateEngine = new MockTemplateEngine();
    loop = new DefaultRpaLoop(screenParser, actionExecutor, templateEngine, varyingActions());
  });

  test("uses template mode when matching template exists (Req 6.2)", async () => {
    const template = makeTemplate({ name: "open-settings", description: "Opens settings" });
    templateEngine.templates.set("open-settings", template);

    const result = await loop.run("dev1", "open settings");

    // Should be a TemplateExecutionResult (has stepsCompleted/totalSteps)
    expect("stepsCompleted" in result).toBe(true);
    const templateResult = result as TemplateExecutionResult;
    expect(templateResult.totalSteps).toBe(2);
    expect(templateResult.success).toBe(true);
  });

  test("uses exploration mode when no matching template (Req 6.1)", async () => {
    screenParser.screenStates = Array.from({ length: 5 }, (_, i) =>
      makeMockScreenState("dev1", [{ text: `Screen ${i}` }]),
    );

    const result = await loop.run("dev1", "do something unique", undefined, { maxSteps: 3 });

    // Should be an ExplorationResult (has history)
    expect("history" in result).toBe(true);
    const explorationResult = result as ExplorationResult;
    expect(explorationResult.history.taskGoal).toBe("do something unique");
  });

  test("mode selection is consistent with findMatchingTemplate (Req 6.1, 6.2)", async () => {
    const template = makeTemplate({ name: "send-message", description: "Send a message" });
    templateEngine.templates.set("send-message", template);

    // Query that matches
    const matchResult = await loop.run("dev1", "send message");
    expect("stepsCompleted" in matchResult).toBe(true);

    // Query that doesn't match
    screenParser.screenStates = Array.from({ length: 5 }, (_, i) =>
      makeMockScreenState("dev1", [{ text: `Screen ${i}` }]),
    );
    const noMatchResult = await loop.run("dev1", "xyz-no-match-abc", undefined, { maxSteps: 2 });
    expect("history" in noMatchResult).toBe(true);
  });
});
