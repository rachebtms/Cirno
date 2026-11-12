import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ContextCompactionNotice } from "@/components/thread/ContextCompactionNotice";
import { projectWebuiThreadMessages } from "@/lib/thread-display-projection";
import { decodeNotification } from "../../packages/client-events/notifications";
import { projectThreadEvents } from "@/lib/thread-event-projection";
import { parseWebuiThreadPayload } from "@/lib/api";
import type { UIMessage } from "@/lib/contracts/messages";

function attempt(id: string, phase: "failed" | "succeeded"): UIMessage {
  return { id, role: "assistant", kind: "compaction", content: "", createdAt: 100,
    compaction: { id, phase, reason: "idle", ...(phase === "failed" ? { error: "ReadTimeout: no response for 120 seconds" } : {}) } };
}

describe("compaction attempts", () => {
  it("keeps task success and learning failure separate through persisted replay", () => {
    const failure = { source: "source-original", error: "Could not save USER.md", saved: [
      { id: "memory:0", kind: "memory", label: "Measured 43.2 K" },
    ], pending: [{ id: "document:0", kind: "document", label: "USER.md" }] };
    const event = { event: "context_compaction", chat_id: "chat", compaction_id: "partial", phase: "succeeded", learning_failure: failure };
    expect(decodeNotification(event)).toEqual(event);
    expect(decodeNotification({ ...event, learning_failure: { ...failure, pending: "invalid" } })).toBeNull();
    const replay = parseWebuiThreadPayload({ schemaVersion: 3, projection: "events", events: [event] }).events;
    const compaction = projectThreadEvents(replay)[0].compaction!;
    expect(compaction.phase).toBe("succeeded");
    expect(compaction.learning_failure).toEqual(failure);
    render(<ContextCompactionNotice compaction={compaction} />);
    expect(screen.getByText("Checkpoint saved; learning incomplete")).toBeInTheDocument();
    expect(screen.getByText("Memory: Measured 43.2 K")).toBeInTheDocument();
    expect(screen.getByText("Document: USER.md")).toBeInTheDocument();
    expect(screen.getByText("/consolidate retry source-original")).toBeInTheDocument();
  });
  it("groups consecutive failures with the final success and exposes each error", () => {
    const raw = [attempt("one", "failed"), attempt("two", "failed"), attempt("three", "succeeded")];
    const grouped = projectWebuiThreadMessages(raw);
    expect(grouped).toHaveLength(1);
    expect(raw).toHaveLength(3);
    expect(grouped[0].compaction?.attempts).toHaveLength(3);
    expect(projectWebuiThreadMessages(grouped)).toEqual(grouped);
    const { container } = render(<ContextCompactionNotice compaction={grouped[0].compaction!} />);
    expect(screen.getByText("3 attempts")).toBeInTheDocument();
    expect(container.querySelector("details")).not.toHaveAttribute("open");
    fireEvent.click(container.querySelector("summary")!);
    expect(screen.getAllByText("ReadTimeout: no response for 120 seconds")).toHaveLength(2);
    expect(screen.getByText(/Attempt 3/)).toHaveTextContent("Context automatically compacted after inactivity");
  });

  it("starts another group after user activity, success, or a different trigger", () => {
    const user: UIMessage = { id: "user", role: "user", content: "continue", createdAt: 101 };
    expect(projectWebuiThreadMessages([attempt("a", "failed"), user, attempt("b", "succeeded")])).toHaveLength(3);
    expect(projectWebuiThreadMessages([attempt("a", "succeeded"), attempt("b", "failed")])).toHaveLength(2);
    const manual = attempt("b", "succeeded");
    manual.compaction!.reason = "manual";
    expect(projectWebuiThreadMessages([attempt("a", "failed"), manual])).toHaveLength(2);
  });

  it("preserves error reasons and post-compaction usage in stored event replay", () => {
    const event = { event: "context_compaction", chat_id: "chat", compaction_id: "one", phase: "succeeded",
      reason: "idle", context_tokens: 1200, context_window_tokens: 512000, context_estimated: true };
    expect(decodeNotification(event)).toEqual(event);
    const events = parseWebuiThreadPayload({ schemaVersion: 3, projection: "events", events: [event] }).events;
    expect(projectThreadEvents(events)[0].compaction).toMatchObject({ context_tokens: 1200, context_window_tokens: 512000, context_estimated: true });
    expect(decodeNotification({ ...event, context_tokens: -1 })).toBeNull();
    const failed = { ...event, phase: "failed", error: "ReadTimeout: model unavailable" };
    const replay = parseWebuiThreadPayload({ schemaVersion: 3, projection: "events", events: [failed] }).events;
    expect(projectThreadEvents(replay)[0].compaction?.error).toBe(failed.error);
  });
});

it("explains an evidence fallback instead of claiming a model summary succeeded", () => {
  const event = decodeNotification({ event: "context_compaction", chat_id: "chat", compaction_id: "fallback", phase: "succeeded", evidence_checkpoint: true });
  expect(event).not.toBeNull();
  render(<ContextCompactionNotice compaction={{ id: "fallback", phase: "succeeded", evidence_checkpoint: true }} />);
  expect(screen.getByText("Evidence checkpoint saved")).toBeInTheDocument();
  expect(screen.getByText(/complete source records remain archived/)).toBeInTheDocument();
});

function retryEvent(outcome: "completed" | "no_updates" | "not_found" | "incomplete" = "completed") {
  return { event: "context_compaction", chat_id: "chat", compaction_id: "retry", phase: outcome === "incomplete" ? "failed" : "succeeded", reason: "manual",
    learning_retry: { source: "source-retained", mode: "replay", outcome, model_called: false,
      requested: [{ id: "document:0", kind: "document", label: "USER.md" }],
      saved: outcome === "completed" ? [{ id: "memory:0", kind: "memory", label: "Measured 43.2 K" }, { id: "document:0", kind: "document", label: "USER.md" }] : [],
      previously_saved: outcome === "completed" ? [{ id: "memory:0", kind: "memory", label: "Measured 43.2 K" }] : [],
      pending: outcome === "incomplete" ? [{ id: "document:0", kind: "document", label: "USER.md" }] : [],
    } };
}

it("replays detailed learning recovery as a consolidation report with acknowledged writes", () => {
  const event = retryEvent();
  expect(decodeNotification(event)).toEqual(event);
  expect(decodeNotification({ ...event, learning_retry: { ...event.learning_retry, saved: "invalid" } })).toBeNull();
  const events = parseWebuiThreadPayload({ schemaVersion: 3, projection: "events", events: [event] }).events;
  const messages = projectThreadEvents(events);
  expect(messages).toHaveLength(1);
  expect(messages[0].kind).toBe("compaction");
  expect(messages[0].content).toBe("");
  render(<ContextCompactionNotice compaction={messages[0].compaction!} />);
  expect(screen.getByText("Learning retry completed")).toBeInTheDocument();
  expect(screen.getByText("Newly completed: 1; previously completed: 1.")).toBeInTheDocument();
  expect(screen.getByText("Document: USER.md")).toBeInTheDocument();
  expect(screen.getByText("No model request was made for this retry.")).toBeInTheDocument();
  expect(screen.getByText("source-retained")).toBeInTheDocument();
});

it("explains empty regeneration and separates original proposals from saved updates", () => {
  const event = retryEvent("no_updates");
  event.learning_retry.mode = "regenerate";
  event.learning_retry.model_called = true;
  const message = projectThreadEvents(parseWebuiThreadPayload({ schemaVersion: 3, projection: "events", events: [event] }).events)[0];
  render(<ContextCompactionNotice compaction={message.compaction!} />);
  expect(screen.getByText("Retry produced no updates")).toBeInTheDocument();
  expect(screen.getByText("Newly completed: 0; previously completed: 0.")).toBeInTheDocument();
  expect(screen.getByText("No updates were generated; the original proposals were not saved by this extraction.")).toBeInTheDocument();
  expect(screen.getByText("Original proposals (not a list of saved updates)")).toBeInTheDocument();
  expect(screen.getByText("A model request was made for this retry.")).toBeInTheDocument();
});

it("does not merge learning-only recovery into an unrelated checkpoint attempt", () => {
  const retry = projectThreadEvents(parseWebuiThreadPayload({ schemaVersion: 3, projection: "events", events: [retryEvent()] }).events)[0];
  const original = attempt("original", "failed");
  original.compaction!.reason = "manual";
  expect(projectWebuiThreadMessages([original, retry])).toHaveLength(2);
});
