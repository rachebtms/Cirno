import { describe, expect, it } from "vitest";
import { sshSessionDraft, sshSessionValues } from "@/components/ssh/session";
describe("SSH environment drafts", () => {
  it("roundtrips multiline literal values and preserves property names", () => {
    const saved = { working_directory: "~/work", init_script: "~/activate.sh", environment: JSON.parse('{"CUDA_VISIBLE_DEVICES":"2","__proto__":"literal\\nvalue"}') };
    expect(sshSessionValues(sshSessionDraft(saved))).toEqual(saved);
  });
  it("rejects duplicate or invalid names instead of overwriting variables", () => {
    const draft = sshSessionDraft({ working_directory: ".", environment: { CUDA_VISIBLE_DEVICES: "2" } });
    draft.environment.push({ id: "other", name: "CUDA_VISIBLE_DEVICES", value: "3" });
    expect(() => sshSessionValues(draft)).toThrow();
    draft.environment[1].name = "wrong-name";
    expect(() => sshSessionValues(draft)).toThrow();
  });
});
