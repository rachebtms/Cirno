import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { ComponentProps } from "react";
import type { CirnoClient } from "@/lib/cirno-client";
import { WorkspaceDialogs } from "@/app/WorkspaceDialogs";

type Props = ComponentProps<typeof WorkspaceDialogs>;
function props(client: CirnoClient, owner = client) {
  return { workspaceState: { client, pendingDelete: { owner, items: [{ key: "a", label: "Research" }] }, restartToast: null },
    navigationActions: { onConfirmDelete: vi.fn(), onCancelDelete: vi.fn(), deleteBusy: false, deleteError: null } } as unknown as Props;
}
it("omits a confirmation owned by a retired connection", () => {
  render(<WorkspaceDialogs {...props({} as CirnoClient, {} as CirnoClient)} />);
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});
it("connects the current dialog to its owned confirm and cancel actions", async () => {
  const user = userEvent.setup(), value = props({} as CirnoClient);
  render(<WorkspaceDialogs {...value} />);
  await screen.findByRole("alertdialog");
  await user.click(screen.getByRole("button", { name: "Delete" }));
  expect(value.navigationActions.onConfirmDelete).toHaveBeenCalledOnce();
  expect(value.navigationActions.onCancelDelete).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(value.navigationActions.onCancelDelete).toHaveBeenCalled();
});
