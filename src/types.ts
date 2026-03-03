// === 设备相关 ===

export interface DeviceInfo {
  id: string;           // 设备序列号
  model: string;        // 设备型号
  status: "device" | "offline" | "unauthorized";
}

// === 屏幕状态相关 ===

export interface Bounds {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface UiElement {
  id: string;           // 唯一标识符 (e.g., "elem_0", "elem_1")
  type: string;         // 元素类型 (Button, EditText, TextView, etc.)
  text: string;         // 文本内容
  contentDesc: string;  // 内容描述
  bounds: Bounds;       // 坐标范围
  clickable: boolean;
  scrollable: boolean;
  focusable: boolean;
  enabled: boolean;
  resourceId: string;   // Android resource ID
  className: string;    // 完整类名
}

export interface ScreenState {
  timestamp: number;
  deviceId: string;
  elements: UiElement[];
  rawXml: string;
}

export interface ScreenDiff {
  added: UiElement[];
  removed: UiElement[];
  changed: Array<{ before: UiElement; after: UiElement }>;
}


// === 操作相关 ===

export type Action =
  | { type: "tap"; x: number; y: number }
  | { type: "tap_element"; elementId: string }
  | { type: "input_text"; text: string }
  | { type: "swipe"; x1: number; y1: number; x2: number; y2: number; duration: number }
  | { type: "key_event"; keyCode: number }
  | { type: "wait"; ms: number }
  | { type: "long_press"; x: number; y: number; duration: number }
  | { type: "open_app"; packageName: string }
  | { type: "go_back" }
  | { type: "go_home" }
  | { type: "scroll_up" }
  | { type: "scroll_down" }
  | { type: "wake_screen" }
  | { type: "lock_screen" };

export interface ActionResult {
  success: boolean;
  action: Action;
  error?: string;
  durationMs: number;
}

// === 模板相关 ===

export interface TemplateParam {
  name: string;
  description: string;
  required: boolean;
  defaultValue?: string;
}

export interface TemplateStep {
  order: number;
  action: Action;
  description: string;
  expectedScreenHint?: string; // 可选：期望的屏幕状态提示
}

export interface OperationTemplate {
  name: string;
  description: string;
  params: TemplateParam[];
  steps: TemplateStep[];
  metadata: {
    createdAt: string;
    source: "manual" | "auto-generated";
    taskDescription?: string;
  };
}

export interface ResolvedTemplate {
  name: string;
  steps: TemplateStep[];  // 参数已替换
}

export interface TemplateSummary {
  name: string;
  description: string;
  params: TemplateParam[];
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}


// === RPA 循环相关 ===

export interface StepRecord {
  stepNumber: number;
  screenSummary: string;
  action: Action;
  result: ActionResult;
  timestamp: number;
}

export interface ExecutionHistory {
  taskGoal: string;
  steps: StepRecord[];
  startTime: number;
  endTime: number;
}

export interface LoopOptions {
  maxSteps: number;       // 默认 30
  stuckThreshold: number; // 默认 3
  timeoutMs: number;      // 默认 300000 (5分钟)
}

export interface ExplorationResult {
  success: boolean;
  history: ExecutionHistory;
  generatedTemplate?: OperationTemplate;
  message: string;
}

export interface TemplateExecutionResult {
  success: boolean;
  stepsCompleted: number;
  totalSteps: number;
  stepResults: ActionResult[];
  message: string;
}

// === 指令与响应 ===

export type CommandType =
  | "list_devices"
  | "get_screen"
  | "execute_action"
  | "run_template"
  | "run_task"
  | "list_templates"
  | "screenshot"
  | "analyze_screen"
  | "smart_task"
  | "collect_data"
  | "list_scripts"
  | "validate_scripts"
  | "autox_execute"
  | "open_app"
  | "go_back"
  | "go_home"
  | "scroll_up"
  | "scroll_down"
  | "get_current_app"
  | "wake_screen"
  | "lock_screen"
  // 安全守卫
  | "safety_rules"
  | "safety_log"
  | "safety_pending"
  | "safety_confirm"
  | "safety_mode"
  | "safety_set_mode"
  // 平台分析
  | "analyze_platform"
  | "traffic_start"
  | "traffic_stop"
  | "traffic_records"
  | "traffic_load_har"
  // AutoJS 直连模式
  | "autox_health"
  | "autox_device_info"
  | "autox_screenshot"
  | "autox_click"
  | "autox_long_click"
  | "autox_swipe"
  | "autox_scroll"
  | "autox_input"
  | "autox_key"
  | "autox_app_start"
  | "autox_app_stop"
  | "autox_app_current"
  | "autox_find_element"
  | "autox_click_element"
  | "autox_ui_tree"
  | "autox_ocr"
  | "autox_clipboard"
  | "autox_smart_task";

export interface ParsedCommand {
  type: CommandType;
  deviceId?: string;
  action?: Action;
  templateName?: string;
  templateParams?: Record<string, string>;
  taskGoal?: string;
  prompt?: string;  // 用于 analyze_screen 的自然语言提示
  packageName?: string; // 用于 open_app
  // 数据采集相关字段 (collect_data)
  app?: string;
  dataType?: string;
  query?: string;
  forceStrategy?: string;
  // AutoX 脚本执行 (autox_execute)
  script?: string;
  // 安全守卫 (safety_confirm)
  confirmId?: string;
  approved?: boolean;
  // 安全模式 (safety_set_mode)
  safetyMode?: string;  // strict / permissive / observe_only
  // 平台分析 (analyze_platform)
  platformName?: string;
  appPackage?: string;
  domainFilter?: string[];
  harFile?: string;
  // AutoJS 直连模式参数
  x?: number;
  y?: number;
  x1?: number;
  y1?: number;
  x2?: number;
  y2?: number;
  duration?: number;
  direction?: "up" | "down";
  text?: string;
  key?: "back" | "home" | "recents" | "power";
  by?: "text" | "textContains" | "id" | "className" | "desc" | "descContains";
  value?: string;
  timeout?: number;
  maxDepth?: number;
  maxSteps?: number;
}

export interface SkillResponse {
  status: "success" | "error";
  message: string;
  data?: unknown;
}


// === 数据采集相关 ===

export interface NavigationStep {
  order: number;
  action: {
    type: "click" | "click_element" | "swipe" | "input_text" | "wait";
    x?: number;
    y?: number;
    selector?: { by: "text" | "resourceId" | "xpath"; value: string };
    text?: string;
    duration?: number;
  };
  description: string;
}

export interface ApiConfig {
  method: string;
  url: string;
  headers?: Record<string, string>;
  params?: Record<string, string>;
  body?: unknown;
  dataPath: string;
}

export interface ClipboardConfig {
  longPressX: number;
  longPressY: number;
  selectAllText: string;
  copyText: string;
}

export interface OcrConfig {
  maxPages: number;
  swipeParams: { x1: number; y1: number; x2: number; y2: number; duration: number };
  extractPrompt: string;
}

export interface ExtractionConfig {
  type: "api" | "clipboard" | "ocr";
  config: ApiConfig | ClipboardConfig | OcrConfig;
}

export interface CollectionScript {
  id: string;
  app: string;
  dataType: string;
  strategy: "api" | "rpa_copy" | "rpa_ocr";
  navigation: NavigationStep[];
  extraction: ExtractionConfig;
  metadata: {
    createdAt: string;
    lastUsedAt: string;
    lastValidatedAt: string;
    useCount: number;
    isValid: boolean;
  };
}

export interface CollectionResult {
  success: boolean;
  items: unknown[];
  strategy: string;
  scriptId?: string;
  error?: string;
}
