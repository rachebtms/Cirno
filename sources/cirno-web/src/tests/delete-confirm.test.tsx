import { DeleteConfirm } from "@/components/DeleteConfirm";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

describe("asynchronous deletion confirmation", () => {
  it("keeps the dialog open until its owner finishes and exposes a retryable error", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    const { rerender } = render(<DeleteConfirm open title="Research" onCancel={onCancel} onConfirm={onConfirm} />);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
    rerender(<DeleteConfirm open title="Research" busy onCancel={onCancel} onConfirm={onConfirm} />);
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(onCancel).not.toHaveBeenCalled();
    rerender(<DeleteConfirm open title="Research" error="Storage unavailable" onCancel={onCancel} onConfirm={onConfirm} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Storage unavailable");
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalledTimes(2);
  });
});
