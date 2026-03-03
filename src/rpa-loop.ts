import type { ScreenParser } from "./screen-parser";
import type { ActionExecutor } from "./action-executor";
import type { TemplateEngine } from "./template-engine";
import type {
  Action,
  ScreenState,
  StepRecord,
  ExecutionHistory,
  LoopOptions,
  ExplorationResult,
  TemplateExecutionResult,
  ResolvedTemplate,
  OperationTemplate,
} from "./types";

// === RpaLoop Interface ===

export interface RpaLoop {
  runExploration(
    deviceId: string,
    goal: string,
    options?: Partial<LoopOptions>,
  ): Promise<ExplorationResult>;

  runTemplate(
    deviceId: string,
    template: ResolvedTemplate,
  ): Promise<TemplateExecutionResult>;

  detectStuck(history: StepRecord[]): boolean;
}

/** Callback used in exploration mode to decide the next action based on screen state and goal */
export type DecideActionFn = (screen: ScreenState, goal: string) => Action;

/** Default loop options */
const DEFAULT_OPTIONS: LoopOptions = {
  maxSteps: 30,
  stuckThreshold: 3,
  timeoutMs: 300_000, // 5 minutes
};

/**
 * Summarize a ScreenState into a short string for StepRecord.screenSummary.
 * Uses element count and first few element texts as a fingerprint.
 */
function summarizeScreen(screen: ScreenState): string {
  const count = screen.elements.length;
  const texts = screen.elements
    .slice(0, 5)
    .map((e) => e.text || e.contentDesc || e.type)
    .join(",");
  return `[${count} elements] ${texts}`;
}

/**
 * Compare two actions for equality (same type and same parameters).
 */
function actionsEqual(a: Action, b: Action): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * DefaultRpaLoop - RPA 循环控制器的具体实现
 *
 * 支持两种模式：
 * - 自由探索模式 (runExploration): 感知→决策→执行→记录 循环
 * - 模板执行模式 (runTemplate): 按模板步骤顺序执行
 *
 * 通过构造函数注入 ScreenParser、ActionExecutor、TemplateEngine 和 decideAction 回调。
 */
export class DefaultRpaLoop implements RpaLoop {
  constructor(
    private readonly screenParser: ScreenParser,
    private readonly actionExecutor: ActionExecutor,
    private readonly templateEngine: TemplateEngine,
    private readonly decideAction?: DecideActionFn,
  ) {}

  /**
   * 卡住检测 (Req 6.5)
   *
   * 检查最近 N 步（stuckThreshold，默认 3）是否满足：
   * - 所有操作类型和参数完全相同
   * - 所有屏幕摘要完全相同
   */
  detectStuck(history: StepRecord[], stuckThreshold: number = DEFAULT_OPTIONS.stuckThreshold): boolean {
    if (history.length < stuckThreshold) {
      return false;
    }

    const recentSteps = history.slice(-stuckThreshold);
    const firstStep = recentSteps[0];

    return recentSteps.every(
      (step) =>
        actionsEqual(step.action, firstStep.action) &&
        step.screenSummary === firstStep.screenSummary,
    );
  }

  /**
   * 自由探索模式 (Req 6.1, 6.3, 6.4, 6.5, 6.6)
   *
   * 循环流程：感知屏幕状态 → 通过 decideAction 确定下一步操作 → 执行操作 → 记录 StepRecord
   * - 每步检查卡住检测
   * - 强制最大步骤数限制
   * - 强制超时控制
   * - 成功完成后调用 generateFromHistory 生成模板
   */
  async runExploration(
    deviceId: string,
    goal: string,
    options?: Partial<LoopOptions>,
  ): Promise<ExplorationResult> {
    if (!this.decideAction) {
      // 没有 decideAction 回调时，不支持 Skill 内部自由探索
      // Agent 应使用逐步调用模式：get_screen + execute_action
      return {
        success: false,
        history: { taskGoal: goal, steps: [], startTime: Date.now(), endTime: Date.now() },
        message: "No matching template found. Use step-by-step mode: call get_screen to observe, then execute_action to act, repeat until done.",
      };
    }

    const opts: LoopOptions = { ...DEFAULT_OPTIONS, ...options };
    const steps: StepRecord[] = [];
    const startTime = Date.now();

    for (let stepNum = 1; stepNum <= opts.maxSteps; stepNum++) {
      // Timeout check
      if (Date.now() - startTime >= opts.timeoutMs) {
        return this.buildExplorationResult(false, goal, steps, startTime, "Timeout reached");
      }

      // 1. Capture screen state
      const screen = await this.screenParser.captureScreen(deviceId);
      const screenSummary = summarizeScreen(screen);

      // 2. Determine next action via callback
      const action = this.decideAction(screen, goal);

      // 3. Execute action
      const result = await this.actionExecutor.execute(deviceId, action);

      // 4. Record step
      const record: StepRecord = {
        stepNumber: stepNum,
        screenSummary,
        action,
        result,
        timestamp: Date.now(),
      };
      steps.push(record);

      // 5. Check if action failed
      if (!result.success) {
        return this.buildExplorationResult(
          false, goal, steps, startTime,
          `Action failed at step ${stepNum}: ${result.error}`,
        );
      }

      // 6. Stuck detection
      if (this.detectStuck(steps, opts.stuckThreshold)) {
        return this.buildExplorationResult(
          false, goal, steps, startTime,
          `Stuck detected: last ${opts.stuckThreshold} steps had same action and screen state`,
        );
      }
    }

    // Reached max steps without explicit success signal — treat as success
    // (In real usage, the decideAction callback would signal completion)
    return this.buildExplorationResult(true, goal, steps, startTime, "Exploration completed");
  }

  private buildExplorationResult(
    success: boolean,
    goal: string,
    steps: StepRecord[],
    startTime: number,
    message: string,
  ): ExplorationResult {
    const history: ExecutionHistory = {
      taskGoal: goal,
      steps,
      startTime,
      endTime: Date.now(),
    };

    let generatedTemplate: OperationTemplate | undefined;
    if (success && steps.length > 0) {
      generatedTemplate = this.templateEngine.generateFromHistory(history, goal);
    }

    return { success, history, generatedTemplate, message };
  }

  /**
   * 模板执行模式 (Req 6.2, 6.7)
   *
   * 按模板步骤顺序执行，记录每步结果。
   */
  async runTemplate(
    deviceId: string,
    template: ResolvedTemplate,
  ): Promise<TemplateExecutionResult> {
    const stepResults = [];
    const totalSteps = template.steps.length;

    for (let i = 0; i < totalSteps; i++) {
      const step = template.steps[i];
      const result = await this.actionExecutor.execute(deviceId, step.action);
      stepResults.push(result);

      if (!result.success) {
        return {
          success: false,
          stepsCompleted: i + 1,
          totalSteps,
          stepResults,
          message: `Step ${i + 1}/${totalSteps} failed: ${result.error}`,
        };
      }
    }

    return {
      success: true,
      stepsCompleted: totalSteps,
      totalSteps,
      stepResults,
      message: `All ${totalSteps} steps completed successfully`,
    };
  }

  /**
   * 模式选择逻辑 (Req 6.1, 6.2)
   *
   * 根据 findMatchingTemplate 结果决定使用哪种模式：
   * - 存在匹配模板 → 模板执行模式
   * - 无匹配模板 → 自由探索模式
   */
  async run(
    deviceId: string,
    taskDescription: string,
    templateParams?: Record<string, string>,
    options?: Partial<LoopOptions>,
  ): Promise<ExplorationResult | TemplateExecutionResult> {
    const matchingTemplate = this.templateEngine.findMatchingTemplate(taskDescription);

    if (matchingTemplate) {
      const resolved = this.templateEngine.resolveParams(
        matchingTemplate,
        templateParams ?? {},
      );
      return this.runTemplate(deviceId, resolved);
    }

    return this.runExploration(deviceId, taskDescription, options);
  }
}
