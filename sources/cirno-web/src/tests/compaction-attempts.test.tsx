import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ContextCompactionNotice } from "@/components/thread/ContextCompactionNotice";
import { projectWebuiThreadMessages } from "@/lib/thread-display-projection";
import { decodeNotification } from "../../packages/client-events/notifications";
import { projectThreadEvents } from "@/lib/thread-event-projection";
import { parseWebuiThreadPayload } from "@/lib/api";
import type { UIMessage } from "@/lib/types";

function attempt(id: string, phase: "failed" | "succeeded"): UIMessage {
  return { id, role: "assistant", kind: "compaction", content: "", createdAt: 100,
    compaction: { id, phase, reason: "idle", ...(phase === "failed" ? { error: "ReadTimeout: no response for 120 seconds" } : {}) } };
}

describe("compaction attempts", () => {
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
