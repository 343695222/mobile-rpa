import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { DefaultTemplateEngine } from "../src/template-engine";
import type { OperationTemplate, TemplateStep, Action, ExecutionHistory, StepRecord, ActionResult } from "../src/types";

// === Helpers ===

function makeValidTemplate(overrides: Partial<OperationTemplate> = {}): OperationTemplate {
  return {
    name: "test-template",
    description: "A test template",
    params: [
      { name: "appName", description: "App to open", required: true },
      { name: "delay", description: "Wait time", required: false, defaultValue: "1000" },
    ],
    steps: [
      {
        order: 1,
        action: { type: "input_text", text: "{{appName}}" } as Action,
        description: "Type {{appName}} into search",
      },
      {
        order: 2,
        action: { type: "wait", ms: 500 } as Action,
        description: "Wait for results",
      },
    ],
    metadata: {
      createdAt: "2024-01-01T00:00:00Z",
      source: "manual",
    },
    ...overrides,
  };
}

// === validateTemplate Tests ===

describe("TemplateEngine - validateTemplate", () => {
  let engine: DefaultTemplateEngine;

  beforeEach(() => {
    engine = new DefaultTemplateEngine();
  });

  test("returns valid for a correct template (Req 5.2)", () => {
    const result = engine.validateTemplate(makeValidTemplate());
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  test("rejects null input", () => {
    const result = engine.validateTemplate(null);
    expect(result.valid).toBe(false);
    expect(result.errors[0]).toContain("non-null object");
  });

  test("rejects array input", () => {
    const result = engine.validateTemplate([]);
    expect(result.valid).toBe(false);
  });

  test("reports missing name", () => {
    const t = makeValidTemplate();
    (t as any).name = "";
    const result = engine.validateTemplate(t);
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes("name"))).toBe(true);
  });

  test("reports missing description", () => {
    const t = makeValidTemplate();
    (t as any).description = 123;
    const result = engine.validateTemplate(t);
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes("description"))).toBe(true);
  });

  test("reports missing params array", () => {
    const t = makeValidTemplate();
    (t as any).params = "not-array";
    const result = engine.validateTemplate(t);
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes("params"))).toBe(true);
  });

  test("reports invalid param entries", () => {
    const t = makeValidTemplate();
    t.params = [{ name: "", description: "x", required: true }];
    const result = engine.validateTemplate(t);
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes("params[0]"))).toBe(true);
  });

  test("reports missing steps array", () => {
    const t = makeValidTemplate();
    (t as any).steps = null;
    const result = engine.validateTemplate(t);
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes("steps"))).toBe(true);
  });

  test("reports invalid step entries", () => {
    const t = makeValidTemplate();
    t.steps = [{ order: "one" as any, action: null as any, description: 42 as any }];
    const result = engine.validateTemplate(t);
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThanOrEqual(1);
  });

  test("reports multiple errors at once", () => {
    const result = engine.validateTemplate({ foo: "bar" });
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThanOrEqual(3); // name, description, params, steps
  });
});

// === serialize / deserialize Tests ===

describe("TemplateEngine - serialize/deserialize", () => {
  let engine: DefaultTemplateEngine;

  beforeEach(() => {
    engine = new DefaultTemplateEngine();
  });

  test("roundtrip produces equivalent template (Req 5.8)", () => {
    const original = makeValidTemplate();
    const json = engine.serialize(original);
    const restored = engine.deserialize(json);
    expect(restored).toEqual(original);
  });

  test("serialize produces formatted JSON", () => {
    const json = engine.serialize(makeValidTemplate());
    expect(json).toContain("\n"); // 2-space indent
    expect(json.startsWith("{")).toBe(true);
  });

  test("deserialize throws on invalid JSON", () => {
    expect(() => engine.deserialize("not json")).toThrow("Invalid JSON");
  });

  test("deserialize throws on invalid template structure", () => {
    expect(() => engine.deserialize('{"foo": "bar"}')).toThrow("Invalid template");
  });
});

// === resolveParams Tests ===

describe("TemplateEngine - resolveParams", () => {
  let engine: DefaultTemplateEngine;

  beforeEach(() => {
    engine = new DefaultTemplateEngine();
  });

  test("replaces placeholders in step descriptions (Req 5.3, 5.4)", () => {
    const template = makeValidTemplate();
    const resolved = engine.resolveParams(template, { appName: "Chrome" });

    expect(resolved.steps[0].description).toBe("Type Chrome into search");
    expect(resolved.name).toBe("test-template");
  });

  test("replaces placeholders in action text fields (Req 5.4)", () => {
    const template = makeValidTemplate();
    const resolved = engine.resolveParams(template, { appName: "Settings" });

    const action = resolved.steps[0].action as { type: "input_text"; text: string };
    expect(action.text).toBe("Settings");
  });

  test("applies default values for optional params", () => {
    const template = makeValidTemplate();
    const resolved = engine.resolveParams(template, { appName: "Maps" });
    // delay has defaultValue "1000", should not cause error
    expect(resolved.steps).toHaveLength(2);
  });

  test("throws on missing required params (Req 5.5)", () => {
    const template = makeValidTemplate();
    expect(() => engine.resolveParams(template, {})).toThrow("Missing required parameters: appName");
  });

  test("lists all missing required params in error", () => {
    const template = makeValidTemplate({
      params: [
        { name: "a", description: "A", required: true },
        { name: "b", description: "B", required: true },
        { name: "c", description: "C", required: false },
      ],
    });
    expect(() => engine.resolveParams(template, {})).toThrow("a, b");
  });

  test("does not mutate original template", () => {
    const template = makeValidTemplate();
    const originalDesc = template.steps[0].description;
    engine.resolveParams(template, { appName: "Chrome" });
    expect(template.steps[0].description).toBe(originalDesc);
  });

  test("no placeholders remain after full resolution (Req 5.3)", () => {
    const template = makeValidTemplate();
    const resolved = engine.resolveParams(template, { appName: "YouTube" });
    const json = JSON.stringify(resolved);
    expect(json).not.toContain("{{");
  });
});

// === loadTemplates Tests ===

describe("TemplateEngine - loadTemplates", () => {
  let engine: DefaultTemplateEngine;
  let tmpDir: string;

  beforeEach(async () => {
    engine = new DefaultTemplateEngine();
    tmpDir = await mkdtemp(join(tmpdir(), "te-test-"));
  });

  afterEach(async () => {
    await rm(tmpDir, { recursive: true, force: true });
  });

  test("loads valid templates from directory (Req 5.6)", async () => {
    const t1 = makeValidTemplate({ name: "template-one" });
    const t2 = makeValidTemplate({ name: "template-two" });
    await writeFile(join(tmpDir, "t1.json"), JSON.stringify(t1));
    await writeFile(join(tmpDir, "t2.json"), JSON.stringify(t2));

    const loaded = await engine.loadTemplates(tmpDir);

    expect(loaded).toHaveLength(2);
    const names = loaded.map((t) => t.name).sort();
    expect(names).toEqual(["template-one", "template-two"]);
  });

  test("skips invalid JSON files", async () => {
    const valid = makeValidTemplate({ name: "good" });
    await writeFile(join(tmpDir, "good.json"), JSON.stringify(valid));
    await writeFile(join(tmpDir, "bad.json"), "not valid json {{{");

    const loaded = await engine.loadTemplates(tmpDir);

    expect(loaded).toHaveLength(1);
    expect(loaded[0].name).toBe("good");
  });

  test("skips files that fail validation", async () => {
    await writeFile(join(tmpDir, "invalid.json"), JSON.stringify({ foo: "bar" }));

    const loaded = await engine.loadTemplates(tmpDir);

    expect(loaded).toHaveLength(0);
  });

  test("ignores non-json files", async () => {
    const valid = makeValidTemplate({ name: "only-one" });
    await writeFile(join(tmpDir, "template.json"), JSON.stringify(valid));
    await writeFile(join(tmpDir, "readme.txt"), "not a template");

    const loaded = await engine.loadTemplates(tmpDir);

    expect(loaded).toHaveLength(1);
  });

  test("returns empty array for non-existent directory", async () => {
    const loaded = await engine.loadTemplates("/tmp/nonexistent-dir-xyz-12345");
    expect(loaded).toHaveLength(0);
  });

  test("makes loaded templates available via getTemplate", async () => {
    const t = makeValidTemplate({ name: "findable" });
    await writeFile(join(tmpDir, "findable.json"), JSON.stringify(t));

    await engine.loadTemplates(tmpDir);

    expect(engine.getTemplate("findable")).toBeDefined();
    expect(engine.getTemplate("findable")!.name).toBe("findable");
  });
});

// === listTemplates Tests ===

describe("TemplateEngine - listTemplates", () => {
  let engine: DefaultTemplateEngine;
  let tmpDir: string;

  beforeEach(async () => {
    engine = new DefaultTemplateEngine();
    tmpDir = await mkdtemp(join(tmpdir(), "te-list-"));
  });

  afterEach(async () => {
    await rm(tmpDir, { recursive: true, force: true });
  });

  test("returns summaries with name, description, params (Req 5.7)", async () => {
    const t = makeValidTemplate({ name: "my-template", description: "Does stuff" });
    await writeFile(join(tmpDir, "my.json"), JSON.stringify(t));
    await engine.loadTemplates(tmpDir);

    const summaries = engine.listTemplates();

    expect(summaries).toHaveLength(1);
    expect(summaries[0].name).toBe("my-template");
    expect(summaries[0].description).toBe("Does stuff");
    expect(summaries[0].params).toHaveLength(2);
  });

  test("returns empty array when no templates loaded", () => {
    expect(engine.listTemplates()).toHaveLength(0);
  });
});

// === saveTemplate Tests ===

describe("TemplateEngine - saveTemplate", () => {
  let engine: DefaultTemplateEngine;
  let tmpDir: string;

  beforeEach(async () => {
    engine = new DefaultTemplateEngine();
    tmpDir = await mkdtemp(join(tmpdir(), "te-save-"));
  });

  afterEach(async () => {
    await rm(tmpDir, { recursive: true, force: true });
  });

  test("saves template as JSON file and makes it retrievable", async () => {
    const t = makeValidTemplate({ name: "saved-template" });
    await engine.saveTemplate(t, tmpDir);

    // Should be retrievable
    expect(engine.getTemplate("saved-template")).toBeDefined();

    // Should be loadable by a new engine
    const engine2 = new DefaultTemplateEngine();
    const loaded = await engine2.loadTemplates(tmpDir);
    expect(loaded).toHaveLength(1);
    expect(loaded[0].name).toBe("saved-template");
  });

  test("creates directory if it does not exist", async () => {
    const nestedDir = join(tmpDir, "nested", "dir");
    const t = makeValidTemplate({ name: "nested-save" });

    await engine.saveTemplate(t, nestedDir);

    const engine2 = new DefaultTemplateEngine();
    const loaded = await engine2.loadTemplates(nestedDir);
    expect(loaded).toHaveLength(1);
  });
});

// === getTemplate Tests ===

describe("TemplateEngine - getTemplate", () => {
  test("returns undefined for unknown template", () => {
    const engine = new DefaultTemplateEngine();
    expect(engine.getTemplate("nonexistent")).toBeUndefined();
  });
});

// === Helper: build an ExecutionHistory ===

function makeStepRecord(overrides: Partial<StepRecord> & { action: Action }): StepRecord {
  return {
    stepNumber: 1,
    screenSummary: "some screen",
    result: { success: true, action: overrides.action, durationMs: 100 },
    timestamp: Date.now(),
    ...overrides,
  };
}

function makeHistory(steps: StepRecord[], taskGoal = "Test task"): ExecutionHistory {
  return {
    taskGoal,
    steps,
    startTime: Date.now() - 5000,
    endTime: Date.now(),
  };
}

// === generateFromHistory Tests ===

describe("TemplateEngine - generateFromHistory", () => {
  let engine: DefaultTemplateEngine;

  beforeEach(() => {
    engine = new DefaultTemplateEngine();
  });

  test("generates template with correct step count (Req 5b.2)", () => {
    const history = makeHistory([
      makeStepRecord({ stepNumber: 1, action: { type: "tap", x: 100, y: 200 } }),
      makeStepRecord({ stepNumber: 2, action: { type: "wait", ms: 500 } }),
      makeStepRecord({ stepNumber: 3, action: { type: "tap", x: 300, y: 400 } }),
    ]);

    const template = engine.generateFromHistory(history, "Open Settings");

    expect(template.steps).toHaveLength(3);
    expect(template.steps[0].order).toBe(1);
    expect(template.steps[1].order).toBe(2);
    expect(template.steps[2].order).toBe(3);
  });

  test("sets metadata.source to auto-generated (Req 5b.2)", () => {
    const history = makeHistory([
      makeStepRecord({ stepNumber: 1, action: { type: "tap", x: 50, y: 50 } }),
    ]);

    const template = engine.generateFromHistory(history, "My Task");

    expect(template.metadata.source).toBe("auto-generated");
  });

  test("sets metadata.taskDescription to the taskName", () => {
    const history = makeHistory([
      makeStepRecord({ stepNumber: 1, action: { type: "tap", x: 50, y: 50 } }),
    ]);

    const template = engine.generateFromHistory(history, "Send a message");

    expect(template.metadata.taskDescription).toBe("Send a message");
  });

  test("sets metadata.createdAt to a valid ISO timestamp", () => {
    const history = makeHistory([
      makeStepRecord({ stepNumber: 1, action: { type: "tap", x: 50, y: 50 } }),
    ]);

    const before = new Date().toISOString();
    const template = engine.generateFromHistory(history, "Task");
    const after = new Date().toISOString();

    expect(template.metadata.createdAt >= before).toBe(true);
    expect(template.metadata.createdAt <= after).toBe(true);
  });

  test("extracts input_text steps as parameterized placeholders (Req 5b.3)", () => {
    const history = makeHistory([
      makeStepRecord({ stepNumber: 1, action: { type: "tap", x: 100, y: 200 } }),
      makeStepRecord({ stepNumber: 2, action: { type: "input_text", text: "Hello World" } }),
      makeStepRecord({ stepNumber: 3, action: { type: "tap", x: 300, y: 400 } }),
    ]);

    const template = engine.generateFromHistory(history, "Type greeting");

    // Should have one param extracted from the input_text step
    expect(template.params).toHaveLength(1);
    expect(template.params[0].name).toBe("param_0");
    expect(template.params[0].required).toBe(true);
    expect(template.params[0].defaultValue).toBe("Hello World");

    // The action text should be replaced with placeholder
    const inputStep = template.steps[1];
    expect((inputStep.action as { type: "input_text"; text: string }).text).toBe("{{param_0}}");
  });

  test("extracts multiple input_text steps as separate params", () => {
    const history = makeHistory([
      makeStepRecord({ stepNumber: 1, action: { type: "input_text", text: "user@example.com" } }),
      makeStepRecord({ stepNumber: 2, action: { type: "input_text", text: "password123" } }),
    ]);

    const template = engine.generateFromHistory(history, "Login");

    expect(template.params).toHaveLength(2);
    expect(template.params[0].name).toBe("param_0");
    expect(template.params[0].defaultValue).toBe("user@example.com");
    expect(template.params[1].name).toBe("param_1");
    expect(template.params[1].defaultValue).toBe("password123");

    expect((template.steps[0].action as any).text).toBe("{{param_0}}");
    expect((template.steps[1].action as any).text).toBe("{{param_1}}");
  });

  test("non-input_text steps have no params extracted", () => {
    const history = makeHistory([
      makeStepRecord({ stepNumber: 1, action: { type: "tap", x: 10, y: 20 } }),
      makeStepRecord({ stepNumber: 2, action: { type: "swipe", x1: 0, y1: 0, x2: 100, y2: 100, duration: 300 } }),
      makeStepRecord({ stepNumber: 3, action: { type: "key_event", keyCode: 4 } }),
      makeStepRecord({ stepNumber: 4, action: { type: "wait", ms: 1000 } }),
    ]);

    const template = engine.generateFromHistory(history, "Navigate");

    expect(template.params).toHaveLength(0);
    expect(template.steps).toHaveLength(4);
  });

  test("generates a kebab-case name from taskName", () => {
    const history = makeHistory([
      makeStepRecord({ stepNumber: 1, action: { type: "tap", x: 10, y: 20 } }),
    ]);

    const template = engine.generateFromHistory(history, "Open My App");

    expect(template.name).toBe("open-my-app");
  });

  test("generated template passes validation", () => {
    const history = makeHistory([
      makeStepRecord({ stepNumber: 1, action: { type: "tap", x: 100, y: 200 } }),
      makeStepRecord({ stepNumber: 2, action: { type: "input_text", text: "test" } }),
    ]);

    const template = engine.generateFromHistory(history, "Valid Task");
    const result = engine.validateTemplate(template);

    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  test("handles empty steps history", () => {
    const history = makeHistory([]);

    const template = engine.generateFromHistory(history, "Empty Task");

    expect(template.steps).toHaveLength(0);
    expect(template.params).toHaveLength(0);
    expect(template.metadata.source).toBe("auto-generated");
  });
});

// === findMatchingTemplate Tests ===

describe("TemplateEngine - findMatchingTemplate", () => {
  let engine: DefaultTemplateEngine;
  let tmpDir: string;

  beforeEach(async () => {
    engine = new DefaultTemplateEngine();
    tmpDir = await mkdtemp(join(tmpdir(), "te-match-"));
  });

  afterEach(async () => {
    await rm(tmpDir, { recursive: true, force: true });
  });

  test("returns undefined when no templates loaded", () => {
    expect(engine.findMatchingTemplate("open settings")).toBeUndefined();
  });

  test("returns undefined for empty query", () => {
    expect(engine.findMatchingTemplate("")).toBeUndefined();
    expect(engine.findMatchingTemplate("   ")).toBeUndefined();
  });

  test("matches by template name (Req 5b.5)", async () => {
    const t = makeValidTemplate({ name: "open-settings", description: "Opens the settings app" });
    await engine.saveTemplate(t, tmpDir);

    const match = engine.findMatchingTemplate("open settings");

    expect(match).toBeDefined();
    expect(match!.name).toBe("open-settings");
  });

  test("matches by template description", async () => {
    const t = makeValidTemplate({ name: "msg-template", description: "Send a WhatsApp message to a contact" });
    await engine.saveTemplate(t, tmpDir);

    const match = engine.findMatchingTemplate("send whatsapp message");

    expect(match).toBeDefined();
    expect(match!.name).toBe("msg-template");
  });

  test("matches by metadata.taskDescription", async () => {
    const t = makeValidTemplate({
      name: "auto-task",
      description: "Auto-generated",
      metadata: { createdAt: "2024-01-01T00:00:00Z", source: "auto-generated", taskDescription: "Order food delivery" },
    });
    await engine.saveTemplate(t, tmpDir);

    const match = engine.findMatchingTemplate("order food");

    expect(match).toBeDefined();
    expect(match!.name).toBe("auto-task");
  });

  test("returns best match when multiple templates exist", async () => {
    const t1 = makeValidTemplate({ name: "open-camera", description: "Opens the camera app" });
    const t2 = makeValidTemplate({ name: "open-settings", description: "Opens the settings app" });
    await engine.saveTemplate(t1, tmpDir);
    await engine.saveTemplate(t2, tmpDir);

    const match = engine.findMatchingTemplate("open settings app");

    expect(match).toBeDefined();
    expect(match!.name).toBe("open-settings");
  });

  test("returns undefined when no words match", async () => {
    const t = makeValidTemplate({ name: "open-camera", description: "Opens the camera" });
    await engine.saveTemplate(t, tmpDir);

    const match = engine.findMatchingTemplate("send message");

    expect(match).toBeUndefined();
  });
});
