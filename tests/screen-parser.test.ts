import { describe, test, expect } from "bun:test";
import {
  DefaultScreenParser,
  parseBounds,
  shouldKeepElement,
} from "../src/screen-parser";
import type { AdbClient } from "../src/adb-client";
import type { ScreenState, UiElement } from "../src/types";

// --- Helper: minimal mock ADB client ---

function createMockAdbClient(xml: string): AdbClient {
  return {
    listDevices: async () => [],
    isConnected: async () => true,
    dumpUiHierarchy: async () => xml,
    tap: async () => {},
    inputText: async () => {},
    swipe: async () => {},
    keyEvent: async () => {},
    shell: async () => "",
  };
}

// --- Sample XML fragments ---

const SIMPLE_XML = `<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node class="android.widget.FrameLayout" text="" content-desc="" resource-id="" bounds="[0,0][1080,1920]" clickable="false" scrollable="false" focusable="false" enabled="true">
    <node class="android.widget.Button" text="OK" content-desc="" resource-id="com.app:id/btn_ok" bounds="[100,200][300,260]" clickable="true" scrollable="false" focusable="true" enabled="true" />
    <node class="android.widget.TextView" text="Hello World" content-desc="" resource-id="com.app:id/title" bounds="[50,50][500,100]" clickable="false" scrollable="false" focusable="false" enabled="true" />
  </node>
</hierarchy>`;

const MIXED_XML = `<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node class="android.widget.FrameLayout" text="" content-desc="" resource-id="" bounds="[0,0][1080,1920]" clickable="false" scrollable="false" focusable="false" enabled="true">
    <node class="android.widget.Button" text="Submit" content-desc="" resource-id="btn1" bounds="[10,10][100,50]" clickable="true" scrollable="false" focusable="true" enabled="true" />
    <node class="android.view.View" text="" content-desc="" resource-id="" bounds="[0,0][1080,1920]" clickable="false" scrollable="false" focusable="false" enabled="true" />
    <node class="android.widget.ScrollView" text="" content-desc="" resource-id="scroll1" bounds="[0,100][1080,1800]" clickable="false" scrollable="true" focusable="false" enabled="true" />
    <node class="android.widget.ImageView" text="" content-desc="Logo" resource-id="" bounds="[200,300][400,500]" clickable="false" scrollable="false" focusable="false" enabled="true" />
  </node>
</hierarchy>`;

// --- Tests ---

describe("parseBounds", () => {
  test("parses valid bounds string", () => {
    expect(parseBounds("[100,200][300,400]")).toEqual({
      left: 100, top: 200, right: 300, bottom: 400,
    });
  });

  test("returns zero bounds for invalid string", () => {
    expect(parseBounds("invalid")).toEqual({
      left: 0, top: 0, right: 0, bottom: 0,
    });
  });

  test("parses bounds with large numbers", () => {
    expect(parseBounds("[0,0][1080,1920]")).toEqual({
      left: 0, top: 0, right: 1080, bottom: 1920,
    });
  });
});


describe("shouldKeepElement", () => {
  test("keeps element with text", () => {
    expect(shouldKeepElement({
      text: "Hello", contentDesc: "", clickable: false, scrollable: false, focusable: false,
    })).toBe(true);
  });

  test("keeps element with contentDesc", () => {
    expect(shouldKeepElement({
      text: "", contentDesc: "Back button", clickable: false, scrollable: false, focusable: false,
    })).toBe(true);
  });

  test("keeps clickable element", () => {
    expect(shouldKeepElement({
      text: "", contentDesc: "", clickable: true, scrollable: false, focusable: false,
    })).toBe(true);
  });

  test("keeps scrollable element", () => {
    expect(shouldKeepElement({
      text: "", contentDesc: "", clickable: false, scrollable: true, focusable: false,
    })).toBe(true);
  });

  test("keeps focusable element", () => {
    expect(shouldKeepElement({
      text: "", contentDesc: "", clickable: false, scrollable: false, focusable: true,
    })).toBe(true);
  });

  test("removes element with no text, no desc, not interactable", () => {
    expect(shouldKeepElement({
      text: "", contentDesc: "", clickable: false, scrollable: false, focusable: false,
    })).toBe(false);
  });
});

describe("parseAccessibilityTree", () => {
  const parser = new DefaultScreenParser(createMockAdbClient(""));

  test("parses simple XML and extracts elements", () => {
    const elements = parser.parseAccessibilityTree(SIMPLE_XML);
    // FrameLayout is filtered out (no text, no desc, not interactable)
    // Button (text="OK", clickable) and TextView (text="Hello World") kept
    expect(elements).toHaveLength(2);
  });

  test("extracts correct fields from Button node", () => {
    const elements = parser.parseAccessibilityTree(SIMPLE_XML);
    const button = elements.find(e => e.type === "Button");
    expect(button).toBeDefined();
    expect(button!.text).toBe("OK");
    expect(button!.clickable).toBe(true);
    expect(button!.focusable).toBe(true);
    expect(button!.resourceId).toBe("com.app:id/btn_ok");
    expect(button!.bounds).toEqual({ left: 100, top: 200, right: 300, bottom: 260 });
    expect(button!.className).toBe("android.widget.Button");
  });

  test("extracts correct fields from TextView node", () => {
    const elements = parser.parseAccessibilityTree(SIMPLE_XML);
    const textView = elements.find(e => e.type === "TextView");
    expect(textView).toBeDefined();
    expect(textView!.text).toBe("Hello World");
    expect(textView!.clickable).toBe(false);
  });

  test("filters out invisible non-interactable elements", () => {
    const elements = parser.parseAccessibilityTree(MIXED_XML);
    // FrameLayout: no text, no desc, not interactable -> filtered
    // Button: text="Submit", clickable -> kept
    // View: no text, no desc, not interactable -> filtered
    // ScrollView: scrollable -> kept
    // ImageView: contentDesc="Logo" -> kept
    expect(elements).toHaveLength(3);
    const types = elements.map(e => e.type);
    expect(types).toContain("Button");
    expect(types).toContain("ScrollView");
    expect(types).toContain("ImageView");
  });

  test("assigns sequential elem_N IDs", () => {
    const elements = parser.parseAccessibilityTree(MIXED_XML);
    expect(elements[0].id).toBe("elem_0");
    expect(elements[1].id).toBe("elem_1");
    expect(elements[2].id).toBe("elem_2");
  });

  test("all IDs are unique", () => {
    const elements = parser.parseAccessibilityTree(MIXED_XML);
    const ids = elements.map(e => e.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  test("handles empty XML", () => {
    const elements = parser.parseAccessibilityTree("");
    expect(elements).toHaveLength(0);
  });

  test("handles XML with no matching nodes", () => {
    const xml = `<?xml version="1.0"?><hierarchy rotation="0"></hierarchy>`;
    const elements = parser.parseAccessibilityTree(xml);
    expect(elements).toHaveLength(0);
  });
});

describe("captureScreen", () => {
  test("returns ScreenState with parsed elements", async () => {
    const parser = new DefaultScreenParser(createMockAdbClient(SIMPLE_XML));
    const state = await parser.captureScreen("device-1");

    expect(state.deviceId).toBe("device-1");
    expect(state.rawXml).toBe(SIMPLE_XML);
    expect(state.elements.length).toBeGreaterThan(0);
    expect(state.timestamp).toBeGreaterThan(0);
  });

  test("propagates ADB errors", async () => {
    const failClient = createMockAdbClient("");
    failClient.dumpUiHierarchy = async () => {
      throw new Error("ADB connection lost");
    };
    const parser = new DefaultScreenParser(failClient);

    await expect(parser.captureScreen("device-1")).rejects.toThrow("ADB connection lost");
  });
});

describe("diffScreens", () => {
  const parser = new DefaultScreenParser(createMockAdbClient(""));

  function makeState(elements: UiElement[], deviceId = "dev1"): ScreenState {
    return { timestamp: Date.now(), deviceId, elements, rawXml: "" };
  }

  function makeElement(overrides: Partial<UiElement> & { id: string }): UiElement {
    return {
      type: "Button",
      text: "",
      contentDesc: "",
      bounds: { left: 0, top: 0, right: 100, bottom: 50 },
      clickable: true,
      scrollable: false,
      focusable: false,
      enabled: true,
      resourceId: "",
      className: "android.widget.Button",
      ...overrides,
    };
  }

  test("detects added elements", () => {
    const prev = makeState([]);
    const curr = makeState([
      makeElement({ id: "elem_0", resourceId: "btn1" }),
    ]);
    const diff = parser.diffScreens(prev, curr);
    expect(diff.added).toHaveLength(1);
    expect(diff.removed).toHaveLength(0);
    expect(diff.changed).toHaveLength(0);
  });

  test("detects removed elements", () => {
    const prev = makeState([
      makeElement({ id: "elem_0", resourceId: "btn1" }),
    ]);
    const curr = makeState([]);
    const diff = parser.diffScreens(prev, curr);
    expect(diff.added).toHaveLength(0);
    expect(diff.removed).toHaveLength(1);
    expect(diff.changed).toHaveLength(0);
  });

  test("detects changed elements (text changed)", () => {
    const prev = makeState([
      makeElement({ id: "elem_0", resourceId: "title", text: "Hello" }),
    ]);
    const curr = makeState([
      makeElement({ id: "elem_0", resourceId: "title", text: "World" }),
    ]);
    const diff = parser.diffScreens(prev, curr);
    expect(diff.added).toHaveLength(0);
    expect(diff.removed).toHaveLength(0);
    expect(diff.changed).toHaveLength(1);
    expect(diff.changed[0].before.text).toBe("Hello");
    expect(diff.changed[0].after.text).toBe("World");
  });

  test("matches elements by resourceId", () => {
    const prev = makeState([
      makeElement({ id: "elem_0", resourceId: "com.app:id/btn", text: "A" }),
    ]);
    const curr = makeState([
      makeElement({ id: "elem_5", resourceId: "com.app:id/btn", text: "B" }),
    ]);
    const diff = parser.diffScreens(prev, curr);
    // Same resourceId -> matched, text changed
    expect(diff.added).toHaveLength(0);
    expect(diff.removed).toHaveLength(0);
    expect(diff.changed).toHaveLength(1);
  });

  test("matches elements by className+bounds when no resourceId", () => {
    const bounds = { left: 10, top: 20, right: 100, bottom: 50 };
    const prev = makeState([
      makeElement({ id: "elem_0", resourceId: "", className: "android.widget.Button", bounds, text: "X" }),
    ]);
    const curr = makeState([
      makeElement({ id: "elem_0", resourceId: "", className: "android.widget.Button", bounds, text: "Y" }),
    ]);
    const diff = parser.diffScreens(prev, curr);
    expect(diff.changed).toHaveLength(1);
    expect(diff.added).toHaveLength(0);
    expect(diff.removed).toHaveLength(0);
  });

  test("identical screens produce empty diff", () => {
    const elem = makeElement({ id: "elem_0", resourceId: "r1", text: "Same" });
    const prev = makeState([elem]);
    const curr = makeState([{ ...elem }]);
    const diff = parser.diffScreens(prev, curr);
    expect(diff.added).toHaveLength(0);
    expect(diff.removed).toHaveLength(0);
    expect(diff.changed).toHaveLength(0);
  });

  test("empty screens produce empty diff", () => {
    const diff = parser.diffScreens(makeState([]), makeState([]));
    expect(diff.added).toHaveLength(0);
    expect(diff.removed).toHaveLength(0);
    expect(diff.changed).toHaveLength(0);
  });
});
