import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { FileLogger, formatLogEntry, type LogEntry } from "../src/logger";
import { unlinkSync, existsSync } from "node:fs";

const TEST_LOG_FILE = "tests/test-logger.log";

describe("formatLogEntry", () => {
  test("produces valid JSON with all fields", () => {
    const entry: LogEntry = {
      timestamp: "2024-01-15T10:30:00.000Z",
      command: "list_devices",
      result: "success",
    };
    const output = formatLogEntry(entry);
    const parsed = JSON.parse(output);

    expect(parsed.timestamp).toBe("2024-01-15T10:30:00.000Z");
    expect(parsed.command).toBe("list_devices");
    expect(parsed.result).toBe("success");
  });

  test("handles special characters in command and result", () => {
    const entry: LogEntry = {
      timestamp: "2024-01-15T10:30:00.000Z",
      command: 'input_text "hello world"',
      result: '{"status":"error","message":"failed"}',
    };
    const output = formatLogEntry(entry);
    const parsed = JSON.parse(output);

    expect(parsed.command).toBe('input_text "hello world"');
    expect(parsed.result).toBe('{"status":"error","message":"failed"}');
  });
});

describe("FileLogger", () => {
  beforeEach(() => {
    if (existsSync(TEST_LOG_FILE)) {
      unlinkSync(TEST_LOG_FILE);
    }
  });

  afterEach(() => {
    if (existsSync(TEST_LOG_FILE)) {
      unlinkSync(TEST_LOG_FILE);
    }
  });

  test("creates log file and writes entry", async () => {
    const logger = new FileLogger(TEST_LOG_FILE);
    await logger.log("list_devices", "found 2 devices");

    const content = await Bun.file(TEST_LOG_FILE).text();
    const lines = content.trim().split("\n");
    expect(lines).toHaveLength(1);

    const entry = JSON.parse(lines[0]);
    expect(entry.command).toBe("list_devices");
    expect(entry.result).toBe("found 2 devices");
    expect(entry.timestamp).toBeTruthy();
    // Verify ISO format
    expect(new Date(entry.timestamp).toISOString()).toBe(entry.timestamp);
  });

  test("appends multiple entries", async () => {
    const logger = new FileLogger(TEST_LOG_FILE);
    await logger.log("get_screen", "ok");
    await logger.log("tap 100 200", "success");
    await logger.log("list_templates", "3 templates");

    const content = await Bun.file(TEST_LOG_FILE).text();
    const lines = content.trim().split("\n");
    expect(lines).toHaveLength(3);

    expect(JSON.parse(lines[0]).command).toBe("get_screen");
    expect(JSON.parse(lines[1]).command).toBe("tap 100 200");
    expect(JSON.parse(lines[2]).command).toBe("list_templates");
  });

  test("each entry has a valid ISO timestamp", async () => {
    const logger = new FileLogger(TEST_LOG_FILE);
    const before = new Date();
    await logger.log("test_cmd", "test_result");
    const after = new Date();

    const content = await Bun.file(TEST_LOG_FILE).text();
    const entry = JSON.parse(content.trim());
    const ts = new Date(entry.timestamp);

    expect(ts.getTime()).toBeGreaterThanOrEqual(before.getTime());
    expect(ts.getTime()).toBeLessThanOrEqual(after.getTime());
  });
});
