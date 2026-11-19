import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { ProviderParameterFields } from "@/features/settings/providers/ProviderParameterFields";
import { ProviderRequestOptions } from "@/features/settings/providers/ProviderRequestOptions";
import { emptyCustomProviderDraft, type ProviderForm } from "@/features/settings/providers/providerForm";

const options = [
  ["openai_codex", "Fast mode"],
  ["openai", "OpenAI web search"],
  ["xai_grok", "X Search"],
] as const;
afterEach(cleanup);

function Harness({ provider, changed }: { provider: string; changed: (patch: Partial<ProviderForm>) => void }) {
  const [form, setForm] = useState<ProviderForm>({ ...emptyCustomProviderDraft(), extraBody: '{"custom":{"retain":true}}' });
  const change = (patch: Partial<ProviderForm>) => {
    changed(patch);
    setForm(previous => ({ ...previous, ...patch }));
  };
  return <>
    <ProviderParameterFields fields={["extra_body"]} form={form} onChange={change} />
    <ProviderRequestOptions providerName={provider} form={form} onChange={change} apiConfigurable />
  </>;
}

it.each(options.flatMap(([provider, label]) => [
  { provider, label, body: '{"custom":' },
  { provider, label, body: '[{"custom":true}]' },
]))("preserves invalid $provider JSON instead of replacing it through $label", ({ provider, label, body }) => {
  const changed = vi.fn();
  render(<Harness provider={provider} changed={changed} />);
  const input = screen.getByRole("textbox", { name: "Body parameters" });
  fireEvent.change(input, { target: { value: body } });
  changed.mockClear();
  const toggle = screen.getByRole("switch", { name: label });
  fireEvent.click(toggle);
  expect(input).toHaveValue(body);
  expect(toggle).toBeDisabled();
  expect(changed).not.toHaveBeenCalled();
});

it.each(options)("re-enables %s options after JSON correction and retains unrelated fields", (provider, label) => {
  const changed = vi.fn();
  render(<Harness provider={provider} changed={changed} />);
  const input = screen.getByRole("textbox", { name: "Body parameters" });
  fireEvent.change(input, { target: { value: '{"custom":' } });
  fireEvent.change(input, { target: { value: '{"custom":{"retain":true},"include":["audit"]}' } });
  const toggle = screen.getByRole("switch", { name: label });
  expect(toggle).toBeEnabled();
  fireEvent.click(toggle);
  expect(JSON.parse((input as HTMLTextAreaElement).value)).toMatchObject({ custom: { retain: true }, include: ["audit"] });
  expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({ extraBody: expect.any(String) }));
});
