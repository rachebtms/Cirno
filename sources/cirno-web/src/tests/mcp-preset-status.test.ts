import { expect, it } from "vitest";
import { mcpPresetStatusLabel } from "@/features/settings/apps/model/status";

it.each([
  ["authorization_required", "Needs sign-in"],
  ["missing_credentials", "Needs key"],
  ["configured", "Configured"],
  ["missing_dependency", "Needs dependency"],
])("describes MCP state %s without treating an authorization requirement as disabled", (status, expected) => {
  expect(mcpPresetStatusLabel(status, (_key, fallback) => fallback)).toBe(expected);
});
