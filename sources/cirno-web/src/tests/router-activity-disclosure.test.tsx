import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThreadMessages } from "@/components/thread/ThreadMessages";
import { preloadMarkdownText } from "@/components/MarkdownText";
import type { UIMessage } from "@/lib/contracts/messages";

const base = 1_800_000_000_000;
const heartbeat = (id: string, start: number): UIMessage => ({
  id, turnId: id, role: "user", content: `Inspect ${id}`, createdAt: start,
  inputOrigin: { kind: "heartbeat", label: "Heartbeat" },
});
const messages: UIMessage[] = [
  { id: "owner", role: "user", content: "Keep an eye on work", createdAt: base - 1000 },
  heartbeat("a", base),
  { id: "a-reasoning", turnId: "a", role: "assistant", content: "", reasoning: "First inspection", createdAt: base + 3000, latencyMs: 3000 },
  heartbeat("b", base + 3_600_000),
  { id: "b-reasoning", turnId: "b", role: "assistant", content: "", reasoning: "Second inspection", createdAt: base + 3_605_000, latencyMs: 5000 },
];

afterEach(() => { vi.useRealTimers(); });

describe("Router shared Working / Worked disclosure", () => {
  it("shows one completed header and retains ordered heartbeat details on expansion", async () => {
    await preloadMarkdownText();
    const { container } = render(<ThreadMessages activityGrouping="conversation" assistantBubbles defaultActivityCollapsed messages={messages} />);
    expect(screen.getAllByRole("button", { name: /^Worked/ })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Worked for 8s" })).toHaveAttribute("aria-expanded", "false");
    expect(container.querySelectorAll("[data-system-input]")).toHaveLength(0);
    expect([...container.querySelectorAll<HTMLElement>("[data-user-prompt-id]")]
      .map(element => element.dataset.userPromptId)).toEqual(["owner", "a", "b"]);
    fireEvent.click(screen.getByRole("button", { name: "Worked for 8s" }));
    const details = screen.getByTestId("agent-activity-content");
    expect(within(details).getAllByRole("button", { name: "Heartbeat" })).toHaveLength(2);
    expect(within(details).getByText("First inspection")).toBeInTheDocument();
    expect(within(details).getByText("Second inspection")).toBeInTheDocument();
    fireEvent.click(within(details).getAllByRole("button", { name: "Heartbeat" })[1]);
    expect(await within(details).findByText("Inspect b")).toBeVisible();
  });

  it("reuses the existing disclosure before the next heartbeat produces its first delta", () => {
    vi.useFakeTimers();
    vi.setSystemTime(base + 7_202_000);
    const view = render(<ThreadMessages activityGrouping="conversation" assistantBubbles defaultActivityCollapsed messages={messages} />);
    const header = screen.getByRole("button", { name: "Worked for 8s" });
    fireEvent.click(header);
    const live = [...messages, heartbeat("c", base + 7_200_000)];
    view.rerender(<ThreadMessages activityGrouping="conversation" assistantBubbles defaultActivityCollapsed messages={live} isStreaming activeTurnId="c" />);
    expect(screen.getAllByRole("button", { name: /^Working/ })).toHaveLength(1);
    expect(screen.getByRole("button", { name: /^Working for 10s/ })).toBe(header);
    expect(header).toHaveAttribute("aria-expanded", "true");
    expect(screen.queryByRole("button", { name: /^Worked/ })).not.toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(1000); });
    expect(header).toHaveAccessibleName(/^Working for 11s/);
    view.rerender(<ThreadMessages activityGrouping="conversation" assistantBubbles defaultActivityCollapsed messages={[...live,
      { id: "c-reasoning", turnId: "c", role: "assistant", content: "", reasoning: "Third inspection", createdAt: base + 7_203_000, latencyMs: 3000 },
    ]} />);
    expect(screen.getByRole("button", { name: /^Worked for 11s/ })).toBe(header);
  });

  it("splits activity at delivered replies and owner messages", async () => {
    await preloadMarkdownText();
    render(<ThreadMessages activityGrouping="conversation" assistantBubbles defaultActivityCollapsed messages={[...messages,
      { id: "reply", role: "assistant", content: "Everything is healthy", createdAt: base + 3_606_000 },
      heartbeat("c", base + 7_200_000),
      { id: "next", role: "user", content: "Check another server", createdAt: base + 7_201_000 },
      heartbeat("d", base + 7_202_000),
    ]} />);
    expect(screen.getAllByRole("button", { name: /^Worked/ })).toHaveLength(3);
    expect(await screen.findByText("Everything is healthy")).toBeVisible();
    expect(screen.getByText("Check another server")).toBeVisible();
  });

  it("preserves the Worker timeline presentation", () => {
    const { container } = render(<ThreadMessages messages={messages} />);
    expect(container.querySelectorAll("[data-system-input]")).toHaveLength(2);
  });

  it("retains linked task results for folded heartbeat inputs", () => {
    render(<ThreadMessages activityGrouping="conversation" assistantBubbles defaultActivityCollapsed messages={messages}
      afterUserMessage={message => <div>{`Linked result for ${message.id}`}</div>} />);
    fireEvent.click(screen.getByRole("button", { name: "Worked for 8s" }));
    const details = screen.getByTestId("agent-activity-content");
    expect(within(details).getByText("Linked result for a")).toBeVisible();
    expect(within(details).getByText("Linked result for b")).toBeVisible();
  });
});
