import { describe, expect, it } from "vitest";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import { automationDraftFromJob, parseAutomationDraft } from "@/features/automations/model/draft";
import { parseLocalDateTime } from "@/lib/local-date-time";

const job: SessionAutomationJob = { id: "task", name: "Read reports", enabled: true,
  schedule: { kind: "every", every_ms: 3_600_000 }, payload: { message: "Keep the exact\n  instruction formatting.\n" }, state: {} };
describe("automation change parsing", () => {
  it.each([1, 1001, 62_500, 3600000, 7 * 86400000])("retains the exact %i ms interval when changing only a name", ms => {
    const current = { ...job, schedule: { kind: "every", every_ms: ms } };
    const draft = automationDraftFromJob(current);
    expect(parseAutomationDraft({ ...draft, name: "New title" }, current)).toEqual({ ok: true, value: { name: "New title" } });
    expect(parseAutomationDraft(draft, current)).toEqual({ ok: true, value: {} });
  });
  it("changes only selected fields and preserves instruction whitespace", () => {
    const draft = automationDraftFromJob(job);
    expect(parseAutomationDraft({ ...draft, message: "\n  Updated instructions.\n" }, job)).toEqual({ ok: true, value: { message: "\n  Updated instructions.\n" } });
    expect(parseAutomationDraft({ ...draft, everyValue: "7", everyUnit: "day" }, job)).toEqual({ ok: true,
      value: { schedule: { kind: "every", every_ms: 604800000 } } });
  });
  it.each(["", "0", "-1", "1.5", "Infinity", "9007199254740992"])("rejects unrepresentable interval %s", everyValue => {
    expect(parseAutomationDraft({ ...automationDraftFromJob(job), everyValue }, job)).toEqual({ ok: false, error: "intervalRequired" });
  });
  it("rejects an interval that overflows during conversion to milliseconds", () => {
    expect(parseAutomationDraft({ ...automationDraftFromJob(job), everyValue: "9007199254740991", everyUnit: "day" }, job)).toEqual({ ok: false, error: "intervalRequired" });
  });
  it("retains an unchanged past one-shot timestamp including its seconds", () => {
    const current = { ...job, schedule: { kind: "at", at_ms: new Date(2020, 0, 1, 12, 30, 45).getTime() } };
    const draft = automationDraftFromJob(current);
    expect(parseAutomationDraft({ ...draft, name: "Rename only" }, current)).toEqual({ ok: true, value: { name: "Rename only" } });
    expect(parseAutomationDraft({ ...draft, atLocal: "2020-01-01T12:31" }, current, Date.now())).toEqual({ ok: false, error: "futureRequired" });
  });
  it("does not rewrite Cron expressions or timezone when editing instructions", () => {
    const current = { ...job, schedule: { kind: "cron", expr: "*/15 9-17 * * MON-FRI", tz: "Asia/Shanghai" } };
    expect(parseAutomationDraft({ ...automationDraftFromJob(current), message: "Updated" }, current)).toEqual({ ok: true, value: { message: "Updated" } });
  });
  it("limits command-trigger edits to its display name", () => {
    const current = { ...job, kind: "local_trigger", schedule: { kind: "local" }, payload: { message: "immutable trigger command" } };
    expect(parseAutomationDraft({ ...automationDraftFromJob(current), name: "New name", message: "Other command" }, current)).toEqual({ ok: true, value: { name: "New name" } });
  });
});
describe("one-shot wall clock parsing", () => {
  it.each(["", "2032-02-30T12:00", "2031-02-29T12:00", "2032-13-01T12:00", "2032-01-01T24:00", "2032-01-01T12:60", "2032-01-01T9:00", "0000-01-01T12:00"])("rejects %s", value => {
    expect(parseLocalDateTime(value)).toBeNull();
  });
  it("supports leap days and years below 100", () => {
    expect(parseLocalDateTime("2032-02-29T00:00")?.getTime()).toBe(new Date(2032, 1, 29).getTime());
    expect(parseLocalDateTime("0099-01-01T00:00")?.getFullYear()).toBe(99);
  });
});
