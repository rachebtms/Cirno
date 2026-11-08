import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ProviderParameterFields } from "@/features/settings/providers/ProviderParameterFields";
import i18n from "@/i18n";
import { ApiError } from "@/lib/api";
beforeEach(async () => {
  await i18n.changeLanguage("en");
});
const form = { extraHeaders: "", extraQuery: "", extraBody: "{}" };
it.each([
  { field: "extra_headers", key: "extraHeaders", title: "请求头" },
  { field: "extra_query", key: "extraQuery", title: "查询参数" },
] as const)(
  "explains an unknown secret mask and retries the corrected $field",
  async ({ field, key, title }) => {
    await i18n.changeLanguage("zh-CN");
    const save = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(400, `${field}.X-Token: Input should be a valid string`))
      .mockResolvedValue(undefined);
    render(
      <ProviderParameterFields
        inherit
        fields={[field]}
        form={form}
        onChange={vi.fn()}
        onSave={save}
      />,
    );
    const editor = screen.getByRole("textbox", { name: title });
    fireEvent.change(editor, { target: { value: '{"X-Token":"••••••••"}' } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("掩码没有对应的已保存密钥");
    expect(editor).toHaveValue('{"X-Token":"••••••••"}');
    fireEvent.change(editor, { target: { value: '{"X-Token":"fixture-value"}' } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "保存" })));
    expect(save).toHaveBeenLastCalledWith({ [key]: '{"X-Token":"fixture-value"}' });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  },
);
it("prevents saving invalid objects and non-string header values", () => {
  const save = vi.fn();
  render(
    <ProviderParameterFields
      fields={["extra_headers"]}
      form={form}
      onChange={vi.fn()}
      onSave={save}
    />,
  );
  const editor = screen.getByRole("textbox", { name: "Headers" });
  for (const value of ["broken", "[]", '{"X-Route":123}']) {
    fireEvent.change(editor, { target: { value } });
    expect(editor).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  }
  expect(save).not.toHaveBeenCalled();
});
it("keeps an unsaved draft on a failed request and permits retrying without changing it", async () => {
  let reject!: (error: Error) => void;
  const save = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise<void>((_, fail) => {
          reject = fail;
        }),
    )
    .mockResolvedValue(undefined);
  render(
    <ProviderParameterFields
      fields={["extra_body"]}
      form={form}
      onChange={vi.fn()}
      onSave={save}
    />,
  );
  const editor = screen.getByRole("textbox", { name: "Body parameters" });
  fireEvent.change(editor, { target: { value: '{"watermark":false}' } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(editor).toBeDisabled();
  await act(async () => reject(new Error("Connection lost")));
  expect(await screen.findByRole("alert")).toHaveTextContent("Connection lost");
  expect(editor).toHaveValue('{"watermark":false}');
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
});
it("edits provider draft parameters inline without making a persistence request", () => {
  const change = vi.fn();
  render(
    <ProviderParameterFields fields={["extra_headers"]} form={form} onChange={change} draft />,
  );
  fireEvent.change(screen.getByRole("textbox", { name: "Headers" }), {
    target: { value: '{"X-Route":"research"}' },
  });
  expect(change).toHaveBeenLastCalledWith({ extraHeaders: '{"X-Route":"research"}' });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
