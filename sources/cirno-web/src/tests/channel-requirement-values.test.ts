import { expect, it } from "vitest";
import type { ChannelConfigField } from "@/channel-plugins/catalog";
import { channelRequirementErrors, channelServerValidationErrors } from "@/features/channels/model/fieldValidation";

it.each([
  ["bool", "false", false],
  ["bool", "true", true],
  ["bool", "on", true],
  ["bool", "off", false],
  ["list", ", , ", false],
  ["list", "one, two", true],
  ["string", " \t ", false],
  ["secret", "false", true],
  ["int", "0", true],
  ["json", "{}", false],
  ["json", '{"key": "value"}', true],
])("checks a required %s value %s in simple and alternative groups", (kind, value, configured) => {
  const fields: ChannelConfigField[] = [
    { key: "account.value", label: "Value", kind: String(kind), secret: kind === "secret" },
    { key: "companion", label: "Companion" },
    { key: "fallback", label: "Fallback" },
  ];
  for (const alternatives of [[["account.value"]], [["account.value", "companion"], ["fallback"]]]) {
    const errors = channelRequirementErrors(fields, [{ alternatives }],
      { "account.value": String(value), companion: "present" }, new Set(), new Set(), "Required");
    expect(Object.keys(errors).length === 0).toBe(configured);
  }
});

it("retains saved secrets as present until explicitly cleared", () => {
  const fields = [{ key: "token", label: "Token", kind: "secret", secret: true }];
  const requirements = [{ alternatives: [["token"]] }];
  expect(channelRequirementErrors(fields, requirements, {}, new Set(["token"]), new Set(), "Required")).toEqual({});
  expect(channelRequirementErrors(fields, requirements, {}, new Set(["token"]), new Set(["token"]), "Required")).toEqual({ token: "Required" });
});

it("attaches nested server errors to the declared path without confusing sibling fields", () => {
  const fields = [
    { key: "channels.plugin.account.token", label: "Account token" },
    { key: "channels.plugin.token", label: "Root token" },
    { key: "channels.plugin.backup.token", label: "Backup token" },
  ];
  expect(channelServerValidationErrors(fields, ["account.token"], "Required")).toEqual({
    "channels.plugin.account.token": "Required",
  });
  expect(channelServerValidationErrors(fields, ["token"], "Required")).toEqual({
    "channels.plugin.token": "Required",
  });
  expect(channelServerValidationErrors(fields, ["channels.plugin.backup.token"], "Required")).toEqual({
    "channels.plugin.backup.token": "Required",
  });
});

it("matches server selection of the most completed alternative on equal missing counts", () => {
  const fields = ["password", "accessToken", "deviceId"].map((key) => ({ key, label: key, secret: key !== "deviceId" }));
  expect(channelRequirementErrors(fields,
    [{ alternatives: [["password"], ["accessToken", "deviceId"]] }],
    {}, new Set(["accessToken"]), new Set(), "Required")).toEqual({ deviceId: "Required" });
});
