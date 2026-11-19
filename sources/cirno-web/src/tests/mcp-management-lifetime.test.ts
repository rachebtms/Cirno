import { act, renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useMcpManagement } from "@/features/settings/mcp/model/useMcpManagement";
import type { McpManagementDialogProps } from "@/features/settings/mcp/model/contracts";

function options(): McpManagementDialogProps {
  return { preset: { name: "fixture", display_name: "Fixture", category: "test", description: "Fixture",
    docs_url: "", transport: "stdio", requires: "", note: "", install_supported: true, installed: true,
    configured: true, available: true, status: "configured", required_fields: [],
    tool_names: ["read", "write"], tool_count: 2, enabled_tools: ["read"], connection_summary: "fixture-mcp" },
    values: {}, actionKey: null, statusLabel: "Connected", statusTone: "success", tab: "overview", icon: null,
    onTabChange: vi.fn(), onOpenChange: vi.fn(), onFieldChange: vi.fn(), onAction: vi.fn(),
    onOAuthConnect: vi.fn(), onToolsChange: vi.fn() };
}
it("keeps an explicitly selected complete tool list distinct from wildcard capabilities", () => {
  const view = renderHook(useMcpManagement, { initialProps: options() });
  act(() => view.result.current.changeTools(["read", "write"]));
  expect(view.result.current.enabled).toEqual(["read", "write"]);
});
it.each(["connect", "remove", "refreshTools", "applyProxy", "applyTools"] as const)("does not submit %s from a retired management dialog", action => {
  const props = options(), view = renderHook(useMcpManagement, { initialProps: props });
  const invoke = view.result.current[action];
  view.unmount();
  invoke();
  expect(props.onAction).not.toHaveBeenCalled();
  expect(props.onOpenChange).not.toHaveBeenCalled();
  expect(props.onOAuthConnect).not.toHaveBeenCalled();
  expect(props.onToolsChange).not.toHaveBeenCalled();
});
it.each(["connect", "remove"] as const)("does not let a retained %s control close the dialog during a new pending action", action => {
  const props = options(), view = renderHook(useMcpManagement, { initialProps: props });
  const invoke = view.result.current[action];
  view.rerender({ ...props, actionKey: "tools:fixture" });
  invoke();
  expect(props.onAction).not.toHaveBeenCalled();
  expect(props.onOpenChange).not.toHaveBeenCalled();
});
it("does not apply an earlier tool-scope draft after the user has changed the selection", () => {
  const props = options(), view = renderHook(useMcpManagement, { initialProps: props });
  const apply = view.result.current.applyTools;
  act(() => view.result.current.clear());
  apply();
  expect(props.onToolsChange).not.toHaveBeenCalled();
});
it("preserves an intentional wildcard grant from the explicit all-tools control", () => {
  const props = options(), view = renderHook(useMcpManagement, { initialProps: props });
  act(() => view.result.current.selectAll());
  view.result.current.applyTools();
  expect(props.onToolsChange).toHaveBeenCalledWith("fixture", ["*"]);
});

it.each([
  { transport: "streamableHttp", values: { token: "replacement" }, expected: { token: "replacement", use_proxy: "false" } },
  { transport: "streamableHttp", values: { token: "replacement", use_proxy: "true" }, expected: { token: "replacement", use_proxy: "true" } },
  { transport: "stdio", values: { token: "replacement" }, expected: { token: "replacement" } },
] as const)("saves edited connection fields through the persistence action ($transport, $values)", ({ transport, values, expected }) => {
  const props = options();
  props.preset = { ...props.preset, transport, required_fields: [{ name: "token", label: "Token", secret: true, required: true, configured: true, placeholder: "" }] };
  props.values = values;
  const view = renderHook(useMcpManagement, { initialProps: props });
  view.result.current.connect();
  expect(props.onAction).toHaveBeenCalledWith("enable", "fixture", expected);
});

it("keeps blank credential drafts on the reconnect path", () => {
  const props = options();
  props.preset = { ...props.preset, transport: "streamableHttp", required_fields: [{ name: "token", label: "Token", secret: true, required: true, configured: true, placeholder: "" }] };
  props.values = { token: "   " };
  const view = renderHook(useMcpManagement, { initialProps: props });
  view.result.current.connect();
  expect(props.onAction).toHaveBeenCalledWith("reconnect", "fixture", props.values);
});

it.each(["connect", "applyProxy"] as const)("rejects a retained %s callback after connection input changes", action => {
  const props = options();
  props.preset = { ...props.preset, transport: "streamableHttp", required_fields: [{ name: "token", label: "Token", secret: true, required: true, configured: true, placeholder: "" }] };
  props.values = { token: "old-secret", use_proxy: "true" };
  const view = renderHook(useMcpManagement, { initialProps: props });
  const invoke = view.result.current[action];
  view.rerender({ ...props, values: { token: "new-secret", use_proxy: "false" } });
  invoke();
  expect(props.onAction).not.toHaveBeenCalled();
  expect(props.onOpenChange).not.toHaveBeenCalled();
  view.result.current.connect();
  expect(props.onAction).toHaveBeenCalledWith("enable", "fixture", { token: "new-secret", use_proxy: "false" });
});

it("rejects retained authorization actions after the connection preset changes", () => {
  const props = options();
  props.preset = { ...props.preset, transport: "streamableHttp", auth: "oauth" };
  const view = renderHook(useMcpManagement, { initialProps: props });
  const invoke = view.result.current.connect;
  view.rerender({ ...props, preset: { ...props.preset, configured: false } });
  invoke();
  expect(props.onOAuthConnect).not.toHaveBeenCalled();
  expect(props.onOpenChange).not.toHaveBeenCalled();
  view.result.current.connect();
  expect(props.onOAuthConnect).toHaveBeenCalledWith("fixture", false, { use_proxy: "false" });
});
