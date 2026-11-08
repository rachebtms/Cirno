import type { CirnoClient } from "@/lib/cirno-client";

export async function downloadRecording(client: CirnoClient, recordingId: string, epoch: string) {
  const blob = await client.exportTraceRecording(recordingId, epoch);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = `cirno-trace-${recordingId}.zip`;
  document.body.append(link);
  try { link.click(); }
  finally { link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); }
}
