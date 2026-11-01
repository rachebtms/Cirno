import { expect, it } from "vitest";
import { implementationToolName, toolAction, displayToolName } from "@/lib/tool-names";
import { parseGenericToolTrace } from "@/components/thread/activity/generic-tool-model";

it("uses the shared catalog to classify namespaced and historical activity", () => {
  expect(implementationToolName("files__read")).toBe("read_file");
  expect(implementationToolName("files.read")).toBe("read_file");
  expect(implementationToolName("read_file")).toBe("read_file");
  expect(implementationToolName("ptc__run")).toBe("run_code");
  expect(displayToolName("memory__search")).toBe("memory.search");
  expect(toolAction("memory__search")).toBe("search");
  expect(toolAction("web__search")).toBeUndefined();
});

it("preserves the operation in a namespaced memory activity", () => {
  const trace = parseGenericToolTrace('memory__search({"query":"exact result"})');
  expect(trace?.family).toBe("memory");
  expect(trace?.fields).toContainEqual({ key: "action", value: "search" });
  expect(trace?.fields).toContainEqual({ key: "query", value: "exact result" });
  expect(parseGenericToolTrace('files__read({"path":"notes.md"})')?.family).toBe("read");
  const read = parseGenericToolTrace('memory__read({"memory_id":"one"})');
  const save = parseGenericToolTrace('memory__save({"content":"result","source":"notes.md"})');
  expect(save?.family).toBe("generic");
  expect(save?.groupKey).not.toBe(read?.groupKey);
});
