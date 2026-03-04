/**
 * midscene-client.ts — Midscene Android Agent 封装
 *
 * 提供 HTTP 服务，供 Python 后端调用 Midscene 的三大能力：
 * - aiAct(instruction)  — 自然语言驱动的 GUI 操作
 * - aiQuery(dataDemand) — 结构化数据提取
 * - aiAssert(assertion)  — 屏幕状态断言
 *
 * 运行方式: bun run src/midscene-client.ts
 * 默认端口: 9401 (MIDSCENE_SERVER_PORT)
 */

import { AndroidAgent, AndroidDevice } from "@midscene/android";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MidsceneConfig {
  port: number;
  adbPath?: string;
  remoteHost?: string;
  remotePort?: number;
}

interface TaskResult {
  success: boolean;
  data?: unknown;
  error?: string;
  durationMs?: number;
}

// ---------------------------------------------------------------------------
// Globals
// ---------------------------------------------------------------------------

let device: AndroidDevice | null = null;
let agent: AndroidAgent | null = null;

const config: MidsceneConfig = {
  port: parseInt(process.env.MIDSCENE_SERVER_PORT || "9401", 10),
  adbPath: process.env.MIDSCENE_ADB_PATH,
  remoteHost: process.env.MIDSCENE_ADB_REMOTE_HOST,
  remotePort: process.env.MIDSCENE_ADB_REMOTE_PORT
    ? parseInt(process.env.MIDSCENE_ADB_REMOTE_PORT, 10)
    : undefined,
};

// ---------------------------------------------------------------------------
// Device & Agent lifecycle
// ---------------------------------------------------------------------------

async function ensureAgent(): Promise<AndroidAgent> {
  if (agent) return agent;

  // AndroidDevice 需要 deviceId，空字符串表示使用默认设备
  const deviceId = process.env.MIDSCENE_DEVICE_ID || "";
  device = new AndroidDevice(deviceId);
  await device.connect();

  agent = new AndroidAgent(device, {
    aiActionContext:
      "这是一台 Android 手机，界面语言为中文。操作时优先识别中文文字。",
  });

  console.log("[midscene] Agent connected to device:", deviceId || "(default)");
  return agent;
}

async function destroyAgent(): Promise<void> {
  if (device) {
    await device.destroy();
    device = null;
    agent = null;
    console.log("[midscene] Agent disconnected");
  }
}

// ---------------------------------------------------------------------------
// Core operations
// ---------------------------------------------------------------------------

async function doAiAct(instruction: string): Promise<TaskResult> {
  const t0 = Date.now();
  try {
    const ag = await ensureAgent();
    await ag.aiAct(instruction);
    return { success: true, durationMs: Date.now() - t0 };
  } catch (e: any) {
    return { success: false, error: e.message, durationMs: Date.now() - t0 };
  }
}

async function doAiQuery(dataDemand: string): Promise<TaskResult> {
  const t0 = Date.now();
  try {
    const ag = await ensureAgent();
    const data = await ag.aiQuery(dataDemand);
    return { success: true, data, durationMs: Date.now() - t0 };
  } catch (e: any) {
    return { success: false, error: e.message, durationMs: Date.now() - t0 };
  }
}

async function doAiAssert(assertion: string): Promise<TaskResult> {
  const t0 = Date.now();
  try {
    const ag = await ensureAgent();
    await ag.aiAssert(assertion);
    return { success: true, data: { pass: true }, durationMs: Date.now() - t0 };
  } catch (e: any) {
    // aiAssert throws on failure
    return {
      success: true,
      data: { pass: false, reason: e.message },
      durationMs: Date.now() - t0,
    };
  }
}

async function doScreenshot(): Promise<TaskResult> {
  const t0 = Date.now();
  try {
    const ag = await ensureAgent();
    const screenshotBase64 = await ag.page.screenshotBase64();
    return {
      success: true,
      data: { screenshot: screenshotBase64 },
      durationMs: Date.now() - t0,
    };
  } catch (e: any) {
    return { success: false, error: e.message, durationMs: Date.now() - t0 };
  }
}

// ---------------------------------------------------------------------------
// HTTP Server (Bun native)
// ---------------------------------------------------------------------------

async function parseBody(req: Request): Promise<Record<string, any>> {
  try {
    return await req.json();
  } catch {
    return {};
  }
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const server = Bun.serve({
  port: config.port,
  async fetch(req) {
    const url = new URL(req.url);
    const path = url.pathname;

    // Health check
    if (path === "/health" && req.method === "GET") {
      return json({
        success: true,
        message: "Midscene service running",
        connected: !!agent,
      });
    }

    // Connect
    if (path === "/connect" && req.method === "POST") {
      try {
        await ensureAgent();
        return json({ success: true, message: "Connected" });
      } catch (e: any) {
        return json({ success: false, error: e.message }, 500);
      }
    }

    // Disconnect
    if (path === "/disconnect" && req.method === "POST") {
      await destroyAgent();
      return json({ success: true, message: "Disconnected" });
    }

    // aiAct
    if (path === "/ai/act" && req.method === "POST") {
      const body = await parseBody(req);
      if (!body.instruction) {
        return json({ success: false, error: "Missing 'instruction'" }, 400);
      }
      const result = await doAiAct(body.instruction);
      return json(result);
    }

    // aiQuery
    if (path === "/ai/query" && req.method === "POST") {
      const body = await parseBody(req);
      if (!body.dataDemand) {
        return json({ success: false, error: "Missing 'dataDemand'" }, 400);
      }
      const result = await doAiQuery(body.dataDemand);
      return json(result);
    }

    // aiAssert
    if (path === "/ai/assert" && req.method === "POST") {
      const body = await parseBody(req);
      if (!body.assertion) {
        return json({ success: false, error: "Missing 'assertion'" }, 400);
      }
      const result = await doAiAssert(body.assertion);
      return json(result);
    }

    // Screenshot
    if (path === "/screenshot" && req.method === "GET") {
      const result = await doScreenshot();
      return json(result);
    }

    return json({ success: false, error: "Not found" }, 404);
  },
});

console.log(`[midscene] HTTP server listening on http://localhost:${config.port}`);

// Graceful shutdown
process.on("SIGINT", async () => {
  console.log("[midscene] Shutting down...");
  await destroyAgent();
  process.exit(0);
});
