/**
 * VisionAgent - 基于视觉语言模型的智能决策器
 *
 * 截图 → 发给 GLM-4.6V → 解析返回的操作指令 → 执行
 * 支持任意 App，不依赖 uiautomator
 */

import type { AdbClient } from "./adb-client";
import type { VisionClient } from "./vision-client";
import type { Action } from "./types";

export interface VisionAgentResult {
  success: boolean;
  action: Action | null;
  reasoning: string;
  done: boolean;       // 模型判断任务已完成
  error?: string;
}

export interface VisionAgent {
  decideNextAction(
    deviceId: string,
    goal: string,
    history: string[],
  ): Promise<VisionAgentResult>;
}

const SYSTEM_PROMPT = `你是手机自动化助手。看截图，返回下一步操作的JSON。

格式：{"reasoning": "思考", "done": false, "action": {"type": "tap", "x": 540, "y": 960}}

操作类型：
- tap: {"type":"tap","x":数字,"y":数字}
- input_text: {"type":"input_text","text":"文字"}
- swipe: {"type":"swipe","x1":起,"y1":起,"x2":终,"y2":终,"duration":毫秒}
- key_event: {"type":"key_event","keyCode":数字} (3=Home,4=返回,66=回车)
- wait: {"type":"wait","ms":毫秒}

完成时：{"reasoning":"完成原因","done":true,"action":null}

规则：坐标基于截图像素位置，每次只返回一个JSON操作，输入文字前先点击输入框。`;

/**
 * 解析模型返回的 JSON 操作指令
 */
export function parseVisionResponse(text: string): VisionAgentResult {
  // 尝试从文本中提取 JSON
  const jsonMatch = text.match(/\{[\s\S]*\}/);
  if (!jsonMatch) {
    return {
      success: false,
      action: null,
      reasoning: "Failed to parse model response",
      done: false,
      error: `No JSON found in response: ${text.slice(0, 200)}`,
    };
  }

  try {
    const parsed = JSON.parse(jsonMatch[0]);
    const reasoning = parsed.reasoning || "";
    const done = parsed.done === true;

    if (done || parsed.action === null) {
      return { success: true, action: null, reasoning, done: true };
    }

    const action = parsed.action as Action;
    if (!action || !action.type) {
      return {
        success: false,
        action: null,
        reasoning,
        done: false,
        error: "Invalid action format",
      };
    }

    return { success: true, action, reasoning, done: false };
  } catch (err) {
    return {
      success: false,
      action: null,
      reasoning: "",
      done: false,
      error: `JSON parse error: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}

/**
 * GlmVisionAgent - 使用 GLM-4.6V 视觉模型做决策
 * 支持预取截图（上一步执行操作时就开始截图）
 */
export class GlmVisionAgent implements VisionAgent {
  private prefetchedScreenshot: Promise<string> | null = null;

  constructor(
    private readonly adbClient: AdbClient,
    private readonly visionClient: VisionClient,
  ) {}

  /**
   * 预取下一张截图（在执行操作后立即调用）
   */
  prefetchScreenshot(deviceId: string): void {
    this.prefetchedScreenshot = this.adbClient.screenshot(deviceId).catch(() => "");
  }

  async decideNextAction(
    deviceId: string,
    goal: string,
    history: string[],
  ): Promise<VisionAgentResult> {
    try {
      // 1. 使用预取的截图，或者现场截图
      let base64: string;
      if (this.prefetchedScreenshot) {
        base64 = await this.prefetchedScreenshot;
        this.prefetchedScreenshot = null;
        // 如果预取失败，重新截图
        if (!base64) {
          base64 = await this.adbClient.screenshot(deviceId);
        }
      } else {
        base64 = await this.adbClient.screenshot(deviceId);
      }

      // 2. 构建提示词
      let userPrompt = `目标：${goal}\n\n`;
      if (history.length > 0) {
        userPrompt += `已执行的操作：\n${history.map((h, i) => `${i + 1}. ${h}`).join("\n")}\n\n`;
      }
      userPrompt += "请根据当前屏幕截图，决定下一步操作。只返回 JSON。";

      // 3. 调用视觉模型
      const result = await this.visionClient.analyzeImage(base64, `${SYSTEM_PROMPT}\n\n${userPrompt}`);

      if (!result.success) {
        return {
          success: false,
          action: null,
          reasoning: "",
          done: false,
          error: `Vision API error: ${result.error}`,
        };
      }

      // 4. 解析返回的操作
      return parseVisionResponse(result.description);
    } catch (err) {
      return {
        success: false,
        action: null,
        reasoning: "",
        done: false,
        error: err instanceof Error ? err.message : String(err),
      };
    }
  }
}
