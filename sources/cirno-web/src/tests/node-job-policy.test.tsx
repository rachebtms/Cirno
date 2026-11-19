import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { NodeJobSettings } from "@/features/settings/nodes/ui/NodeJobSettings";
import type { NodesController } from "@/features/settings/nodes/model/useNodes";
import type { CirnoClient } from "@/lib/cirno-client";

it("autosaves zero values, keeps a failed draft and never renders a Save button", async () => {
  let fail = true;
  const save = vi.fn(async () => { if (fail) throw new Error("Could not save monitoring settings"); });
  const nodes = { jobSettings: { poll_interval_seconds: 60, retention_days: 30 }, saveJobSettings: save } as unknown as NodesController;
  render(<NodeJobSettings nodes={nodes} client={{} as CirnoClient} />);
  const interval = screen.getByRole("spinbutton", { name: "Automatic SSH check interval (seconds)" });
  fireEvent.change(interval, { target: { value: "0" } });
  fireEvent.blur(interval);
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not save monitoring settings");
  expect(interval).toHaveValue(0);
  fail = false;
  fireEvent.blur(interval);
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(save).toHaveBeenCalledWith({ poll_interval_seconds: 0 });
  const retention = screen.getByRole("spinbutton", { name: "Finished record retention (days)" });
  fireEvent.change(retention, { target: { value: "0" } });
  await act(async () => fireEvent.blur(retention));
  expect(save).toHaveBeenCalledWith({ retention_days: 0 });
  expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
});

it("retires a failed autosave draft when switching connected servers", async () => {
  const first = { jobSettings: { poll_interval_seconds: 60, retention_days: 30 },
    saveJobSettings: vi.fn().mockRejectedValue(new Error("Old settings failed")) } as unknown as NodesController;
  const next = { jobSettings: { poll_interval_seconds: 120, retention_days: 14 }, saveJobSettings: vi.fn() } as unknown as NodesController;
  const view = render(<NodeJobSettings nodes={first} client={{} as CirnoClient} />);
  const name = "Finished record retention (days)";
  fireEvent.change(screen.getByRole("spinbutton", { name }), { target: { value: "99" } });
  fireEvent.blur(screen.getByRole("spinbutton", { name }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Old settings failed");
  view.rerender(<NodeJobSettings nodes={next} client={{} as CirnoClient} />);
  expect(screen.getByRole("spinbutton", { name })).toHaveValue(14);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await act(async () => fireEvent.blur(screen.getByRole("spinbutton", { name })));
  expect(next.saveJobSettings).not.toHaveBeenCalled();
});
it("releases a retired autosave busy state without letting it unlock a current save", async () => {
  let finishOld!: () => void, finishNew!: () => void;
  const first = { jobSettings: { poll_interval_seconds: 60, retention_days: 30 },
    saveJobSettings: vi.fn(() => new Promise<void>(resolve => { finishOld = resolve; })) } as unknown as NodesController;
  const next = { jobSettings: { poll_interval_seconds: 120, retention_days: 14 },
    saveJobSettings: vi.fn(() => new Promise<void>(resolve => { finishNew = resolve; })) } as unknown as NodesController;
  const view = render(<NodeJobSettings nodes={first} client={{} as CirnoClient} />);
  const name = "Finished record retention (days)";
  fireEvent.change(screen.getByRole("spinbutton", { name }), { target: { value: "99" } });
  fireEvent.blur(screen.getByRole("spinbutton", { name }));
  expect(screen.getByRole("spinbutton", { name })).toBeDisabled();
  view.rerender(<NodeJobSettings nodes={next} client={{} as CirnoClient} />);
  expect(screen.getByRole("spinbutton", { name })).toBeEnabled();
  fireEvent.change(screen.getByRole("spinbutton", { name }), { target: { value: "7" } });
  fireEvent.blur(screen.getByRole("spinbutton", { name }));
  expect(next.saveJobSettings).toHaveBeenCalledWith({ retention_days: 7 });
  await act(async () => finishOld());
  expect(screen.getByRole("spinbutton", { name })).toBeDisabled();
  await act(async () => finishNew());
  expect(screen.getByRole("spinbutton", { name })).toBeEnabled();
});
