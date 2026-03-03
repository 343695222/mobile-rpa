/**
 * VisionClient - 调用 GLM-4.6V 视觉模型分析图片
 * 支持流式和非流式两种模式
 */

export interface VisionAnalysisResult {
  success: boolean;
  description: string;
  model: string;
  error?: string;
}

export interface VisionClient {
  analyzeImage(base64Image: string, prompt: string): Promise<VisionAnalysisResult>;
  analyzeImageStream(base64Image: string, prompt: string, onChunk: (text: string) => void): Promise<VisionAnalysisResult>;
  analyzeImageParallel(base64Image: string, prompts: string[]): Promise<VisionAnalysisResult>;
}

/**
 * 从 SSE 流中逐块读取文本，拼接 content 字段
 * onChunk 回调可选：每收到一段文本就立即回调（用于流式输出到终端）
 */
async function readStream(response: Response, onChunk?: (text: string) => void): Promise<string> {
  const reader = response.body?.getReader();
  if (!reader) return "";

  const decoder = new TextDecoder();
  let content = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value, { stream: true });
    // SSE 格式: data: {...}\n\n
    const lines = chunk.split("\n");
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      const jsonStr = trimmed.slice(5).trim();
      if (jsonStr === "[DONE]") continue;

      try {
        const parsed = JSON.parse(jsonStr);
        const delta = parsed.choices?.[0]?.delta?.content ?? "";
        if (delta) {
          content += delta;
          onChunk?.(delta);
        }
      } catch {
        // 忽略解析失败的行
      }
    }
  }

  return content;
}

/**
 * GLM-4.6V 视觉模型客户端
 * 使用流式调用，边生成边接收，减少等待时间
 */
export class GlmVisionClient implements VisionClient {
  private readonly apiKey: string;
  private readonly model: string;
  private readonly baseUrl = "https://open.bigmodel.cn/api/paas/v4/chat/completions";

  constructor(apiKey: string, model = "glm-4.6v") {
    this.apiKey = apiKey;
    this.model = model;
  }

  async analyzeImage(base64Image: string, prompt: string): Promise<VisionAnalysisResult> {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 120_000);

      const response = await fetch(this.baseUrl, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${this.apiKey}`,
          "Content-Type": "application/json",
        },
        signal: controller.signal,
        body: JSON.stringify({
          model: this.model,
          max_tokens: 500,
          stream: true,
          messages: [
            {
              role: "user",
              content: [
                {
                  type: "image_url",
                  image_url: { url: base64Image },
                },
                {
                  type: "text",
                  text: prompt,
                },
              ],
            },
          ],
        }),
      });

      clearTimeout(timeout);

      if (!response.ok) {
        const errText = await response.text();
        return {
          success: false,
          description: "",
          model: this.model,
          error: `API error ${response.status}: ${errText.slice(0, 500)}`,
        };
      }

      const content = await readStream(response);

      return {
        success: true,
        description: content,
        model: this.model,
      };
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return {
        success: false,
        description: "",
        model: this.model,
        error: message.includes("abort") ? "API request timeout (120s)" : message,
      };
    }
  }

  /**
   * 流式分析：边接收边通过 onChunk 回调输出，适合终端实时显示
   */
  async analyzeImageStream(
    base64Image: string,
    prompt: string,
    onChunk: (text: string) => void,
  ): Promise<VisionAnalysisResult> {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 120_000);

      const response = await fetch(this.baseUrl, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${this.apiKey}`,
          "Content-Type": "application/json",
        },
        signal: controller.signal,
        body: JSON.stringify({
          model: this.model,
          max_tokens: 500,
          stream: true,
          messages: [
            {
              role: "user",
              content: [
                { type: "image_url", image_url: { url: base64Image } },
                { type: "text", text: prompt },
              ],
            },
          ],
        }),
      });

      clearTimeout(timeout);

      if (!response.ok) {
        const errText = await response.text();
        return {
          success: false,
          description: "",
          model: this.model,
          error: `API error ${response.status}: ${errText.slice(0, 500)}`,
        };
      }

      const content = await readStream(response, onChunk);

      return { success: true, description: content, model: this.model };
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return {
        success: false,
        description: "",
        model: this.model,
        error: message.includes("abort") ? "API request timeout (120s)" : message,
      };
    }
  }

  /**
   * 并行分析：同一张图发多个不同 prompt，并行请求，合并结果
   * 用于加速 smart_task（同时问"屏幕上有什么"和"下一步该怎么做"）
   */
  async analyzeImageParallel(base64Image: string, prompts: string[]): Promise<VisionAnalysisResult> {
    try {
      const results = await Promise.all(
        prompts.map((prompt) => this.analyzeImage(base64Image, prompt)),
      );

      const errors = results.filter((r) => !r.success);
      if (errors.length === results.length) {
        return {
          success: false,
          description: "",
          model: this.model,
          error: errors.map((e) => e.error).join("; "),
        };
      }

      const combined = results
        .filter((r) => r.success)
        .map((r) => r.description)
        .join("\n\n");

      return {
        success: true,
        description: combined,
        model: this.model,
      };
    } catch (err) {
      return {
        success: false,
        description: "",
        model: this.model,
        error: err instanceof Error ? err.message : String(err),
      };
    }
  }
}
