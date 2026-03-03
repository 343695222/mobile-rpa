import type { DeviceInfo } from "./types";

/**
 * ADB Client 接口 - 封装所有 ADB 命令调用
 * 通过接口定义支持依赖注入，便于测试时使用 Mock 实现
 */
export interface AdbClient {
  listDevices(): Promise<DeviceInfo[]>;
  isConnected(deviceId: string): Promise<boolean>;
  dumpUiHierarchy(deviceId: string): Promise<string>;
  screenshot(deviceId: string): Promise<string>; // 返回 base64 PNG
  tap(deviceId: string, x: number, y: number): Promise<void>;
  inputText(deviceId: string, text: string): Promise<void>;
  swipe(
    deviceId: string,
    x1: number,
    y1: number,
    x2: number,
    y2: number,
    durationMs: number
  ): Promise<void>;
  keyEvent(deviceId: string, keyCode: number): Promise<void>;
  shell(deviceId: string, command: string): Promise<string>;
}

/**
 * 执行 ADB 命令并返回 stdout 输出
 * 使用 Bun.spawn 执行外部进程
 */
async function execAdb(args: string[]): Promise<string> {
  const proc = Bun.spawn(["adb", ...args], {
    stdout: "pipe",
    stderr: "pipe",
  });

  const exitCode = await proc.exited;
  const stdout = await new Response(proc.stdout).text();
  const stderr = await new Response(proc.stderr).text();

  if (exitCode !== 0) {
    throw new Error(
      `ADB command failed (exit ${exitCode}): adb ${args.join(" ")}\n${stderr.trim()}`
    );
  }

  return stdout;
}

/**
 * 构建设备目标参数
 * 当指定 deviceId 时，在命令前添加 `-s deviceId`
 */
function deviceArgs(deviceId: string, args: string[]): string[] {
  return ["-s", deviceId, ...args];
}

/**
 * 解析 `adb devices -l` 输出，提取设备信息
 *
 * 输出格式示例：
 * ```
 * List of devices attached
 * emulator-5554          device product:sdk_gphone64_x86_64 model:sdk_gphone64_x86_64 transport_id:1
 * 192.168.1.100:5555     offline
 * ```
 */
/** @internal Exported for testing */
export function parseDeviceList(output: string): DeviceInfo[] {
  const lines = output.split("\n");
  const devices: DeviceInfo[] = [];

  for (const line of lines) {
    const trimmed = line.trim();
    // 跳过空行和标题行
    if (!trimmed || trimmed.startsWith("List of devices")) {
      continue;
    }

    // 格式: <serial> <status> [properties...]
    const match = trimmed.match(/^(\S+)\s+(device|offline|unauthorized)\b(.*)$/);
    if (!match) continue;

    const [, id, status, rest] = match;

    // 从属性中提取 model
    let model = "unknown";
    const modelMatch = rest.match(/model:(\S+)/);
    if (modelMatch) {
      model = modelMatch[1];
    }

    devices.push({
      id,
      model,
      status: status as DeviceInfo["status"],
    });
  }

  return devices;
}

/**
 * BunAdbClient - 使用 Bun.spawn 执行 ADB 命令的具体实现
 */
export class BunAdbClient implements AdbClient {
  async listDevices(): Promise<DeviceInfo[]> {
    const output = await execAdb(["devices", "-l"]);
    return parseDeviceList(output);
  }

  async isConnected(deviceId: string): Promise<boolean> {
    try {
      const devices = await this.listDevices();
      return devices.some((d) => d.id === deviceId && d.status === "device");
    } catch {
      return false;
    }
  }

  async dumpUiHierarchy(deviceId: string): Promise<string> {
      const remotePath = "/sdcard/window_dump.xml";
      // 先 dump 到手机文件，再 cat 读取内容（避免 /dev/tty 在远程隧道下丢失输出）
      await execAdb(
        deviceArgs(deviceId, ["shell", "uiautomator", "dump", remotePath])
      );
      const output = await execAdb(
        deviceArgs(deviceId, ["shell", "cat", remotePath])
      );

      const xmlMatch = output.match(/<\?xml[\s\S]*<\/hierarchy>/);
      if (xmlMatch) {
        return xmlMatch[0];
      }
      const hierarchyMatch = output.match(/<hierarchy[\s\S]*<\/hierarchy>/);
      if (hierarchyMatch) {
        return hierarchyMatch[0];
      }
      throw new Error(`Failed to extract UI hierarchy XML from output: ${output.slice(0, 200)}`);
    }


  async screenshot(deviceId: string): Promise<string> {
    // 直接通过 adb exec-out 流式获取截图，避免写文件再 pull 的两步开销
    const proc = Bun.spawn(
      ["adb", "-s", deviceId, "exec-out", "screencap", "-p"],
      { stdout: "pipe", stderr: "pipe" },
    );
    const exitCode = await proc.exited;
    const buffer = await new Response(proc.stdout).arrayBuffer();

    if (exitCode !== 0 || buffer.byteLength === 0) {
      // fallback: 用传统方式
      const remotePath = "/sdcard/screenshot_rpa.png";
      await execAdb(deviceArgs(deviceId, ["shell", "screencap", "-p", remotePath]));
      const tmpPath = "/tmp/screenshot_rpa.png";
      await execAdb(deviceArgs(deviceId, ["pull", remotePath, tmpPath]));
      const file = Bun.file(tmpPath);
      const fallbackBuffer = await file.arrayBuffer();
      return Buffer.from(fallbackBuffer).toString("base64");
    }

    return Buffer.from(buffer).toString("base64");
  }


  async tap(deviceId: string, x: number, y: number): Promise<void> {
    await execAdb(
      deviceArgs(deviceId, ["shell", "input", "tap", String(x), String(y)])
    );
  }

  async inputText(deviceId: string, text: string): Promise<void> {
    // ADB input text 需要对空格进行转义
    const escaped = text.replace(/ /g, "%s");
    await execAdb(
      deviceArgs(deviceId, ["shell", "input", "text", escaped])
    );
  }

  async swipe(
    deviceId: string,
    x1: number,
    y1: number,
    x2: number,
    y2: number,
    durationMs: number
  ): Promise<void> {
    await execAdb(
      deviceArgs(deviceId, [
        "shell", "input", "swipe",
        String(x1), String(y1), String(x2), String(y2), String(durationMs),
      ])
    );
  }

  async keyEvent(deviceId: string, keyCode: number): Promise<void> {
    await execAdb(
      deviceArgs(deviceId, ["shell", "input", "keyevent", String(keyCode)])
    );
  }

  async shell(deviceId: string, command: string): Promise<string> {
    return execAdb(deviceArgs(deviceId, ["shell", command]));
  }
}
