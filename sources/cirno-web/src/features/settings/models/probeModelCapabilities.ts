import type { WebUIMutationTransport } from "@/lib/api/transport";
import type { AgentSettingsDraft } from "./modelDraft";
export type CapabilityProbe = { supported: boolean | null; detail: string };
export type CapabilityResults = { image?: CapabilityProbe; video?: CapabilityProbe };

export async function probeModelCapabilities(client: WebUIMutationTransport, form: AgentSettingsDraft, presetId?: string): Promise<CapabilityResults> {
  if (form.imageInput != null && form.videoInput != null) return {};
  return client.requestMutation<CapabilityResults>("instance.action", { action: "models.probe", values: { preset_id: presetId, preset: {
    model: form.model, provider: form.provider, api: form.api,
    image_input: form.imageInput ?? null, video_input: form.videoInput ?? null,
    reasoning_effort: form.reasoningEffort || null,
    extra_headers: form.extraHeaders.trim() ? JSON.parse(form.extraHeaders) : null,
    extra_body: form.extraBody.trim() ? JSON.parse(form.extraBody) : null,
    extra_query: form.extraQuery.trim() ? JSON.parse(form.extraQuery) : null,
  } } }, 900_000);
}
