import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { CirnoClient } from "@/lib/cirno-client";
import { TerminalTab } from "@/features/terminal/TerminalTab";

const state = vi.hoisted(() => ({ nodeId: "", connect: vi.fn() }));
vi.mock("@/features/terminal/model/useTerminalHosts", () => ({
  useTerminalHosts: () => ({ nodes: [{ id: "remote", name: "Remote node" }], error: "", retry: vi.fn() }),
}));
vi.mock("@/features/terminal/model/useTerminalSession", () => ({
  useTerminalSession: ({ nodeId }: { nodeId: string }) => {
    state.nodeId = nodeId;
    return { host: { current: null }, phase: "idle", started: false, errors: [], connect: state.connect };
  },
}));
async function mount() {
  const user = userEvent.setup();
  const props = { client: {} as CirnoClient, terminalKey: "tab", active: true, onCloseReady: vi.fn() };
  const view = render(<TerminalTab {...props} />);
  await user.click(screen.getByRole("button", { name: /Terminal host/ }));
  await user.click(await screen.findByRole("option", { name: "Remote node" }));
  expect(state.nodeId).toBe("remote");
  return { ...view, props };
}
it("resets a selected SSH host when its connected server changes", async () => {
  const view = await mount();
  view.rerender(<TerminalTab {...view.props} client={{} as CirnoClient} />);
  expect(state.nodeId).toBe("local");
  expect(screen.getByRole("button", { name: /Terminal host/ })).toHaveTextContent("Local server");
});
it("retains its selected SSH host on an ordinary same-server render", async () => {
  const view = await mount();
  view.rerender(<TerminalTab {...view.props} active={false} />);
  expect(state.nodeId).toBe("remote");
});
