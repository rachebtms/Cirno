import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThreadMessages } from "@/components/thread/ThreadMessages";

vi.mock("@/components/MarkdownText", () => ({ MarkdownText: ({ content }: { content: string }) => <p>{content}</p> }));
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("persistent message timestamps", () => {
  it("uses human creation and assistant completion times without a menu or hover", () => {
    const createdAt = Date.UTC(2026, 8, 23, 12);
    const completedAt = Date.UTC(2026, 8, 24, 14, 32);
    const { container } = render(<ThreadMessages messages={[
      { id: "u", role: "user", content: "Question", createdAt },
      { id: "a", role: "assistant", content: "Answer", createdAt, completedAt },
    ]} />);
    const times = container.querySelectorAll<HTMLTimeElement>("time[data-message-timestamp]");
    expect(times).toHaveLength(2);
    expect(times[0]).toHaveAttribute("datetime", new Date(createdAt).toISOString());
    expect(times[1]).toHaveAttribute("datetime", new Date(completedAt).toISOString());
    expect(times[0]).toBeVisible();
    expect(times[1]).toBeVisible();
    const groups = screen.getAllByRole("group", { name: "Message actions" });
    expect(times[0].compareDocumentPosition(within(groups[0]).getByRole("button", { name: "Copy" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(groups[1]).getByRole("button", { name: "Copy" }).compareDocumentPosition(times[1]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container.querySelector("[data-message-block-menu]")).toBeNull();
  });

  it("falls back to creation time and omits invalid timestamps", () => {
    const createdAt = Date.UTC(2026, 8, 22);
    const { container } = render(<ThreadMessages messages={[
      { id: "a", role: "assistant", content: "Answer", createdAt, completedAt: NaN },
      { id: "b", role: "assistant", content: "Unknown", createdAt: NaN },
    ]} />);
    const times = container.querySelectorAll("time");
    expect(times).toHaveLength(1);
    expect(times[0]).toHaveAttribute("datetime", new Date(createdAt).toISOString());
  });
});
