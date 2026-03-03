import { describe, test, expect } from "bun:test";
import { BunAdbClient, parseDeviceList } from "../src/adb-client";

describe("ADB Client - parseDeviceList", () => {
  test("parses single connected device with model", () => {
    const output = `List of devices attached
emulator-5554          device product:sdk_gphone64_x86_64 model:Pixel_6 transport_id:1
`;
    const devices = parseDeviceList(output);
    expect(devices).toHaveLength(1);
    expect(devices[0]).toEqual({
      id: "emulator-5554",
      model: "Pixel_6",
      status: "device",
    });
  });

  test("parses multiple devices with different statuses", () => {
    const output = `List of devices attached
emulator-5554          device product:sdk model:Pixel_6 transport_id:1
192.168.1.100:5555     offline
ABCDEF123456           unauthorized
`;
    const devices = parseDeviceList(output);
    expect(devices).toHaveLength(3);
    expect(devices[0].status).toBe("device");
    expect(devices[1].status).toBe("offline");
    expect(devices[1].model).toBe("unknown");
    expect(devices[2].status).toBe("unauthorized");
  });

  test("returns empty array when no devices connected", () => {
    const output = `List of devices attached

`;
    const devices = parseDeviceList(output);
    expect(devices).toHaveLength(0);
  });

  test("handles device without model property", () => {
    const output = `List of devices attached
192.168.1.100:5555     device
`;
    const devices = parseDeviceList(output);
    expect(devices).toHaveLength(1);
    expect(devices[0].model).toBe("unknown");
    expect(devices[0].id).toBe("192.168.1.100:5555");
  });

  test("ignores malformed lines", () => {
    const output = `List of devices attached
some garbage line
emulator-5554          device model:Test
another bad line
`;
    const devices = parseDeviceList(output);
    expect(devices).toHaveLength(1);
    expect(devices[0].id).toBe("emulator-5554");
  });

  test("handles empty output", () => {
    const devices = parseDeviceList("");
    expect(devices).toHaveLength(0);
  });
});

describe("ADB Client - interface contract", () => {
  test("BunAdbClient implements AdbClient interface", () => {
    const client = new BunAdbClient();

    expect(typeof client.listDevices).toBe("function");
    expect(typeof client.isConnected).toBe("function");
    expect(typeof client.dumpUiHierarchy).toBe("function");
    expect(typeof client.tap).toBe("function");
    expect(typeof client.inputText).toBe("function");
    expect(typeof client.swipe).toBe("function");
    expect(typeof client.keyEvent).toBe("function");
    expect(typeof client.shell).toBe("function");
  });
});
