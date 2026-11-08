import { describe, expect, it } from "vitest";
import i18n from "@/i18n";
import { entriesForJobs } from "@/features/automations/calendar/model";
import {
  formatAutomationInterval,
  formatAutomationNext,
  formatAutomationSchedule,
} from "@/features/automations/model/presentation";
import {
  automationMatchesFilter,
  automationStatusKey,
} from "@/features/automations/model/status";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
const base: SessionAutomationJob = {
  id: "research",
  name: "Research",
  enabled: true,
  schedule: { kind: "cron", expr: "30 13 25 * *" },
  payload: { message: "Review results" },
  state: {},
};
const tx = (key: string, fallback: string, values?: Record<string, unknown>) =>
  i18n.t(key, { defaultValue: fallback, ...values });
describe("Automation scheduling presentation", () => {
  it.each([
    ["30 13 25 * *", "Monthly on day 25 at 13:30"],
    ["0 0 1 * *", "Monthly on day 1 at 00:00"],
    ["30 8 * * 1", "Every Monday at 08:30"],
    ["0 19 * * 0", "Every Sunday at 19:00"],
    ["0 19 * * 7", "Every Sunday at 19:00"],
    ["0 10 * * SAT", "Every Saturday at 10:00"],
    ["0 10 * * 8", "Custom schedule"],
    ["30 13 25 * 1", "Custom schedule"],
    ["*/15 9-17 * * 1,3,5", "Custom schedule"],
    ["0 9 0 * *", "Custom schedule"],
  ])(
    "summarizes %s without inventing a supported schedule",
    (expr, summary) => {
      expect(
        formatAutomationSchedule(
          { ...base, schedule: { kind: "cron", expr } },
          "en",
          tx,
        ),
      ).toBe(summary);
    },
  );
  it("preserves exact durations when seconds or minutes would lose precision", () => {
    expect(formatAutomationInterval(62_500, "en")).toBe("62,500 milliseconds");
    expect(formatAutomationInterval(1001, "en")).toBe("1,001 milliseconds");
    expect(formatAutomationInterval(60_000, "en")).toBe("1 minute");
  });
  it("does not call a missing next run a completed task", () => {
    expect(automationStatusKey(base)).toBe("idle");
    expect(formatAutomationNext(base, tx)).toBe("No next run");
    expect(
      automationStatusKey({
        ...base,
        delete_after_run: true,
        state: { last_status: "ok" },
      }),
    ).toBe("completed");
    expect(automationStatusKey({ ...base, state: { next_run_at_ms: 0 } })).toBe(
      "active",
    );
  });
  it("preserves the failure filter for a paused or still-running task", () => {
    for (const state of [
      { last_status: "error" },
      { last_error: "Disk is full" },
      { pending: true, last_status: "error" },
    ]) {
      expect(
        automationMatchesFilter({ ...base, enabled: false, state }, "failed"),
      ).toBe(true);
    }
    expect(
      automationStatusKey({
        ...base,
        enabled: false,
        state: { pending: true, last_status: "error" },
      }),
    ).toBe("running");
  });
});
describe("Automation run identity", () => {
  it("keeps historical output linked to its recorded chat instead of the current task chat", () => {
    const run = {
      run_at_ms: 0,
      status: "ok",
      duration_ms: 0,
      webui_session_key: "websocket:original",
    };
    const result = entriesForJobs([
      {
        ...base,
        origin: { channel: "websocket", session_key: "websocket:new" },
        state: { next_run_at_ms: 1000, run_history: [run] },
      },
    ]);
    expect(result).toHaveLength(2);
    expect(result[0]).toMatchObject({ kind: "recorded", startMs: 0, run });
    expect(result[1]).toMatchObject({
      kind: "planned",
      startMs: 1000,
      run: null,
    });
  });
  it("includes command-trigger history without inventing a future run", () => {
    const result = entriesForJobs([
      {
        ...base,
        kind: "local_trigger",
        schedule: { kind: "local" },
        state: {
          last_run_at_ms: 0,
          last_status: "error",
          last_error: "GPU is offline",
        },
      },
    ]);
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      kind: "recorded",
      startMs: 0,
      run: { status: "error", error: "GPU is offline" },
    });
  });
  it("retains recorded runs when a task is disabled", () => {
    const result = entriesForJobs([
      {
        ...base,
        enabled: false,
        state: {
          next_run_at_ms: 1000,
          run_history: [{ run_at_ms: 500, status: "skipped" }],
        },
      },
    ]);
    expect(result.map((entry) => entry.kind)).toEqual(["recorded"]);
  });
});
