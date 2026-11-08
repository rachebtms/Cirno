import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { TraceInspector } from "@/features/trace/TraceInspector";
import type { TraceEvent } from "@/features/trace/contracts";
import * as clipboard from "@/lib/clipboard";

const event: TraceEvent = { id: 1, kind: "request", created_ms: 1, summary: "model", status: "done", session_key: "websocket:router", turn_id: "turn" };
it("copies exactly the displayed message page and reports a clipboard rejection", async () => {
  const copy = vi.spyOn(clipboard, "copyTextToClipboard").mockResolvedValueOnce(true).mockResolvedValueOnce(false);
  const messages = [{ role: "system", content: "Long context begins here" }];
  const props = { event, busy: false, close: vi.fn(), more: vi.fn() };
  const { rerender } = render(<TraceInspector {...props} detail={{ messages, total: 50, tools: [{ name: "files.read" }] }} />);
  fireEvent.click(screen.getByRole("button", { name: "Copy displayed details" }));
  await screen.findByRole("button", { name: "Copied" });
  expect(copy).toHaveBeenCalledWith(JSON.stringify(messages, null, 2));
  rerender(<TraceInspector {...props} detail={{ messages: [...messages, { role: "user", content: "Another page" }], total: 50, tools: [{ name: "files.read" }] }} />);
  expect(screen.getByRole("button", { name: "Copy displayed details" })).toBeEnabled();
  fireEvent.click(screen.getByRole("tab", { name: "Tools" }));
  fireEvent.click(screen.getByRole("button", { name: "Copy displayed details" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Copy failed");
  copy.mockRestore();
});
