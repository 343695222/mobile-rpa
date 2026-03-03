import type { AdbClient } from "./adb-client";
import type { UiElement, Bounds, ScreenState, ScreenDiff } from "./types";

/**
 * ScreenParser 接口 - 屏幕状态解析与差异计算
 */
export interface ScreenParser {
  captureScreen(deviceId: string): Promise<ScreenState>;
  diffScreens(prev: ScreenState, curr: ScreenState): ScreenDiff;
  parseAccessibilityTree(xml: string): UiElement[];
}

/**
 * 解析 bounds 属性字符串 "[left,top][right,bottom]" 为 Bounds 对象
 */
export function parseBounds(boundsStr: string): Bounds {
  const match = boundsStr.match(/\[(\d+),(\d+)\]\[(\d+),(\d+)\]/);
  if (!match) {
    return { left: 0, top: 0, right: 0, bottom: 0 };
  }
  return {
    left: parseInt(match[1], 10),
    top: parseInt(match[2], 10),
    right: parseInt(match[3], 10),
    bottom: parseInt(match[4], 10),
  };
}

/**
 * 从完整类名中提取简短类型名
 * e.g. "android.widget.Button" -> "Button"
 */
function extractTypeName(className: string): string {
  const parts = className.split(".");
  return parts[parts.length - 1] || className;
}

/**
 * 判断元素是否应保留（过滤逻辑）
 *
 * 保留条件（满足任一即保留）：
 * - 有文本内容 (text)
 * - 有内容描述 (content-desc)
 * - 可点击 (clickable)
 * - 可滚动 (scrollable)
 * - 可聚焦 (focusable)
 *
 * 即：移除那些既没有文本/描述，又不可交互的元素
 */
export function shouldKeepElement(attrs: {
  text: string;
  contentDesc: string;
  clickable: boolean;
  scrollable: boolean;
  focusable: boolean;
}): boolean {
  return (
    attrs.text.length > 0 ||
    attrs.contentDesc.length > 0 ||
    attrs.clickable ||
    attrs.scrollable ||
    attrs.focusable
  );
}


/**
 * 从 XML 字符串中提取所有 <node> 元素的属性
 * 使用正则解析，避免依赖外部 XML 库
 */
function extractNodeAttributes(xml: string): Array<Record<string, string>> {
  const nodes: Array<Record<string, string>> = [];
  // Match each <node ... > or <node ... />
  const nodeRegex = /<node\s([^>]*?)\/?>/g;
  let match: RegExpExecArray | null;

  while ((match = nodeRegex.exec(xml)) !== null) {
    const attrStr = match[1];
    const attrs: Record<string, string> = {};

    // Match key="value" pairs
    const attrRegex = /(\w[\w-]*)="([^"]*)"/g;
    let attrMatch: RegExpExecArray | null;
    while ((attrMatch = attrRegex.exec(attrStr)) !== null) {
      attrs[attrMatch[1]] = attrMatch[2];
    }
    nodes.push(attrs);
  }

  return nodes;
}

/**
 * 生成元素的匹配键，用于 diffScreens 中匹配元素
 * 优先使用 resourceId，若为空则使用 className+bounds 组合
 */
function elementMatchKey(elem: UiElement): string {
  if (elem.resourceId) {
    return `rid:${elem.resourceId}`;
  }
  return `cls:${elem.className}|b:${elem.bounds.left},${elem.bounds.top},${elem.bounds.right},${elem.bounds.bottom}`;
}

/**
 * 比较两个 UiElement 是否属性发生了变化（排除 id 字段）
 */
function elementsChanged(a: UiElement, b: UiElement): boolean {
  return (
    a.text !== b.text ||
    a.contentDesc !== b.contentDesc ||
    a.clickable !== b.clickable ||
    a.scrollable !== b.scrollable ||
    a.focusable !== b.focusable ||
    a.enabled !== b.enabled ||
    a.bounds.left !== b.bounds.left ||
    a.bounds.top !== b.bounds.top ||
    a.bounds.right !== b.bounds.right ||
    a.bounds.bottom !== b.bounds.bottom ||
    a.className !== b.className ||
    a.type !== b.type
  );
}

/**
 * DefaultScreenParser - ScreenParser 的具体实现
 */
export class DefaultScreenParser implements ScreenParser {
  constructor(private readonly adbClient: AdbClient) {}

  parseAccessibilityTree(xml: string): UiElement[] {
    const nodeAttrs = extractNodeAttributes(xml);
    const elements: UiElement[] = [];
    let idCounter = 0;

    for (const attrs of nodeAttrs) {
      const text = attrs["text"] ?? "";
      const contentDesc = attrs["content-desc"] ?? "";
      const clickable = attrs["clickable"] === "true";
      const scrollable = attrs["scrollable"] === "true";
      const focusable = attrs["focusable"] === "true";

      if (!shouldKeepElement({ text, contentDesc, clickable, scrollable, focusable })) {
        continue;
      }

      const className = attrs["class"] ?? "";
      const boundsStr = attrs["bounds"] ?? "[0,0][0,0]";

      elements.push({
        id: `elem_${idCounter}`,
        type: extractTypeName(className),
        text,
        contentDesc,
        bounds: parseBounds(boundsStr),
        clickable,
        scrollable,
        focusable,
        enabled: attrs["enabled"] === "true",
        resourceId: attrs["resource-id"] ?? "",
        className,
      });

      idCounter++;
    }

    return elements;
  }

  async captureScreen(deviceId: string): Promise<ScreenState> {
    const rawXml = await this.adbClient.dumpUiHierarchy(deviceId);
    const elements = this.parseAccessibilityTree(rawXml);
    return {
      timestamp: Date.now(),
      deviceId,
      elements,
      rawXml,
    };
  }

  diffScreens(prev: ScreenState, curr: ScreenState): ScreenDiff {
    const prevMap = new Map<string, UiElement>();
    for (const elem of prev.elements) {
      prevMap.set(elementMatchKey(elem), elem);
    }

    const currMap = new Map<string, UiElement>();
    for (const elem of curr.elements) {
      currMap.set(elementMatchKey(elem), elem);
    }

    const added: UiElement[] = [];
    const removed: UiElement[] = [];
    const changed: Array<{ before: UiElement; after: UiElement }> = [];

    // Find added and changed elements
    for (const [key, currElem] of currMap) {
      const prevElem = prevMap.get(key);
      if (!prevElem) {
        added.push(currElem);
      } else if (elementsChanged(prevElem, currElem)) {
        changed.push({ before: prevElem, after: currElem });
      }
    }

    // Find removed elements
    for (const [key, prevElem] of prevMap) {
      if (!currMap.has(key)) {
        removed.push(prevElem);
      }
    }

    return { added, removed, changed };
  }
}
