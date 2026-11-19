import { describe, expect, it } from "vitest";

import {
  canonicalToolTrace,
  mergeToolProgressTraceLines,
  mergeUniqueToolTraceLines,
} from "@/lib/tool-traces";

describe("tool trace identity", () => {
  it("treats persisted and live JSON formatting as the same call", () => {
    const persisted = 'web_search({"query": "site:linkedin.com/company Evomap startup", "count": 10})';
    const live = 'web_search({"query":"site:linkedin.com/company Evomap startup","count":10})';

    expect(canonicalToolTrace(persisted)).toBe(canonicalToolTrace(live));
    expect(mergeUniqueToolTraceLines([persisted], [live])).toEqual({
      traces: [persisted],
      added: false,
    });
  });

  it("keeps genuinely different calls separate", () => {
    const first = 'web_search({"query":"cirno"})';
    const second = 'web_search({"query":"cirno cloud"})';

    expect(mergeUniqueToolTraceLines([first], [second])).toEqual({
      traces: [first, second],
      added: true,
    });
  });

  it("ignores nested JSON object field order without changing array order", () => {
    const first = 'fixture({"z":{"b":2,"a":1},"a":[{"y":2,"x":1},3]})';
    const reordered = 'fixture({"a":[{"x":1,"y":2},3],"z":{"a":1,"b":2}})';
    const different = 'fixture({"a":[3,{"x":1,"y":2}],"z":{"a":1,"b":2}})';
    expect(canonicalToolTrace(first)).toBe(canonicalToolTrace(reordered));
    expect(canonicalToolTrace(first)).not.toBe(canonicalToolTrace(different));
  });

  it("replaces an empty streaming placeholder when hosted search arguments arrive", () => {
    expect(mergeToolProgressTraceLines(
      ["web_search()"],
      [{ phase: "start", call_id: "ws-1", name: "web_search", arguments: {} }],
      ['web_search({"query":"cirno news"})'],
      [{
        phase: "end",
        call_id: "ws-1",
        name: "web_search",
        arguments: { query: "cirno news" },
      }],
    )).toEqual(['web_search({"query":"cirno news"})']);
  });
});
