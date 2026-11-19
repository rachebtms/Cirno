import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ProviderParameterFields } from "@/features/settings/providers/ProviderParameterFields";

const form = { extraHeaders: "", extraBody: "", extraQuery: "" };
function deferred() {
  let resolve!: () => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<void>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
afterEach(cleanup);

it("submits an explicit request-parameter save once before the pending render", async () => {
  const pending = deferred(), save = vi.fn(() => pending.promise);
  render(<ProviderParameterFields fields={["extra_headers"]} form={form} onChange={vi.fn()} onSave={save} />);
  fireEvent.change(screen.getByRole("textbox", { name: "Headers" }), { target: { value: '{"X-Route":"research"}' } });
  const button = screen.getByRole("button", { name: "Save" });
  act(() => { fireEvent.click(button); fireEvent.click(button); });
  await act(async () => { pending.resolve(); });
  expect(save).toHaveBeenCalledTimes(1);
  expect(save).toHaveBeenCalledWith({ extraHeaders: '{"X-Route":"research"}' });
});

it.each([
  ["extra_headers", "Headers", '{"Authorization":"old-preset-secret"}'],
  ["extra_query", "Query parameters", '{"api_key":"old-preset-secret"}'],
  ["extra_body", "Body parameters", '{"custom":"old-preset-value"}'],
] as const)("keeps an unsaved %s draft out of another preset with the same saved value", (field, title, draft) => {
  const save = vi.fn(async () => {}), change = vi.fn();
  const { rerender } = render(<ProviderParameterFields owner="primary" fields={[field]} form={form} onChange={change} onSave={save} />);
  fireEvent.change(screen.getByRole("textbox", { name: title }), { target: { value: draft } });
  rerender(<ProviderParameterFields owner="backup" fields={[field]} form={form} onChange={change} onSave={save} />);
  expect(screen.getByRole("textbox", { name: title })).toHaveValue("");
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  expect(save).not.toHaveBeenCalled();
});

it.each([true, false])("isolates a retired parameter save from the new owner's pending save (success: %s)", async success => {
  const old = deferred(), current = deferred();
  const saveOld = vi.fn(() => old.promise), saveCurrent = vi.fn(() => current.promise);
  const { rerender } = render(<ProviderParameterFields owner="primary" fields={["extra_headers"]} form={form} onChange={vi.fn()} onSave={saveOld} />);
  fireEvent.change(screen.getByRole("textbox", { name: "Headers" }), { target: { value: '{"X-Route":"old"}' } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  rerender(<ProviderParameterFields owner="backup" fields={["extra_headers"]} form={form} onChange={vi.fn()} onSave={saveCurrent} />);
  const input = screen.getByRole("textbox", { name: "Headers" });
  expect(input).toBeEnabled();
  fireEvent.change(input, { target: { value: '{"X-Route":"current"}' } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await act(async () => { if (success) old.resolve(); else old.reject(new Error("Retired preset error")); });
  expect(input).toBeDisabled();
  expect(input).toHaveValue('{"X-Route":"current"}');
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await act(async () => { current.resolve(); });
  expect(input).toBeEnabled();
  expect(saveCurrent).toHaveBeenCalledExactlyOnceWith({ extraHeaders: '{"X-Route":"current"}' });
});

it("preserves an explicit draft and failure while its owner remains selected", async () => {
  const save = vi.fn().mockRejectedValueOnce(new Error("Save failed")).mockResolvedValueOnce(undefined);
  const { rerender } = render(<ProviderParameterFields owner="primary" fields={["extra_headers"]} form={form} onChange={vi.fn()} onSave={save} />);
  fireEvent.change(screen.getByRole("textbox", { name: "Headers" }), { target: { value: '{"X-Route":"research"}' } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save" })); });
  rerender(<ProviderParameterFields owner="primary" fields={["extra_headers"]} form={{ ...form }} onChange={vi.fn()} onSave={save} />);
  expect(screen.getByRole("textbox", { name: "Headers" })).toHaveValue('{"X-Route":"research"}');
  expect(screen.getByRole("alert")).toHaveTextContent("Save failed");
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save" })); });
  expect(save).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
