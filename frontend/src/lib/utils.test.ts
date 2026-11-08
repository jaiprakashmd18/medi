import { formatBytes, isProcessing } from "./utils";

it("formats bytes", () => {
  expect(formatBytes(512)).toBe("512 B");
  expect(formatBytes(2048)).toBe("2 KB");
  expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
});

it("knows terminal processing states", () => {
  expect(isProcessing("embedding")).toBe(true);
  expect(isProcessing("ready")).toBe(false);
  expect(isProcessing("failed")).toBe(false);
});
