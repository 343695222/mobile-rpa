import type { AdbClient } from "./adb-client";
import type { ScreenParser } from "./screen-parser";
import type { ActionExecutor } from "./action-executor";
import type { TemplateEngine } from "./template-engine";
import type { RpaLoop } from "./rpa-loop";
import type { Logger } from "./logger";
import type { CommandType, ParsedCommand, SkillResponse } from "./types";
import { callU2, checkU2Health } from "./u2-proxy";
import { AutoXClient } from "./autox-client";

/**
 * SkillCli 接口 - 入口脚本，处理 OpenClaw Agent 的指令调用
 */
export interface SkillCli {
  handleCommand(input: string): Promise<SkillResponse>;
  routeCommand(command: ParsedCommand): Promise<SkillResponse>;
}

/** All supported command types */
const SUPPORTED_COMMANDS: CommandType[] = [
  "list_devices",
  "get_screen",
  "execute_action",
  "run_template",
  "run_task",
  "list_templates",
  "screenshot",
  "analyze_screen",
  "smart_task",
  "collect_data",
  "list_scripts",
  "validate_scripts",
  "autox_execute",
  "open_app",
  "go_back",
  "go_home",
  "scroll_up",
  "scroll_down",
  "get_current_app",
  "wake_screen",
  "lock_screen",
  // 安全守卫
  "safety_rules",
  "safety_log",
  "safety_pending",
  "safety_confirm",
  "safety_mode",
  "safety_set_mode",
  // 平台分析
  "analyze_platform",
  "traffic_start",
  "traffic_stop",
  "traffic_records",
  "traffic_load_har",
  // AutoJS 直连模式
  "autox_health",
  "autox_device_info",
  "autox_screenshot",
  "autox_click",
  "autox_long_click",
  "autox_swipe",
  "autox_scroll",
  "autox_input",
  "autox_key",
  "autox_app_start",
  "autox_app_stop",
  "autox_app_current",
  "autox_find_element",
  "autox_click_element",
  "autox_ui_tree",
  "autox_ocr",
  "autox_clipboard",
  "autox_smart_task",
];

/**
 * Parse a raw JSON input string into a ParsedCommand.
 * Returns the parsed command or throws an Error with a descriptive message.
 */
export function parseInput(input: string): ParsedCommand {
  const obj = JSON.parse(input);

  if (typeof obj !== "object" || obj === null || Array.isArray(obj)) {
    throw new Error("Input must be a JSON object");
  }

  const type = obj.type as string | undefined;
  if (!type || !SUPPORTED_COMMANDS.includes(type as CommandType)) {
    throw new Error(
      `Unknown command type: "${type ?? ""}". Supported commands: ${SUPPORTED_COMMANDS.join(", ")}`,
    );
  }

  return {
    type: type as CommandType,
    deviceId: obj.deviceId,
    action: obj.action,
    templateName: obj.templateName,
    templateParams: obj.templateParams,
    taskGoal: obj.taskGoal,
    prompt: obj.prompt,
    packageName: obj.packageName,
    app: obj.app,
    dataType: obj.dataType ?? obj.data_type,
    query: obj.query,
    forceStrategy: obj.forceStrategy ?? obj.force_strategy,
    script: obj.script,
    confirmId: obj.confirmId ?? obj.confirm_id,
    approved: obj.approved,
    safetyMode: obj.safetyMode ?? obj.safety_mode ?? obj.mode,
    platformName: obj.platformName ?? obj.platform_name,
    appPackage: obj.appPackage ?? obj.app_package,
    domainFilter: obj.domainFilter ?? obj.domain_filter,
    harFile: obj.harFile ?? obj.har_file,
    // AutoJS 直连模式参数
    x: obj.x,
    y: obj.y,
    x1: obj.x1,
    y1: obj.y1,
    x2: obj.x2,
    y2: obj.y2,
    duration: obj.duration,
    direction: obj.direction,
    text: obj.text,
    key: obj.key,
    by: obj.by,
    value: obj.value,
    timeout: obj.timeout,
    maxDepth: obj.maxDepth ?? obj.max_depth,
    maxSteps: obj.maxSteps ?? obj.max_steps,
  };
}

/**
 * DefaultSkillCli - SkillCli 的具体实现
 *
 * 通过构造函数注入所有依赖，支持测试时使用 Mock 实现。
 * 所有指令执行结果以统一 JSON 格式返回 (status, message, data)。
 */
export class DefaultSkillCli implements SkillCli {
  constructor(
    private readonly adbClient: AdbClient,
    private readonly screenParser: ScreenParser,
    private readonly actionExecutor: ActionExecutor,
    private readonly templateEngine: TemplateEngine,
    private readonly rpaLoop: RpaLoop,
    private readonly logger: Logger,
  ) {}

  async handleCommand(input: string): Promise<SkillResponse> {
    let command: ParsedCommand;
    try {
      command = parseInput(input);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await this.logger.log(input, `error: ${message}`);
      return { status: "error", message };
    }

    const response = await this.routeCommand(command);
    await this.logger.log(JSON.stringify(command), `${response.status}: ${response.message}`);
    return response;
  }

  async routeCommand(command: ParsedCommand): Promise<SkillResponse> {
    try {
      switch (command.type) {
        case "list_devices":
          return await this.handleListDevices();

        case "get_screen":
          return await this.handleGetScreen(command.deviceId);

        case "execute_action":
          return await this.handleExecuteAction(command.deviceId, command.action);

        case "run_template":
          return await this.handleRunTemplate(
            command.deviceId,
            command.templateName,
            command.templateParams,
          );

        case "run_task":
          return await this.handleRunTask(command.deviceId, command.taskGoal);

        case "list_templates":
          return await this.handleListTemplates();

        case "screenshot":
          return await this.handleScreenshot(command.deviceId);

        case "analyze_screen":
          return await this.handleAnalyzeScreen(command.deviceId, command.prompt);

        case "smart_task":
          return await this.handleSmartTask(command.deviceId, command.taskGoal);

        case "collect_data":
          return await this.handleCollectData(command.deviceId, command.app, command.dataType, command.query, command.forceStrategy);

        case "list_scripts":
          return await this.handleListScripts();

        case "validate_scripts":
          return await this.handleValidateScripts(command.deviceId);

        case "autox_execute":
          return await this.handleAutoxExecute(command.script);

        case "open_app":
          return await this.handleOpenApp(command.deviceId, command.packageName);

        case "go_back":
          return await this.handleSimpleAction(command.deviceId, { type: "go_back" }, "Pressed back");

        case "go_home":
          return await this.handleSimpleAction(command.deviceId, { type: "go_home" }, "Pressed home");

        case "scroll_up":
          return await this.handleSimpleAction(command.deviceId, { type: "scroll_up" }, "Scrolled up");

        case "scroll_down":
          return await this.handleSimpleAction(command.deviceId, { type: "scroll_down" }, "Scrolled down");

        case "get_current_app":
          return await this.handleGetCurrentApp(command.deviceId);

        case "wake_screen":
          return await this.handleSimpleAction(command.deviceId, { type: "wake_screen" }, "Screen woken up");

        case "lock_screen":
          return await this.handleSimpleAction(command.deviceId, { type: "lock_screen" }, "Screen locked");

        // === 安全守卫 ===
        case "safety_rules":
          return await this.handleSafetyProxy("GET", "/safety/rules");

        case "safety_log":
          return await this.handleSafetyProxy("GET", "/safety/log");

        case "safety_pending":
          return await this.handleSafetyProxy("GET", "/safety/pending");

        case "safety_confirm":
          return await this.handleSafetyConfirm(command.confirmId, command.approved);

        case "safety_mode":
          return await this.handleSafetyProxy("GET", "/safety/mode");

        case "safety_set_mode":
          return await this.handleSafetySetMode(command.safetyMode);

        // === 平台分析 ===
        case "analyze_platform":
          return await this.handleAnalyzePlatform(command);

        case "traffic_start":
          return await this.handleTrafficStart(command);

        case "traffic_stop":
          return await this.handleSafetyProxy("POST", "/traffic/stop");

        case "traffic_records":
          return await this.handleSafetyProxy("GET", "/traffic/records");

        case "traffic_load_har":
          return await this.handleTrafficLoadHar(command);

        // === AutoJS 直连模式 ===
        case "autox_health":
          return await this.handleAutoxHealth();

        case "autox_device_info":
          return await this.handleAutoxDeviceInfo();

        case "autox_screenshot":
          return await this.handleAutoxScreenshot();

        case "autox_click":
          return await this.handleAutoxClick(command.x, command.y);

        case "autox_long_click":
          return await this.handleAutoxLongClick(command.x, command.y, command.duration);

        case "autox_swipe":
          return await this.handleAutoxSwipe(command.x1, command.y1, command.x2, command.y2, command.duration);

        case "autox_scroll":
          return await this.handleAutoxScroll(command.direction);

        case "autox_input":
          return await this.handleAutoxInput(command.text);

        case "autox_key":
          return await this.handleAutoxKey(command.key);

        case "autox_app_start":
          return await this.handleAutoxAppStart(command.packageName);

        case "autox_app_stop":
          return await this.handleAutoxAppStop(command.packageName);

        case "autox_app_current":
          return await this.handleAutoxAppCurrent();

        case "autox_find_element":
          return await this.handleAutoxFindElement(command.by, command.value, command.timeout);

        case "autox_click_element":
          return await this.handleAutoxClickElement(command.by, command.value, command.timeout);

        case "autox_ui_tree":
          return await this.handleAutoxUiTree(command.maxDepth);

        case "autox_ocr":
          return await this.handleAutoxOcr();

        case "autox_clipboard":
          return await this.handleAutoxClipboard(command.text);

        case "autox_smart_task":
          return await this.handleAutoxSmartTask(command.taskGoal, command.maxSteps);

        default: {
          // Exhaustive check — should never reach here since parseInput validates
          const _exhaustive: never = command.type;
          return {
            status: "error",
            message: `Unknown command type: ${command.type}. Supported commands: ${SUPPORTED_COMMANDS.join(", ")}`,
          };
        }
      }
    } catch (err) {
      return {
        status: "error",
        message: err instanceof Error ? err.message : String(err),
      };
    }
  }

  private async handleListDevices(): Promise<SkillResponse> {
    const devices = await this.adbClient.listDevices();
    return {
      status: "success",
      message: `Found ${devices.length} device(s)`,
      data: devices,
    };
  }

  private async handleGetScreen(deviceId?: string): Promise<SkillResponse> {
    if (!deviceId) {
      return { status: "error", message: "deviceId is required for get_screen" };
    }
    const screenState = await this.screenParser.captureScreen(deviceId);
    return {
      status: "success",
      message: `Captured ${screenState.elements.length} UI elements`,
      data: screenState,
    };
  }

  private async handleExecuteAction(deviceId?: string, action?: unknown): Promise<SkillResponse> {
    if (!deviceId) {
      return { status: "error", message: "deviceId is required for execute_action" };
    }
    if (!action) {
      return { status: "error", message: "action is required for execute_action" };
    }
    const result = await this.actionExecutor.execute(deviceId, action as any);
    return {
      status: result.success ? "success" : "error",
      message: result.success
        ? `Action ${result.action.type} executed successfully`
        : `Action failed: ${result.error}`,
      data: result,
    };
  }

  private async handleRunTemplate(
    deviceId?: string,
    templateName?: string,
    templateParams?: Record<string, string>,
  ): Promise<SkillResponse> {
    if (!deviceId) {
      return { status: "error", message: "deviceId is required for run_template" };
    }
    if (!templateName) {
      return { status: "error", message: "templateName is required for run_template" };
    }

    const template = this.templateEngine.getTemplate(templateName);
    if (!template) {
      return { status: "error", message: `Template not found: ${templateName}` };
    }

    const resolved = this.templateEngine.resolveParams(template, templateParams ?? {});
    const result = await this.rpaLoop.runTemplate(deviceId, resolved);
    return {
      status: result.success ? "success" : "error",
      message: result.message,
      data: result,
    };
  }

  private async handleRunTask(deviceId?: string, taskGoal?: string): Promise<SkillResponse> {
    if (!deviceId) {
      return { status: "error", message: "deviceId is required for run_task" };
    }
    if (!taskGoal) {
      return { status: "error", message: "taskGoal is required for run_task" };
    }

    // 混合方案：先尝试匹配模板，有模板则 Skill 内部驱动执行
    const matchingTemplate = this.templateEngine.findMatchingTemplate(taskGoal);
    if (matchingTemplate) {
      const resolved = this.templateEngine.resolveParams(matchingTemplate, {});
      const result = await this.rpaLoop.runTemplate(deviceId, resolved);
      return {
        status: result.success ? "success" : "error",
        message: result.message,
        data: result,
      };
    }

    // 无匹配模板：引导 Agent 使用逐步调用模式
    return {
      status: "success",
      message: "No matching template found. Please use step-by-step mode: 1) call get_screen to observe the current screen, 2) decide the next action, 3) call execute_action to perform it, 4) repeat until the task is done. After completing the task, you can call save_history to generate a reusable template.",
      data: {
        mode: "step-by-step",
        taskGoal,
        deviceId,
        availableCommands: ["get_screen", "execute_action", "list_templates"],
      },
    };
  }

  private async handleListTemplates(): Promise<SkillResponse> {
    const templates = this.templateEngine.listTemplates();
    return {
      status: "success",
      message: `Found ${templates.length} template(s)`,
      data: templates,
    };
  }

  private async handleScreenshot(deviceId?: string): Promise<SkillResponse> {
    if (!deviceId) {
      return { status: "error", message: "deviceId is required for screenshot" };
    }
    const base64 = await this.adbClient.screenshot(deviceId);
    return {
      status: "success",
      message: "Screenshot captured",
      data: { base64, format: "png", length: base64.length },
    };
  }

  private async handleAnalyzeScreen(deviceId?: string, prompt?: string): Promise<SkillResponse> {
    if (!deviceId) {
      return { status: "error", message: "deviceId is required for analyze_screen" };
    }

    // 通过 Python U2 服务代理视觉分析（DashScope 百炼平台）
    const result = await callU2("/vision/analyze", {
      device_id: deviceId,
      prompt: prompt || "请详细描述这个手机屏幕上的内容，包括所有可见的文字、按钮、图标和界面元素。",
    });

    return {
      status: result.success ? "success" : "error",
      message: result.success ? "Screen analyzed" : (result.message || "Vision analysis failed"),
      data: result.data,
    };
  }

  private async handleSmartTask(deviceId?: string, taskGoal?: string): Promise<SkillResponse> {
    if (!deviceId) {
      return { status: "error", message: "deviceId is required for smart_task" };
    }
    if (!taskGoal) {
      return { status: "error", message: "taskGoal is required for smart_task" };
    }

    // 通过 Python U2 服务代理智能任务（DashScope 百炼平台 GUI-Plus 模型）
    const result = await callU2("/vision/smart_task", {
      device_id: deviceId,
      goal: taskGoal,
      max_steps: 20,
    });

    return {
      status: result.success ? "success" : "error",
      message: result.message,
      data: result.data,
    };
  }

  // === 便捷操作指令 ===

  private async handleOpenApp(deviceId?: string, packageName?: string): Promise<SkillResponse> {
    if (!deviceId) return { status: "error", message: "deviceId is required for open_app" };
    if (!packageName) return { status: "error", message: "packageName is required for open_app" };
    const result = await this.actionExecutor.execute(deviceId, { type: "open_app", packageName });
    return {
      status: result.success ? "success" : "error",
      message: result.success ? `Opened app: ${packageName}` : `Failed to open app: ${result.error}`,
      data: result,
    };
  }

  private async handleSimpleAction(deviceId: string | undefined, action: any, successMsg: string): Promise<SkillResponse> {
    if (!deviceId) return { status: "error", message: "deviceId is required" };
    const result = await this.actionExecutor.execute(deviceId, action);
    return {
      status: result.success ? "success" : "error",
      message: result.success ? successMsg : `Action failed: ${result.error}`,
      data: result,
    };
  }

  private async handleGetCurrentApp(deviceId?: string): Promise<SkillResponse> {
    if (!deviceId) return { status: "error", message: "deviceId is required for get_current_app" };
    try {
      const output = await this.adbClient.shell(deviceId, "dumpsys activity activities | grep mResumedActivity");
      const match = output.match(/u0\s+(\S+)\/(\S+)/);
      if (match) {
        return {
          status: "success",
          message: `Current app: ${match[1]}`,
          data: { packageName: match[1], activity: match[2], raw: output.trim() },
        };
      }
      return {
        status: "success",
        message: "Current app info retrieved",
        data: { raw: output.trim() },
      };
    } catch (err) {
      return { status: "error", message: err instanceof Error ? err.message : String(err) };
    }
  }

  // === 数据采集指令 ===

  private async handleCollectData(
    deviceId?: string,
    app?: string,
    dataType?: string,
    query?: string,
    forceStrategy?: string,
  ): Promise<SkillResponse> {
    if (!deviceId) return { status: "error", message: "deviceId is required for collect_data" };
    if (!app) return { status: "error", message: "app is required for collect_data" };
    if (!dataType) return { status: "error", message: "dataType is required for collect_data" };

    const result = await callU2("/collect", {
      device_id: deviceId,
      app,
      data_type: dataType,
      query: query ?? "",
      force_strategy: forceStrategy ?? null,
    });

    return {
      status: result.success ? "success" : "error",
      message: result.message,
      data: result.data,
    };
  }

  private async handleListScripts(): Promise<SkillResponse> {
    const result = await callU2("/scripts");
    return {
      status: result.success ? "success" : "error",
      message: result.message,
      data: result.data,
    };
  }

  private async handleValidateScripts(deviceId?: string): Promise<SkillResponse> {
    if (!deviceId) return { status: "error", message: "deviceId is required for validate_scripts" };

    const result = await callU2("/scripts/validate", { device_id: deviceId });
    return {
      status: result.success ? "success" : "error",
      message: result.message,
      data: result.data,
    };
  }

  // === AutoX 指令 ===

  private async handleAutoxExecute(script?: string): Promise<SkillResponse> {
    if (!script) return { status: "error", message: "script is required for autox_execute" };

    const autox = new AutoXClient();
    const result = await autox.runScript(script);
    return {
      status: result.success ? "success" : "error",
      message: result.success ? "Script executed" : (result.error ?? "AutoX execution failed"),
      data: result.data,
    };
  }

  // === 安全守卫指令 ===

  private async handleSafetyProxy(method: string, path: string): Promise<SkillResponse> {
    if (method === "GET") {
      const result = await callU2(path);
      return { status: result.success ? "success" : "error", message: result.message, data: result.data };
    }
    const result = await callU2(path, {});
    return { status: result.success ? "success" : "error", message: result.message, data: result.data };
  }

  private async handleSafetyConfirm(confirmId?: string, approved?: boolean): Promise<SkillResponse> {
    if (!confirmId) return { status: "error", message: "confirmId is required for safety_confirm" };
    if (approved === undefined) return { status: "error", message: "approved (true/false) is required for safety_confirm" };
    const result = await callU2("/safety/confirm", { confirm_id: confirmId, approved });
    return { status: result.success ? "success" : "error", message: result.message, data: result.data };
  }

  private async handleSafetySetMode(mode?: string): Promise<SkillResponse> {
    if (!mode) return { status: "error", message: "safetyMode is required for safety_set_mode" };
    if (!["strict", "permissive", "observe_only"].includes(mode)) {
      return { status: "error", message: `Invalid safety mode: ${mode}. Must be: strict, permissive, observe_only` };
    }
    const result = await callU2("/safety/mode", { mode });
    return { status: result.success ? "success" : "error", message: result.message, data: result.data };
  }

  // === 平台分析指令 ===

  private async handleAnalyzePlatform(command: ParsedCommand): Promise<SkillResponse> {
    if (!command.deviceId) return { status: "error", message: "deviceId is required for analyze_platform" };
    if (!command.platformName) return { status: "error", message: "platformName is required for analyze_platform" };
    const result = await callU2("/analyze/platform", {
      device_id: command.deviceId,
      platform_name: command.platformName,
      app_package: command.appPackage || "",
      domain_filter: command.domainFilter || [],
      har_file: command.harFile || null,
    });
    return { status: result.success ? "success" : "error", message: result.message, data: result.data };
  }

  private async handleTrafficStart(command: ParsedCommand): Promise<SkillResponse> {
    if (!command.platformName) return { status: "error", message: "platformName is required for traffic_start" };
    const result = await callU2("/traffic/start", {
      platform_name: command.platformName,
      domain_filter: command.domainFilter || [],
    });
    return { status: result.success ? "success" : "error", message: result.message, data: result.data };
  }

  private async handleTrafficLoadHar(command: ParsedCommand): Promise<SkillResponse> {
    if (!command.harFile) return { status: "error", message: "harFile is required for traffic_load_har" };
    const result = await callU2("/traffic/load_har", { har_file: command.harFile });
    return { status: result.success ? "success" : "error", message: result.message, data: result.data };
  }

  // === AutoJS 直连模式处理方法 ===

  private getAutoxClient(): AutoXClient {
    return new AutoXClient();
  }

  private async handleAutoxHealth(): Promise<SkillResponse> {
    const autox = this.getAutoxClient();
    const result = await autox.getHealth();
    if (!result.success) {
      return { status: "error", message: result.error ?? "AutoJS service unavailable" };
    }
    return { status: "success", message: "AutoJS service running", data: result.data };
  }

  private async handleAutoxDeviceInfo(): Promise<SkillResponse> {
    const autox = this.getAutoxClient();
    const result = await autox.getDeviceInfo();
    if (!result.success) {
      return { status: "error", message: result.error ?? "Failed to get device info" };
    }
    return { status: "success", message: "Device info retrieved", data: result.data };
  }

  private async handleAutoxScreenshot(): Promise<SkillResponse> {
    const autox = this.getAutoxClient();
    const result = await autox.screenshot();
    if (!result.success) {
      return { status: "error", message: result.error ?? "Screenshot failed" };
    }
    return { status: "success", message: "Screenshot captured", data: result.data };
  }

  private async handleAutoxClick(x?: number, y?: number): Promise<SkillResponse> {
    if (x === undefined || y === undefined) {
      return { status: "error", message: "x and y are required for autox_click" };
    }
    const autox = this.getAutoxClient();
    const result = await autox.click(x, y);
    if (!result.success) {
      return { status: "error", message: result.error ?? "Click failed" };
    }
    return { status: "success", message: `Clicked (${x}, ${y})`, data: result.data };
  }

  private async handleAutoxLongClick(x?: number, y?: number, duration?: number): Promise<SkillResponse> {
    if (x === undefined || y === undefined) {
      return { status: "error", message: "x and y are required for autox_long_click" };
    }
    const autox = this.getAutoxClient();
    const result = await autox.longClick(x, y, duration ?? 500);
    if (!result.success) {
      return { status: "error", message: result.error ?? "Long click failed" };
    }
    return { status: "success", message: `Long clicked (${x}, ${y})`, data: result.data };
  }

  private async handleAutoxSwipe(x1?: number, y1?: number, x2?: number, y2?: number, duration?: number): Promise<SkillResponse> {
    if (x1 === undefined || y1 === undefined || x2 === undefined || y2 === undefined) {
      return { status: "error", message: "x1, y1, x2, y2 are required for autox_swipe" };
    }
    const autox = this.getAutoxClient();
    const result = await autox.swipe(x1, y1, x2, y2, duration ?? 500);
    if (!result.success) {
      return { status: "error", message: result.error ?? "Swipe failed" };
    }
    return { status: "success", message: `Swiped (${x1},${y1}) -> (${x2},${y2})`, data: result.data };
  }

  private async handleAutoxScroll(direction?: "up" | "down"): Promise<SkillResponse> {
    const autox = this.getAutoxClient();
    const result = await autox.scroll(direction ?? "down");
    if (!result.success) {
      return { status: "error", message: result.error ?? "Scroll failed" };
    }
    return { status: "success", message: `Scrolled ${direction ?? "down"}`, data: result.data };
  }

  private async handleAutoxInput(text?: string): Promise<SkillResponse> {
    if (!text) {
      return { status: "error", message: "text is required for autox_input" };
    }
    const autox = this.getAutoxClient();
    const result = await autox.inputText(text);
    if (!result.success) {
      return { status: "error", message: result.error ?? "Input failed" };
    }
    return { status: "success", message: "Text input sent", data: result.data };
  }

  private async handleAutoxKey(key?: "back" | "home" | "recents" | "power"): Promise<SkillResponse> {
    const autox = this.getAutoxClient();
    const result = await autox.pressKey(key ?? "back");
    if (!result.success) {
      return { status: "error", message: result.error ?? "Key press failed" };
    }
    return { status: "success", message: `Pressed ${key ?? "back"}`, data: result.data };
  }

  private async handleAutoxAppStart(packageName?: string): Promise<SkillResponse> {
    if (!packageName) {
      return { status: "error", message: "packageName is required for autox_app_start" };
    }
    const autox = this.getAutoxClient();
    const result = await autox.appStart(packageName);
    if (!result.success) {
      return { status: "error", message: result.error ?? "App start failed" };
    }
    return { status: "success", message: `Started ${packageName}`, data: result.data };
  }

  private async handleAutoxAppStop(packageName?: string): Promise<SkillResponse> {
    if (!packageName) {
      return { status: "error", message: "packageName is required for autox_app_stop" };
    }
    const autox = this.getAutoxClient();
    const result = await autox.appStop(packageName);
    if (!result.success) {
      return { status: "error", message: result.error ?? "App stop failed" };
    }
    return { status: "success", message: `Stopped ${packageName}`, data: result.data };
  }

  private async handleAutoxAppCurrent(): Promise<SkillResponse> {
    const autox = this.getAutoxClient();
    const result = await autox.appCurrent();
    if (!result.success) {
      return { status: "error", message: result.error ?? "Failed to get current app" };
    }
    return { status: "success", message: "Current app retrieved", data: result.data };
  }

  private async handleAutoxFindElement(by?: string, value?: string, timeout?: number): Promise<SkillResponse> {
    if (!by || !value) {
      return { status: "error", message: "by and value are required for autox_find_element" };
    }
    const autox = this.getAutoxClient();
    const element = await autox.findElement({ by: by as any, value }, timeout ?? 3000);
    if (element) {
      return { status: "success", message: "Element found", data: element };
    }
    return { status: "success", message: "Element not found", data: null };
  }

  private async handleAutoxClickElement(by?: string, value?: string, timeout?: number): Promise<SkillResponse> {
    if (!by || !value) {
      return { status: "error", message: "by and value are required for autox_click_element" };
    }
    const autox = this.getAutoxClient();
    const clicked = await autox.clickElement({ by: by as any, value }, timeout ?? 3000);
    if (clicked) {
      return { status: "success", message: "Element clicked", data: { clicked: true } };
    }
    return { status: "error", message: "Element not found or click failed", data: { clicked: false } };
  }

  private async handleAutoxUiTree(maxDepth?: number): Promise<SkillResponse> {
    const autox = this.getAutoxClient();
    const result = await autox.uiTree(maxDepth ?? 3);
    if (!result.success) {
      return { status: "error", message: result.error ?? "Failed to get UI tree" };
    }
    return { status: "success", message: "UI tree retrieved", data: result.data };
  }

  private async handleAutoxOcr(): Promise<SkillResponse> {
    const autox = this.getAutoxClient();
    const texts = await autox.ocr();
    return { status: "success", message: `Found ${texts.length} texts`, data: texts };
  }

  private async handleAutoxClipboard(text?: string): Promise<SkillResponse> {
    const autox = this.getAutoxClient();
    if (text !== undefined) {
      const result = await autox.setClipboard(text);
      if (!result.success) {
        return { status: "error", message: result.error ?? "Failed to set clipboard" };
      }
      return { status: "success", message: "Clipboard set", data: { text } };
    }
    const clipText = await autox.getClipboard();
    return { status: "success", message: "Clipboard read", data: { text: clipText } };
  }

  private async handleAutoxSmartTask(taskGoal?: string, maxSteps?: number): Promise<SkillResponse> {
    if (!taskGoal) {
      return { status: "error", message: "taskGoal is required for autox_smart_task" };
    }
    // 调用 Python 服务的 smart_task 端点
    const result = await callU2("/vision/smart_task", {
      goal: taskGoal,
      max_steps: maxSteps ?? 20,
    });
    return { status: result.success ? "success" : "error", message: result.message, data: result.data };
  }
}


// === CLI Entry Point ===

/**
 * main() reads a single JSON command from stdin, creates real instances,
 * calls handleCommand, and prints the JSON response to stdout.
 */
async function main(): Promise<void> {
  const { BunAdbClient } = await import("./adb-client");
  const { DefaultScreenParser } = await import("./screen-parser");
  const { DefaultActionExecutor } = await import("./action-executor");
  const { DefaultTemplateEngine } = await import("./template-engine");
  const { DefaultRpaLoop } = await import("./rpa-loop");
  const { FileLogger } = await import("./logger");
  const adbClient = new BunAdbClient();
  const screenParser = new DefaultScreenParser(adbClient);
  const actionExecutor = new DefaultActionExecutor(adbClient, screenParser);
  const templateEngine = new DefaultTemplateEngine();
  const logger = new FileLogger("skill.log");

  // Load templates from the templates directory
  await templateEngine.loadTemplates("templates");

  // 混合方案：不提供 decideAction，自由探索由 Agent 逐步调用驱动
  const rpaLoop = new DefaultRpaLoop(screenParser, actionExecutor, templateEngine);

  // 视觉分析和智能任务现在全部通过 Python U2 服务代理（DashScope 百炼平台）
  // 不再需要 TypeScript 侧的 VisionClient/VisionAgent
  const cli = new DefaultSkillCli(
    adbClient,
    screenParser,
    actionExecutor,
    templateEngine,
    rpaLoop,
    logger,
  );

  // Read all stdin
  const input = await new Response(Bun.stdin.stream()).text();
  const response = await cli.handleCommand(input.trim());
  console.log(JSON.stringify(response, null, 2));
}

// Run main when executed directly
const isMainModule = typeof Bun !== "undefined" && Bun.main === import.meta.path;
if (isMainModule) {
  main().catch((err) => {
    console.error(JSON.stringify({ status: "error", message: String(err) }));
    process.exit(1);
  });
}
