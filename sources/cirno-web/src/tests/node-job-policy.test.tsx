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
