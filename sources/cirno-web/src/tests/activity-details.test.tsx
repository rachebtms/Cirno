import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it } from "vitest";
import { ReasoningRow } from "@/components/thread/activity/ReasoningRow";
import { ActivityStep } from "@/components/thread/activity/ActivityStep";
import { DEFAULT_PREFERENCES, readPreferences, writePreferences } from "@/features/preferences/store";
import { setAppLanguage } from "@/i18n";
beforeEach(async () => { localStorage.clear(); await setAppLanguage("en"); });
afterEach(cleanup);
it("allows a brief reasoning row to expand its complete multiline text", () => {
  const text = "First line\nSecond line\n" + "Full detail. ".repeat(60);
  render(<ReasoningRow text={text} streaming={false} />);
  expect(screen.queryByTestId("activity-step-details")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Expand step" }));
  expect(screen.getByTestId("activity-step-details").textContent).toBe(text);
});
it("keeps reasoning and tool detail preferences independent and persistent", () => {
  writePreferences({ ...DEFAULT_PREFERENCES, reasoningDetailMode: "detailed", toolDetailMode: "brief" });
  expect(readPreferences().reasoningDetailMode).toBe("detailed");
  const view = render(<><ReasoningRow text="First line\nSecond line" streaming={false} /><ActivityStep label="Tool summary" detail="Line one\nLine two" /></>);
  expect(screen.getAllByTestId("activity-step-details")).toHaveLength(1);
  view.unmount();
  writePreferences({ ...DEFAULT_PREFERENCES, reasoningDetailMode: "brief", toolDetailMode: "detailed" });
  render(<><ReasoningRow text="First line\nSecond line" streaming={false} /><ActivityStep label="Tool summary" detail="Line one\nLine two" /></>);
  expect(screen.getAllByTestId("activity-step-details")).toHaveLength(1);
  expect(screen.getByTestId("activity-step-details")).toHaveTextContent("Tool summary");
});

it("expands the complete Node command and output while keeping a short summary", async () => {
  const { AgentActivityCluster } = await import("@/components/thread/AgentActivityCluster");
  const command = "cd /srv/research\npython experiment.py --seed 42\nprintf 'finished'";
  const event = { phase: "end" as const, call_id: "node-call", name: "nodes__execute", arguments: { node_id: "lab", command }, result: "epoch 1\nepoch 2\nfinished" };
  render(<AgentActivityCluster expanded messages={[{ id: "node", role: "tool", kind: "trace", content: "", traces: [`nodes__execute(${JSON.stringify(event.arguments)})`], createdAt: 1, toolEvents: [event] }]} isTurnStreaming={false} hasBodyBelow={false} />);
  const buttons = screen.getAllByRole("button", { name: "Expand step" });
  fireEvent.click(buttons[0]);
  const details = screen.getByTestId("activity-step-details");
  expect(details).toHaveTextContent("experiment.py --seed 42");
  expect(details.textContent).toContain(command);
  expect(details.textContent).toContain("epoch 1\nepoch 2\nfinished");
});
